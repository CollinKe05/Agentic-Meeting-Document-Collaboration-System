from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import context_store


EXIT_KEYWORDS = {
    "exit",
    "clear context",
    "退出",
    "取消上下文",
    "清除上下文",
    "回到主对话",
    "回主对话",
    "换个话题",
    "不看刚才",
}
SYSTEM_TOPIC_KEYWORDS = {
    "部署",
    "代码",
    "模型",
    "接口",
    "wsl",
    "windows",
    "linux",
    "ubuntu",
    "typst",
    "怎么改",
    "报错",
    "路径",
    "环境",
    "llama",
    "gguf",
}
NEW_TASK_KEYWORDS = {
    "解析",
    "上传",
    "开始会议",
    "开始记录",
    "导出",
    "生成文件",
    "做合规审查",
    "审查",
    "下一个任务",
    "重新解析",
}
ANAPHORA_KEYWORDS = {
    "这个",
    "这张",
    "这份",
    "里面",
    "其中",
    "刚才",
    "刚刚",
    "上面",
    "前面",
    "它",
    "该",
    "继续",
    "根据它",
    "根据这个",
    "这次",
}


def resolve_transition(
    *,
    thread_id: str = context_store.THREAD_MAIN,
    user_message: str,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = str(user_message or "").strip()
    lowered = text.lower()
    attachments = attachments or []
    active = context_store.get_active_context(thread_id=thread_id, include_context=True)
    from_state = str(active.get("focus_state") or context_store.FOCUS_MAIN)

    if _contains_any(lowered, text, EXIT_KEYWORDS):
        context_store.clear_active_context(thread_id=thread_id, reason="explicit_exit")
        return _transition(
            "exit",
            from_state,
            context_store.FOCUS_MAIN,
            None,
            "用户显式退出上下文",
            confidence=1.0,
            should_notify_user=True,
        )

    explicit = _explicit_context_reference(text)
    if explicit:
        context = _latest_or_named_context(explicit, text)
        if context:
            active_state = context_store.focus_state_for_kind(str(context["kind"]))
            context_store.set_active_context(
                thread_id=thread_id,
                focus_state=active_state,
                context_id=str(context["id"]),
                entered_reason=f"explicit_{explicit}",
            )
            return _transition(
                "switch" if from_state != active_state else "continue",
                from_state,
                active_state,
                str(context["id"]),
                f"用户显式引用 {explicit} context",
                confidence=0.92,
                should_attach_context=True,
                should_notify_user=from_state != active_state,
            )

    if _is_new_task(text, attachments):
        if _should_keep_active_for_task(text, active):
            context_store.mark_active_used(thread_id=thread_id)
            return _transition(
                "task",
                from_state,
                from_state,
                active.get("context_id"),
                "新任务需要沿用当前业务上下文",
                confidence=0.82,
                should_attach_context=bool(active.get("context_id")),
            )
        context_store.age_active_context(thread_id=thread_id)
        return _transition(
            "task",
            from_state,
            context_store.FOCUS_MAIN,
            None,
            "检测到新文件或新任务，等待任务结果创建新上下文",
            confidence=0.85,
            should_attach_context=False,
        )

    if from_state != context_store.FOCUS_MAIN and _is_system_topic(text):
        context_store.clear_active_context(thread_id=thread_id, reason="system_topic")
        return _transition(
            "exit",
            from_state,
            context_store.FOCUS_MAIN,
            None,
            "检测到系统/代码/部署类问题，退出业务上下文",
            confidence=0.9,
            should_notify_user=True,
        )

    if active.get("context_id") and _contains_any(lowered, text, ANAPHORA_KEYWORDS):
        context_store.mark_active_used(thread_id=thread_id)
        return _transition(
            "continue",
            from_state,
            from_state,
            active.get("context_id"),
            "用户使用指代词继续当前上下文",
            confidence=0.84,
            should_attach_context=True,
        )

    if not _is_system_topic(text):
        candidate = _search_context_candidate(text)
        if candidate:
            active_state = context_store.focus_state_for_kind(str(candidate["kind"]))
            context_store.set_active_context(
                thread_id=thread_id,
                focus_state=active_state,
                context_id=str(candidate["id"]),
                entered_reason="fts_match",
            )
            return _transition(
                "enter",
                from_state,
                active_state,
                str(candidate["id"]),
                "根据上下文检索命中历史材料",
                confidence=0.68,
                should_attach_context=True,
                should_notify_user=True,
            )

    aged = context_store.age_active_context(thread_id=thread_id)
    if aged.get("focus_state") == context_store.FOCUS_MAIN and from_state != context_store.FOCUS_MAIN:
        return _transition(
            "exit",
            from_state,
            context_store.FOCUS_MAIN,
            None,
            "soft 上下文已过期",
            confidence=0.75,
            should_notify_user=False,
        )

    return _transition(
        "stay_main" if from_state == context_store.FOCUS_MAIN else "idle",
        from_state,
        str(aged.get("focus_state") or from_state),
        aged.get("context_id") if aged.get("focus_state") != context_store.FOCUS_MAIN else None,
        "默认不附加业务上下文",
        confidence=0.6,
        should_attach_context=False,
    )


def _transition(
    transition: str,
    from_state: str,
    to_state: str,
    target_context_id: Any,
    reason: str,
    *,
    confidence: float,
    should_attach_context: bool = False,
    should_notify_user: bool = False,
) -> dict[str, Any]:
    return {
        "transition": transition,
        "from_state": from_state,
        "to_state": to_state,
        "target_context_id": target_context_id,
        "mode": "soft",
        "reason": reason,
        "confidence": confidence,
        "should_attach_context": should_attach_context,
        "should_notify_user": should_notify_user,
    }


def _contains_any(lowered: str, original: str, keywords: set[str]) -> bool:
    return any(keyword in lowered or keyword in original for keyword in keywords)


def _is_system_topic(text: str) -> bool:
    lowered = text.lower()
    return _contains_any(lowered, text, SYSTEM_TOPIC_KEYWORDS)


def _is_new_task(text: str, attachments: list[dict[str, Any]]) -> bool:
    lowered = text.lower()
    if attachments:
        return True
    if _contains_any(lowered, text, NEW_TASK_KEYWORDS):
        return True
    return bool(re.search(r"uploads/[^\s<>]+|[\w./\-\u4e00-\u9fff]+\.(pdf|png|jpg|jpeg|txt|md|docx?)", text, re.I))


def _should_keep_active_for_task(text: str, active: dict[str, Any]) -> bool:
    state = str(active.get("focus_state") or "")
    if not active.get("context_id"):
        return False
    if state == "MEETING_ACTIVE" and any(word in text.lower() or word in text for word in {"导出", "pdf", "typst", "纪要", "格式化"}):
        return True
    return False


def _explicit_context_reference(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered or word in text for word in {"ocr", "识别", "图片", "这张图", "上一次ocr", "上次ocr"}):
        return "ocr"
    if any(word in lowered or word in text for word in {"会议", "纪要", "转写", "录音记录", "meeting"}):
        return "meeting"
    if any(word in lowered or word in text for word in {"文档", "文件", "document"}):
        return "document"
    return ""


def _latest_or_named_context(kind: str, text: str) -> dict[str, Any] | None:
    contexts = context_store.list_contexts(kind=kind, limit=30)
    if not contexts:
        return None
    names = _possible_names(text)
    for context in contexts:
        haystack = " ".join(
            [
                str(context.get("title") or ""),
                str(context.get("source_path") or ""),
                str(context.get("summary") or ""),
            ]
        ).lower()
        if any(name.lower() in haystack for name in names):
            return context
    return contexts[0]


def _search_context_candidate(text: str) -> dict[str, Any] | None:
    chunks = context_store.search_chunks(text, limit=5)
    if chunks:
        context = chunks[0].get("context") or {}
        context_id = context.get("id")
        if context_id:
            return context_store.get_context(str(context_id), include_artifacts=False)

    names = _possible_names(text)
    if names:
        for context in context_store.list_contexts(limit=50):
            haystack = f"{context.get('title', '')} {context.get('source_path', '')}".lower()
            if any(name.lower() in haystack for name in names):
                return context
    return None


def _possible_names(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"([A-Za-z0-9_.\-\u4e00-\u9fff]+\.[A-Za-z0-9]{2,5})", text):
        names.append(Path(match.group(1)).name)
    for match in re.finditer(r"(\d{4}[-_年]\d{1,2}[-_月]\d{1,2})", text):
        names.append(match.group(1))
    return names

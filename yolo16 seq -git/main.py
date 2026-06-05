"""syss CLI — 文档智能处理系统"""
import argparse
import sys
from pathlib import Path

from .config import SystemConfig
from .utils.pdf_utils import pdf_to_images
from .utils.json_utils import save_json, load_json
from .markdown.generator import json_to_markdown, json_to_markdown_detailed
from .merge.merger import BlockOCRMerger


def cmd_pipeline(args):
    from .pipeline import DocumentPipeline
    cfg = SystemConfig(
        yolo_model=args.yolo_model or "",
        ocr_model_dir=args.ocr_model_dir or "",
        layoutreader_model=args.layoutreader or "",
        char_dict=args.char_dict or "",
        layout_conf=args.layout_conf,
        layout_iou=args.layout_iou,
        ocr_rec_thresh=args.ocr_rec_thresh,
        block_score_filter=args.block_score_filter,
        dpi=args.dpi,
        keep_temp=args.keep_temp,
        debug=args.debug,
        labels=args.labels,
    )
    pipeline = DocumentPipeline(cfg)
    pipeline.run(args.input, args.output_dir)


def cmd_layout(args):
    from .layout.analyzer import LayoutAnalyzer
    cfg = SystemConfig(yolo_model=args.yolo_model or "", labels=args.labels)
    analyzer = LayoutAnalyzer(cfg.yolo_model, args.conf, args.iou, cfg.labels)
    images = pdf_to_images(args.input, dpi=args.dpi)
    for i, img in enumerate(images):
        blocks = analyzer.analyze(img, i)
        print(f"Page {i+1}: {len(blocks)} blocks")
        for b in blocks:
            print(f"  [{b.class_name}] score={b.score:.3f} bbox={b.bbox}")


def cmd_ocr(args):
    from .ocr.factory import create_ocr
    cfg = SystemConfig(
        ocr_model_dir=args.ocr_model_dir or "",
        char_dict=args.char_dict or "",
        ocr_rec_thresh=args.rec_thresh,
    )
    ocr = create_ocr(cfg)
    images = pdf_to_images(args.input, dpi=args.dpi)
    for i, img in enumerate(images):
        result = ocr.process_image(img, i)
        print(f"Page {i+1}: {len(result.results)} text lines")
        for r in result.results:
            print(f"  [{r.score:.3f}] {r.transcription[:60]}")


def cmd_merge(args):
    from .layout.analyzer import LayoutAnalyzer
    from .ocr.factory import create_ocr
    cfg = SystemConfig(
        yolo_model=args.yolo_model or "",
        ocr_model_dir=args.ocr_model_dir or "",
        char_dict=args.char_dict or "",
        ocr_rec_thresh=args.ocr_rec_thresh,
        block_score_filter=args.block_score_filter,
        labels=args.labels,
    )
    analyzer = LayoutAnalyzer(cfg.yolo_model, args.layout_conf, args.layout_iou, cfg.labels)
    ocr = create_ocr(cfg)
    merger = BlockOCRMerger(score_filter=cfg.block_score_filter)
    images = pdf_to_images(args.input, dpi=args.dpi)
    blocks_by_page = analyzer.analyze_images(images)
    ocr_results = ocr.process_images(images)
    merged = merger.merge_all(blocks_by_page, ocr_results)
    save_json(merged, args.output)
    print(f"Merged result saved: {args.output}")


def cmd_sort(args):
    from .reading_order.fast_sorter import FastReadingOrderSorter
    sorter = FastReadingOrderSorter()
    data = load_json(args.input)
    sorted_data = sorter.sort(data)
    save_json(sorted_data, args.output)
    print(f"Sorted result saved: {args.output}")


def cmd_markdown(args):
    data = load_json(args.input)
    if args.detailed:
        json_to_markdown_detailed(data, args.output)
    else:
        json_to_markdown(data, args.output)
    print(f"Markdown saved: {args.output}")


def cmd_llm(args):
    from .llm.client import LLMClient
    client = LLMClient(model=args.model)
    result = client.process(
        args.input, args.output, mode=args.mode, direction=args.direction or "zh2en"
    )
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Done ({result['elapsed']}s): {result['output_file']}")


def main():
    parser = argparse.ArgumentParser(description="文档智能处理系统")
    sub = parser.add_subparsers(dest="command")

    # ── pipeline ──
    p_pl = sub.add_parser("pipeline", help="完整流水线: PDF → MD")
    p_pl.add_argument("-i", "--input", required=True)
    p_pl.add_argument("-o", "--output-dir", default="./output")
    p_pl.add_argument("--yolo-model", default="")
    p_pl.add_argument("--ocr-model-dir", default="")
    p_pl.add_argument("--layoutreader", default="")
    p_pl.add_argument("--char-dict", default="")
    p_pl.add_argument("--layout-conf", type=float, default=0.2)
    p_pl.add_argument("--layout-iou", type=float, default=0.5)
    p_pl.add_argument("--ocr-rec-thresh", type=float, default=0.5)
    p_pl.add_argument("--block-score-filter", type=float, default=0.5)
    p_pl.add_argument("--dpi", type=int, default=200)
    p_pl.add_argument("--labels", default="cn")
    p_pl.add_argument("--keep-temp", action="store_true")
    p_pl.add_argument("--debug", action="store_true")

    # ── layout ──
    p_lo = sub.add_parser("layout", help="仅版面分析")
    p_lo.add_argument("-i", "--input", required=True)
    p_lo.add_argument("--yolo-model", default="")
    p_lo.add_argument("--conf", type=float, default=0.2)
    p_lo.add_argument("--iou", type=float, default=0.5)
    p_lo.add_argument("--dpi", type=int, default=200)
    p_lo.add_argument("--labels", default="cn")

    # ── ocr ──
    p_oc = sub.add_parser("ocr", help="仅 OCR")
    p_oc.add_argument("-i", "--input", required=True)
    p_oc.add_argument("--ocr-model-dir", default="")
    p_oc.add_argument("--char-dict", default="")
    p_oc.add_argument("--rec-thresh", type=float, default=0.5)
    p_oc.add_argument("--dpi", type=int, default=200)

    # ── merge ──
    p_mg = sub.add_parser("merge", help="版面+OCR 合并")
    p_mg.add_argument("-i", "--input", required=True)
    p_mg.add_argument("-o", "--output", required=True)
    p_mg.add_argument("--yolo-model", default="")
    p_mg.add_argument("--ocr-model-dir", default="")
    p_mg.add_argument("--char-dict", default="")
    p_mg.add_argument("--layout-conf", type=float, default=0.2)
    p_mg.add_argument("--layout-iou", type=float, default=0.5)
    p_mg.add_argument("--ocr-rec-thresh", type=float, default=0.5)
    p_mg.add_argument("--block-score-filter", type=float, default=0.5)
    p_mg.add_argument("--dpi", type=int, default=200)
    p_mg.add_argument("--labels", default="cn")

    # ── sort ──
    p_so = sub.add_parser("sort", help="阅读排序")
    p_so.add_argument("-i", "--input", required=True)
    p_so.add_argument("-o", "--output", required=True)
    p_so.add_argument("--layoutreader", default="")

    # ── markdown ──
    p_md = sub.add_parser("markdown", help="JSON → Markdown")
    p_md.add_argument("-i", "--input", required=True)
    p_md.add_argument("-o", "--output", required=True)
    p_md.add_argument("--detailed", action="store_true")

    # ── llm ──
    p_lm = sub.add_parser("llm", help="LLM 后处理")
    p_lm.add_argument("-i", "--input", required=True)
    p_lm.add_argument("-o", "--output", default="")
    p_lm.add_argument("-m", "--mode", choices=["summary", "extract", "refine", "translate"], default="summary")
    p_lm.add_argument("-d", "--direction", choices=["zh2en", "en2zh"], default="zh2en")
    p_lm.add_argument("--model", default="qwen2.5:1.5b")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    cmds = {
        "pipeline": cmd_pipeline, "layout": cmd_layout,
        "ocr": cmd_ocr, "merge": cmd_merge,
        "sort": cmd_sort, "markdown": cmd_markdown, "llm": cmd_llm,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()

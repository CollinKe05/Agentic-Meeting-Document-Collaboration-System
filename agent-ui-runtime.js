(function () {
  const inputElement = document.getElementById('prompt-input');
  const chatMessages = document.getElementById('chat-messages');
  const fileInput = document.getElementById('file-input');
  const filePreviewArea = document.getElementById('file-preview-area');
  const thoughtProcessPanel = document.getElementById('agent-thought-process');
  const thoughtStepsContainer = document.getElementById('thought-steps');
  const taskList = document.getElementById('task-list');
  const sendButton = document.getElementById('send-btn');
  const voiceInputButton = document.getElementById('voice-input-btn');
  const meetingToggleButton = document.getElementById('meeting-toggle-btn');
  const meetingStatusText = document.getElementById('meeting-status-text');
  const meetingStatusDot = document.getElementById('meeting-status-dot');
  const meetingControl = document.getElementById('meeting-control');
  const meetingControlDetails = document.getElementById('meeting-control-details');
  const meetingCollapseButton = document.getElementById('meeting-collapse-btn');
  const resourceStatusText = document.getElementById('resource-status-text');
  const resourceStatusDot = document.getElementById('resource-status-dot');
  const modelSelect = document.getElementById('model-select');
  const skillEditor = document.querySelector('textarea[placeholder^="在此定义Agent技能"]');
  const skillSaveButton = document.getElementById('save-skill-button') || document.querySelector('button[onclick*="已保存技能配置"]');
  const featuresPanel = document.querySelector('main > aside:last-child .p-3.overflow-y-auto');
  const activeContextBar = document.getElementById('active-context-bar');
  const contextLibrary = document.getElementById('context-library');
  const refreshContextsButton = document.getElementById('refresh-contexts-btn');

  let selectedFiles = [];
  let pendingFeature = null;
  let activeEventSource = null;
  let currentSkillName = 'ui_skill.md';
  let currentTaskDoneShown = false;
  let meetingRunning = false;
  let voiceInputRunning = false;
  let latestMeetingTranscript = '';
  let latestVoiceTranscript = '';
  let meetingCollapsed = localStorage.getItem('agentMeetingCollapsed') === '1';
  let switchingModel = false;

  function applyResponsiveDensity() {
    const dpr = window.devicePixelRatio || 1;
    const width = window.innerWidth || document.documentElement.clientWidth || 0;
    const height = window.innerHeight || document.documentElement.clientHeight || 0;
    const compact = dpr >= 1.2 || width < 1360 || height < 760;
    const dense = dpr >= 1.45 || width < 1120 || height < 680;
    const narrow = width < 980;

    document.body.classList.toggle('edge-compact', compact);
    document.body.classList.toggle('edge-dense', dense);
    document.body.classList.toggle('edge-narrow', narrow);
    document.documentElement.style.setProperty('--screen-dpr', dpr.toFixed(2));
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function iconSvg(kind, extraClass) {
    const klass = extraClass || 'w-4 h-4';
    const icons = {
      ok: `<svg class="${klass}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>`,
      run: `<svg class="${klass} animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>`,
      file: `<svg class="${klass}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>`,
      bot: `<svg class="${klass}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 3v2m6-2v2M5 9H3m18 0h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h.01M15 9h.01M8 14h8" /></svg>`,
      user: `<svg class="${klass}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>`,
      send: `<svg class="${klass}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>`,
      mic: `<svg class="${klass}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 18.5v3m0 0h3m-3 0H9M8 10a4 4 0 108 0V6a4 4 0 10-8 0v4zm10 0a6 6 0 01-12 0" /></svg>`,
      x: `<svg class="${klass}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>`
    };
    return icons[kind] || icons.ok;
  }

  function toast(message) {
    if (typeof window.showLocalToast === 'function') {
      window.showLocalToast(message);
      return;
    }
    console.log(message);
  }

  function setSendBusy(isBusy) {
    if (!sendButton) return;
    sendButton.disabled = isBusy;
    sendButton.innerHTML = isBusy
      ? iconSvg('run', 'h-5 w-5 text-white')
      : iconSvg('send', 'w-5 h-5');
  }

  function appendMessage(sender, text, files) {
    const wrapper = document.createElement('div');
    wrapper.className = `flex items-start gap-3 ${sender === 'user' ? 'flex-row-reverse' : ''}`;
    const avatar = document.createElement('div');
    avatar.className = `w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
      sender === 'user' ? 'bg-indigo-100 text-indigo-600' : sender === 'error' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'
    }`;
    avatar.innerHTML = sender === 'user' ? iconSvg('user', 'w-5 h-5') : iconSvg('bot', 'w-5 h-5');

    const bubble = document.createElement('div');
    const bubbleColors = sender === 'user'
      ? 'bg-indigo-600 text-white rounded-tr-none'
      : sender === 'error'
        ? 'bg-white border border-red-100 text-red-700 rounded-tl-none shadow-sm'
        : 'bg-white border border-gray-100 text-gray-800 rounded-tl-none shadow-sm';
    bubble.className = `p-4 rounded-2xl max-w-[85%] ${bubbleColors} whitespace-pre-wrap break-words text-sm`;

    if (files && files.length) {
      const fileContainer = document.createElement('div');
      fileContainer.className = 'flex flex-wrap gap-2 mb-2';
      fileContainer.innerHTML = files.map(file => `
        <div class="flex items-center gap-1 bg-black/10 px-2 py-1 rounded text-xs">
          ${iconSvg('file', 'w-3 h-3')} ${escapeHtml(file.name || file.path || file)}
        </div>
      `).join('');
      bubble.appendChild(fileContainer);
    }

    const textEl = document.createElement('span');
    textEl.textContent = text;
    bubble.appendChild(textEl);
    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function renderFilePreviews() {
    if (!filePreviewArea) return;
    if (!selectedFiles.length) {
      filePreviewArea.classList.add('hidden');
      filePreviewArea.innerHTML = '';
      return;
    }
    filePreviewArea.classList.remove('hidden');
    filePreviewArea.innerHTML = selectedFiles.map((file, index) => `
      <div class="flex items-center gap-1.5 bg-white border border-gray-200 px-2 py-1 rounded text-[11px] text-gray-700 shrink-0 shadow-sm">
        ${iconSvg('file', 'w-3.5 h-3.5 text-gray-500')}
        <span class="max-w-[120px] truncate" title="${escapeHtml(file.name || file.path)}">${escapeHtml(file.name || file.path)}</span>
        <button data-remove-index="${index}" class="text-gray-400 hover:text-red-500 focus:outline-none ml-1">${iconSvg('x', 'w-3 h-3')}</button>
      </div>
    `).join('');
    filePreviewArea.querySelectorAll('[data-remove-index]').forEach(button => {
      button.addEventListener('click', () => {
        selectedFiles.splice(Number(button.dataset.removeIndex), 1);
        renderFilePreviews();
      });
    });
  }

  async function uploadFiles(files) {
    const uploaded = [];
    for (const file of files) {
      if (file.path) {
        uploaded.push(file);
        continue;
      }
      const form = new FormData();
      form.append('file', file);
      toast(`正在上传：${file.name}`);
      const response = await fetch('/api/upload', { method: 'POST', body: form });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || '上传失败');
      }
      uploaded.push(...payload.files);
    }
    return uploaded;
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `请求失败：${response.status}`);
    }
    return payload;
  }

  function contextKindLabel(kind) {
    return { ocr: 'OCR', meeting: '会议', document: '文档' }[kind] || kind || '上下文';
  }

  function renderActiveContext(active) {
    if (!activeContextBar) return;
    const context = active && active.context;
    if (!context || active.focus_state === 'MAIN') {
      activeContextBar.classList.add('hidden');
      activeContextBar.innerHTML = '';
      return;
    }
    activeContextBar.classList.remove('hidden');
    activeContextBar.innerHTML = `
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0">
          <span class="font-semibold">当前上下文：</span>
          <span>${escapeHtml(contextKindLabel(context.kind))} · ${escapeHtml(context.title || context.id)}</span>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button id="active-context-view" class="text-blue-700 hover:text-blue-900 focus:outline-none">查看</button>
          <button id="active-context-clear" class="text-gray-500 hover:text-red-600 focus:outline-none">退出</button>
        </div>
      </div>
    `;
    const view = activeContextBar.querySelector('#active-context-view');
    const clear = activeContextBar.querySelector('#active-context-clear');
    if (view) view.addEventListener('click', () => showContextDetail(context.id));
    if (clear) clear.addEventListener('click', clearActiveContext);
  }

  async function loadActiveContext() {
    if (!activeContextBar) return;
    try {
      const response = await fetch('/api/context/active');
      const payload = await response.json();
      if (payload.ok) renderActiveContext(payload.active || {});
    } catch {
      return;
    }
  }

  async function loadContexts() {
    if (!contextLibrary) return;
    try {
      const response = await fetch('/api/contexts?limit=12');
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || '上下文读取失败');
      const contexts = payload.contexts || [];
      contextLibrary.innerHTML = contexts.length ? contexts.map(context => `
        <button data-context-id="${escapeHtml(context.id)}" class="w-full text-left p-2 rounded-lg border border-gray-100 hover:border-blue-200 hover:bg-blue-50 transition-colors focus:outline-none">
          <div class="flex items-center justify-between gap-2">
            <span class="text-[11px] font-medium text-gray-800 truncate">${escapeHtml(context.title || context.id)}</span>
            <span class="text-[10px] text-blue-600 shrink-0">${escapeHtml(contextKindLabel(context.kind))}</span>
          </div>
          <p class="text-[10px] text-gray-500 mt-0.5">${escapeHtml(context.summary || context.source_path || '')}</p>
        </button>
      `).join('') : '<p class="text-[11px] text-gray-400 px-1 py-2">暂无上下文</p>';
      contextLibrary.querySelectorAll('[data-context-id]').forEach(button => {
        button.addEventListener('click', () => activateContext(button.dataset.contextId));
      });
    } catch (error) {
      contextLibrary.innerHTML = `<p class="text-[11px] text-red-500 px-1 py-2">${escapeHtml(error.message)}</p>`;
    }
  }

  async function activateContext(contextId) {
    if (!contextId) return;
    try {
      await postJson(`/api/contexts/${encodeURIComponent(contextId)}/activate`, {});
      await loadActiveContext();
      await loadContexts();
      toast('已切换上下文');
    } catch (error) {
      appendMessage('error', `上下文切换失败：${error.message}`);
    }
  }

  async function clearActiveContext() {
    try {
      await postJson('/api/context/clear-active', {});
      await loadActiveContext();
      toast('已退出上下文');
    } catch (error) {
      appendMessage('error', `退出上下文失败：${error.message}`);
    }
  }

  async function showContextDetail(contextId) {
    try {
      const response = await fetch(`/api/contexts/${encodeURIComponent(contextId)}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || '上下文读取失败');
      const context = payload.context || {};
      const artifacts = (context.artifacts || []).map(item => `- ${item.artifact_type}: ${item.path}`).join('\n') || '无';
      appendMessage('agent', `上下文：${context.title}\n类型：${contextKindLabel(context.kind)}\n来源：${context.source_path || '无'}\n摘要：${context.summary || '无'}\n\nArtifacts:\n${artifacts}`);
    } catch (error) {
      appendMessage('error', `查看上下文失败：${error.message}`);
    }
  }

  async function putJson(url, body) {
    const response = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `请求失败：${response.status}`);
    }
    return payload;
  }

  function formatModelLabel(model) {
    const size = Number(model && model.size_bytes || 0);
    const gb = size > 0 ? ` ${(size / 1024 / 1024 / 1024).toFixed(1)}G` : '';
    return `${model && model.name ? model.name : 'unknown'}${gb}`;
  }

  async function loadModels() {
    if (!modelSelect) return;
    try {
      const response = await fetch('/api/models');
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error || '模型列表读取失败');
      const models = payload.models || [];
      modelSelect.innerHTML = '';
      if (!models.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '未发现 GGUF';
        modelSelect.appendChild(option);
        modelSelect.disabled = true;
        return;
      }
      modelSelect.disabled = false;
      for (const model of models) {
        const option = document.createElement('option');
        option.value = model.id;
        option.textContent = formatModelLabel(model);
        option.title = model.path || '';
        if (model.selected) option.selected = true;
        modelSelect.appendChild(option);
      }
    } catch (error) {
      modelSelect.innerHTML = '<option value="">模型读取失败</option>';
      modelSelect.disabled = true;
      toast(`模型列表读取失败：${error.message}`);
    }
  }

  async function switchModel(modelId) {
    if (!modelSelect || !modelId || switchingModel) return;
    switchingModel = true;
    modelSelect.disabled = true;
    try {
      const payload = await postJson('/api/models/select', { model_id: modelId });
      toast(`已切换模型：${formatModelLabel(payload.model)}`);
      await loadModels();
      await refreshSystemStatus();
    } catch (error) {
      toast(`模型切换失败：${error.message}`);
      await loadModels();
    } finally {
      switchingModel = false;
      if (modelSelect.options.length) modelSelect.disabled = false;
    }
  }

  function addThoughtStep(event) {
    if (!thoughtProcessPanel || !thoughtStepsContainer) return;
    thoughtProcessPanel.classList.remove('hidden');
    const step = document.createElement('div');
    step.className = 'flex items-start gap-2 animate-fade-in-up min-w-0';
    const isError = event.type === 'ERROR';
    step.innerHTML = `
      <div class="mt-0.5 shrink-0">${iconSvg(isError ? 'x' : 'ok', `w-4 h-4 ${isError ? 'text-red-500' : 'text-indigo-500'}`)}</div>
      <span class="text-gray-600 min-w-0"><strong>${escapeHtml(event.title || event.type)}</strong>${event.message ? `：${escapeHtml(event.message)}` : ''}</span>
    `;
    thoughtStepsContainer.appendChild(step);
    thoughtStepsContainer.scrollTop = thoughtStepsContainer.scrollHeight;
  }

  async function submitTask(promptText, files) {
    const prompt = (promptText || inputElement.value || '').trim();
    const fileList = files || selectedFiles;
    if (!prompt && !fileList.length) return;
    setSendBusy(true);
    thoughtStepsContainer.innerHTML = '';
    thoughtProcessPanel.classList.remove('hidden');

    try {
      const uploaded = await uploadFiles(fileList);
      const finalPrompt = prompt || `请读取并处理这些文件：${uploaded.map(file => file.path).join(', ')}`;
      appendMessage('user', finalPrompt, uploaded);
      inputElement.value = '';
      inputElement.style.height = 'auto';
      selectedFiles = [];
      renderFilePreviews();

      const created = await postJson('/api/tasks', {
        prompt: finalPrompt,
        attachments: uploaded,
        backend: 'llama_cpp'
      });
      await loadTasks();
      subscribeTask(created.task_id);
    } catch (error) {
      appendMessage('error', `任务提交失败：${error.message}`);
      setSendBusy(false);
    }
  }

  function subscribeTask(taskId) {
    if (activeEventSource) activeEventSource.close();
    currentTaskDoneShown = false;
    activeEventSource = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events`);
    activeEventSource.addEventListener('agent_event', event => {
      const data = JSON.parse(event.data);
      addThoughtStep(data);
      if (data.type === 'CONTEXT_TRANSITION' && data.payload && data.payload.should_notify_user) {
        toast(data.message || '上下文已切换');
      }
      if (data.type === 'TASK_DONE') {
        currentTaskDoneShown = true;
        appendMessage('agent', data.message || '任务完成。');
        setSendBusy(false);
        loadTasks();
        loadActiveContext();
        loadContexts();
      }
      if (data.type === 'ERROR') {
        appendMessage('error', data.message || '任务失败。');
        setSendBusy(false);
        loadTasks();
        loadActiveContext();
        loadContexts();
      }
    });
    activeEventSource.addEventListener('task_state', event => {
      const data = JSON.parse(event.data);
      const task = data.task || {};
      if (!currentTaskDoneShown && task.result) {
        currentTaskDoneShown = true;
        appendMessage('agent', task.result);
      }
      if (!currentTaskDoneShown && task.error) {
        appendMessage('error', task.error);
      }
      setSendBusy(false);
      loadTasks();
      loadActiveContext();
      loadContexts();
      activeEventSource.close();
    });
    activeEventSource.onerror = () => {
      setSendBusy(false);
      if (activeEventSource) activeEventSource.close();
    };
  }

  async function loadTasks() {
    const response = await fetch('/api/tasks');
    const payload = await response.json();
    if (!payload.ok || !taskList) return;
    taskList.innerHTML = '';
    for (const task of payload.tasks || []) {
      const failed = task.status === 'failed';
      const running = task.status === 'running' || task.status === 'queued';
      const node = document.createElement('div');
      node.className = 'p-2 rounded bg-gray-50 border border-gray-100 flex items-start gap-2 cursor-pointer hover:bg-blue-50 transition-all';
      node.innerHTML = `
        <div class="shrink-0 ${failed ? 'text-red-500' : running ? 'text-blue-500' : 'text-green-500'} mt-0.5">
          ${running ? iconSvg('run', 'h-4 w-4') : failed ? iconSvg('x', 'h-4 w-4') : iconSvg('ok', 'h-4 w-4')}
        </div>
        <div class="min-w-0">
          <p class="font-medium text-xs text-gray-700 truncate">${escapeHtml(task.prompt || '')}</p>
          <p class="text-[10px] text-gray-500">${escapeHtml(task.created_at || '')} · ${escapeHtml(statusText(task.status))}</p>
        </div>
      `;
      node.addEventListener('click', () => replayTask(task.id));
      taskList.appendChild(node);
    }
  }

  async function replayTask(taskId) {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`);
    const payload = await response.json();
    if (!payload.ok) return;
    thoughtStepsContainer.innerHTML = '';
    thoughtProcessPanel.classList.remove('hidden');
    for (const event of payload.events || []) addThoughtStep(event);
    if (payload.task.result) appendMessage('agent', payload.task.result);
    if (payload.task.error) appendMessage('error', payload.task.error);
  }

  function statusText(status) {
    return {
      queued: '排队中',
      running: '处理中',
      completed: '完成',
      failed: '失败',
      cancelled: '取消'
    }[status] || status || '未知';
  }

  async function loadFeatures() {
    if (!featuresPanel) return;
    const response = await fetch('/api/features');
    const payload = await response.json();
    if (!payload.ok) return;
    featuresPanel.innerHTML = '';
    for (const feature of payload.features || []) {
      const button = document.createElement('button');
      button.className = 'w-full text-left p-2.5 rounded-lg border border-gray-100 hover:border-blue-200 hover:bg-blue-50 transition-all group focus:outline-none';
      button.innerHTML = `
        <div class="flex items-center gap-2.5">
          <div class="w-7 h-7 rounded bg-blue-100 text-blue-600 flex items-center justify-center shrink-0">${iconSvg('file', 'w-4 h-4')}</div>
          <div>
            <h3 class="font-medium text-xs text-gray-800 group-hover:text-blue-700">${escapeHtml(feature.title)}</h3>
            <p class="text-[10px] text-gray-500 mt-0.5">${escapeHtml(feature.description)}</p>
          </div>
        </div>
      `;
      button.addEventListener('click', () => {
        if (feature.action === 'meeting-summary') {
          requestMeetingSummary();
          return;
        }
        if (feature.action === 'meeting-minutes-export') {
          requestMeetingMinutesExport(feature);
          return;
        }
        if (feature.action === 'ocr-summary-export') {
          requestOcrSummaryExport(feature);
          return;
        }
        if (feature.needsFile) {
          pendingFeature = feature;
          fileInput.click();
        } else {
          inputElement.value = feature.prompt;
          inputElement.focus();
          if (typeof window.autoResize === 'function') window.autoResize(inputElement);
        }
      });
      featuresPanel.appendChild(button);
    }
    appendCryptoFeatureCard();
  }

  function appendCryptoFeatureCard() {
    if (!featuresPanel) return;
    const card = document.createElement('div');
    card.className = 'w-full p-2.5 rounded-lg border border-amber-100 bg-amber-50/40';
    card.innerHTML = `
      <div class="flex items-start gap-2.5">
        <div class="w-7 h-7 rounded bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">${iconSvg('file', 'w-4 h-4')}</div>
        <div class="min-w-0 flex-1">
          <h3 class="font-medium text-xs text-gray-800">Markdown 加密工具</h3>
          <p class="text-[10px] text-gray-500 mt-0.5">人工选择文件，不进入 Agent 任务规划。</p>
          <div class="grid grid-cols-2 gap-1.5 mt-2">
            <button type="button" data-crypto-op="encrypt" class="px-2 py-1.5 rounded-md bg-white border border-amber-200 text-[11px] text-amber-800 hover:bg-amber-100 focus:outline-none">加密</button>
            <button type="button" data-crypto-op="decrypt" class="px-2 py-1.5 rounded-md bg-white border border-amber-200 text-[11px] text-amber-800 hover:bg-amber-100 focus:outline-none">解密</button>
          </div>
        </div>
      </div>
    `;
    card.querySelectorAll('[data-crypto-op]').forEach(button => {
      button.addEventListener('click', () => chooseCryptoFile(button.getAttribute('data-crypto-op')));
    });
    featuresPanel.appendChild(card);
  }

  async function loadSkill() {
    if (!skillEditor) return;
    let response = await fetch(`/api/skills?name=${encodeURIComponent(currentSkillName)}`);
    let payload = await response.json();
    if (!payload.ok) {
      const list = await (await fetch('/api/skills')).json();
      currentSkillName = (list.skills && list.skills[0]) || currentSkillName;
      response = await fetch(`/api/skills?name=${encodeURIComponent(currentSkillName)}`);
      payload = await response.json();
    }
    if (payload.ok) skillEditor.value = payload.content || '';
  }

  async function saveSkill() {
    if (!skillEditor) return;
    try {
      const payload = await putJson('/api/skills', { name: currentSkillName, content: skillEditor.value });
      currentSkillName = payload.name;
      toast(`Skill 已保存：${payload.name}`);
    } catch (error) {
      toast(`Skill 保存失败：${error.message}`);
    }
  }

  function updateMeetingUi(status) {
    meetingRunning = Boolean(status && status.running);
    latestMeetingTranscript = (status && status.transcript || '').trim();
    const asrState = status && status.asr_state || {};
    const stateName = (status && status.status) || '';
    const stateMessage = asrState.message || '';
    const preview = latestMeetingTranscript ? latestMeetingTranscript.slice(-120) : stateMessage;
    const label = meetingRunning
      ? stateName === 'loading'
        ? '加载 ASR 模型中'
        : stateName === 'ready'
          ? 'ASR 就绪，正在转写'
          : '会议中'
      : '等待会议请求';
    if (meetingStatusText) {
      meetingStatusText.textContent = preview ? `${label} · ${preview}` : label;
      meetingStatusText.className = `text-[11px] mt-0.5 ${meetingRunning ? 'text-red-600' : 'text-green-600'}`;
      meetingStatusText.title = latestMeetingTranscript || stateMessage || label;
    }
    if (meetingStatusDot) {
      meetingStatusDot.className = `w-2.5 h-2.5 rounded-full ${meetingRunning ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`;
    }
    if (meetingToggleButton) {
      meetingToggleButton.textContent = meetingRunning ? 'OFF' : 'ON';
      meetingToggleButton.className = `px-3 py-1.5 rounded-lg text-white text-xs font-medium focus:outline-none ${
        meetingRunning ? 'bg-red-600 hover:bg-red-700' : 'bg-gray-900 hover:bg-gray-700'
      }`;
    }
  }

  function applyMeetingCollapsed() {
    if (!meetingControl) return;
    meetingControl.classList.toggle('w-64', !meetingCollapsed);
    meetingControl.classList.toggle('w-auto', meetingCollapsed);
    meetingControl.classList.toggle('p-3', !meetingCollapsed);
    meetingControl.classList.toggle('p-2', meetingCollapsed);
    if (meetingControlDetails) meetingControlDetails.classList.toggle('hidden', meetingCollapsed);
    if (meetingCollapseButton) {
      meetingCollapseButton.textContent = meetingCollapsed ? '展开' : '−';
      meetingCollapseButton.title = meetingCollapsed ? '展开会议浮窗' : '收起会议浮窗';
    }
  }

  function updateResourceUi(status) {
    if (!resourceStatusText && !resourceStatusDot) return;
    const engine = status && status.active_engine ? status.active_engine : 'UNKNOWN';
    const llamaRunning = Boolean(status && status.llama_server_running);
    const modelName = status && status.current_model && status.current_model.name ? ` / ${status.current_model.name}` : '';
    const label = `资源状态：${engine} / llama-server ${llamaRunning ? '运行中' : '已停止'}${modelName}`;
    const colorClass = engine === 'IDLE'
      ? 'bg-green-500'
      : engine === 'OCR_RUNNING'
        ? 'bg-amber-500 animate-pulse'
        : engine === 'ASR_STREAMING'
          ? 'bg-red-500 animate-pulse'
          : 'bg-blue-500 animate-pulse';
    if (resourceStatusText) resourceStatusText.textContent = label;
    if (resourceStatusDot) resourceStatusDot.className = `w-2 h-2 rounded-full ${colorClass}`;
  }

  async function refreshSystemStatus() {
    try {
      const response = await fetch('/api/system/status');
      const payload = await response.json();
      if (payload.ok) updateResourceUi(payload);
    } catch {
      return;
    }
  }

  async function refreshMeetingStatus() {
    try {
      const response = await fetch('/api/meeting/status');
      const payload = await response.json();
      if (payload.ok) updateMeetingUi(payload.meeting || {});
    } catch {
      return;
    }
  }

  async function toggleMeeting() {
    try {
      if (meetingRunning) {
        const payload = await postJson('/api/meeting/stop', {});
        updateMeetingUi(payload.meeting || {});
        await loadActiveContext();
        await loadContexts();
        const meeting = payload.meeting || {};
        const transcript = meeting.transcript || '';
        const workspacePath = meeting.workspace_transcript_relpath || '';
        const rawPath = meeting.transcript_path || '';
        const pathLines = [
          workspacePath ? `工作区会议记录：${workspacePath}` : '',
          meeting.workspace_transcript_path ? `工作区绝对路径：${meeting.workspace_transcript_path}` : '',
          rawPath ? `原始 ASR 文件：${rawPath}` : ''
        ].filter(Boolean).join('\n');
        const message = transcript
          ? `会议记录已结束。\n${pathLines ? `\n${pathLines}\n` : ''}\n转写内容：\n\n${transcript}`
          : `会议记录已结束，但没有读取到转写内容。${pathLines ? `\n\n${pathLines}` : ''}`;
        appendMessage('agent', message);
      } else {
        const payload = await postJson('/api/meeting/start', {});
        updateMeetingUi(payload.meeting || {});
        await loadActiveContext();
        await loadContexts();
        toast('会议记录已开启');
      }
    } catch (error) {
      appendMessage('error', `会议控制失败：${error.message}`);
    }
  }

  async function requestMeetingMinutesExport(feature) {
    try {
      const response = await fetch('/api/meeting/records?limit=50');
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || '读取会议记录列表失败');
      const records = payload.records || [];
      if (!records.length) {
        appendMessage('error', '还没有可导出的会议记录。请先结束一次会议记录，系统会把转写保存到 workspace_files/meeting_records/。');
        return;
      }
      showMeetingRecordPicker(records, feature);
    } catch (error) {
      appendMessage('error', `会议纪要导出失败：${error.message}`);
    }
  }

  function showMeetingRecordPicker(records, feature) {
    const old = document.getElementById('meeting-record-picker');
    if (old) old.remove();

    const overlay = document.createElement('div');
    overlay.id = 'meeting-record-picker';
    overlay.className = 'fixed inset-0 z-[70] bg-black/35 flex items-center justify-center p-4';
    overlay.innerHTML = `
      <div class="w-full max-w-2xl max-h-[80vh] bg-white rounded-xl shadow-xl border border-gray-100 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h3 class="text-sm font-semibold text-gray-800">选择会议记录</h3>
            <p class="text-[11px] text-gray-500 mt-0.5">来源目录：workspace_files/meeting_records/</p>
          </div>
          <button id="meeting-record-picker-close" class="px-2 py-1 rounded border border-gray-200 text-xs text-gray-500 hover:bg-gray-50">关闭</button>
        </div>
        <div class="p-3 overflow-y-auto max-h-[60vh] space-y-2">
          ${records.map((record, index) => `
            <button data-record-index="${index}" class="w-full text-left p-3 rounded-lg border border-gray-100 hover:border-blue-200 hover:bg-blue-50 transition-colors">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-xs font-medium text-gray-800 truncate">${escapeHtml(record.name)}</div>
                  <div class="text-[11px] text-gray-500 mt-1 break-all">${escapeHtml(record.path)}</div>
                </div>
                <div class="text-[10px] text-gray-400 shrink-0">${escapeHtml(record.updated_at || '')}</div>
              </div>
            </button>
          `).join('')}
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#meeting-record-picker-close').addEventListener('click', close);
    overlay.addEventListener('click', event => {
      if (event.target === overlay) close();
    });
    overlay.querySelectorAll('[data-record-index]').forEach(button => {
      button.addEventListener('click', () => {
        const record = records[Number(button.dataset.recordIndex)];
        close();
        const relPath = record.path;
        const prompt = feature.prompt.replaceAll('{path}', relPath);
        submitTask(prompt, [{ name: record.name, path: relPath }]);
      });
    });
  }

  async function requestMeetingSummary() {
    try {
      const payload = await postJson('/api/meeting/summary', {});
      thoughtStepsContainer.innerHTML = '';
      thoughtProcessPanel.classList.remove('hidden');
      subscribeTask(payload.task_id);
      await loadTasks();
    } catch (error) {
      appendMessage('error', `会议总结失败：${error.message}`);
    }
  }

  async function requestOcrSummaryExport(feature) {
    try {
      const response = await fetch('/api/ocr/records?limit=50');
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || '读取 OCR 记录列表失败');
      const records = payload.records || [];
      if (!records.length) {
        appendMessage('error', '还没有可总结的 OCR 结果。请先解析一个 PDF/图片，生成 workspace_files/ocr_outputs/*.md。');
        return;
      }
      showOcrRecordPicker(records, feature);
    } catch (error) {
      appendMessage('error', `OCR 总结导出失败：${error.message}`);
    }
  }

  function showOcrRecordPicker(records, feature) {
    const old = document.getElementById('ocr-record-picker');
    if (old) old.remove();

    const overlay = document.createElement('div');
    overlay.id = 'ocr-record-picker';
    overlay.className = 'fixed inset-0 z-[70] bg-black/35 flex items-center justify-center p-4';
    overlay.innerHTML = `
      <div class="w-full max-w-2xl max-h-[80vh] bg-white rounded-xl shadow-xl border border-gray-100 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h3 class="text-sm font-semibold text-gray-800">选择 OCR 文档</h3>
            <p class="text-[11px] text-gray-500 mt-0.5">来源目录：workspace_files/ocr_outputs/</p>
          </div>
          <button id="ocr-record-picker-close" class="px-2 py-1 rounded border border-gray-200 text-xs text-gray-500 hover:bg-gray-50">关闭</button>
        </div>
        <div class="p-3 overflow-y-auto max-h-[60vh] space-y-2">
          ${records.map((record, index) => `
            <button data-ocr-record-index="${index}" class="w-full text-left p-3 rounded-lg border border-gray-100 hover:border-blue-200 hover:bg-blue-50 transition-colors">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-xs font-medium text-gray-800 truncate">${escapeHtml(record.name)}</div>
                  <div class="text-[11px] text-gray-500 mt-1 break-all">${escapeHtml(record.path)}</div>
                </div>
                <div class="text-[10px] text-gray-400 shrink-0">${escapeHtml(record.updated_at || '')}</div>
              </div>
            </button>
          `).join('')}
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#ocr-record-picker-close').addEventListener('click', close);
    overlay.addEventListener('click', event => {
      if (event.target === overlay) close();
    });
    overlay.querySelectorAll('[data-ocr-record-index]').forEach(button => {
      button.addEventListener('click', () => {
        const record = records[Number(button.dataset.ocrRecordIndex)];
        close();
        const relPath = record.path;
        const prompt = `请使用 EXPORT_OCR_SUMMARY 生成 OCR 总结导出文档。Action Input 必须是 JSON：{"tool_name":"EXPORT_OCR_SUMMARY","args":{"path":"${relPath}"}}。输出 Markdown、Typst、PDF 和 metadata JSON 路径。`;
        submitTask(prompt, [{ name: record.name, path: relPath }]);
      });
    });
  }

  function chooseCryptoFile(operation) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.md,.markdown,.txt,text/markdown,text/plain';
    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      if (file) runCryptoOperation(operation, file);
    }, { once: true });
    input.click();
  }

  async function runCryptoOperation(operation, file) {
    try {
      const statusResponse = await fetch('/api/crypto/status');
      const status = await statusResponse.json();
      if (!status.ok || !status.available) {
        throw new Error(status.error || '加密模块不可用');
      }
      const key = window.prompt('请输入 Markdown 加密密钥。留空则使用服务端 MARKDOWN_ENCRYPT_KEY 或默认密钥。', '');
      if (key === null) return;
      const uploaded = await uploadFiles([file]);
      const target = uploaded[0];
      const endpoint = operation === 'decrypt' ? '/api/crypto/decrypt' : '/api/crypto/encrypt';
      const result = await postJson(endpoint, { path: target.path, key });
      const label = operation === 'decrypt' ? '解密' : '加密';
      toast(`${label}完成：${result.output_path}`);
      appendMessage(
        'agent',
        `Markdown ${label}完成。\n源文件：${target.path}\n输出文件：${result.output_path}\n绝对路径：${result.absolute_output_path}`
      );
    } catch (error) {
      appendMessage('error', `Markdown 加密工具失败：${error.message}`);
    }
  }

  async function refreshVoiceInputStatus() {
    if (!voiceInputRunning) return;
    try {
      const response = await fetch('/api/voice-input/status');
      const payload = await response.json();
      const voice = payload.voice_input || {};
      if (!payload.ok) return;
      voiceInputRunning = Boolean(voice.running);
      latestVoiceTranscript = (voice.transcript || '').trim();
      updateVoiceButton();
      if (latestVoiceTranscript && inputElement) {
        inputElement.value = latestVoiceTranscript;
        if (typeof window.autoResize === 'function') window.autoResize(inputElement);
      }
    } catch {
      return;
    }
  }

  function updateVoiceButton() {
    if (!voiceInputButton) return;
    voiceInputButton.className = `p-2.5 rounded-lg transition-colors focus:outline-none ${
      voiceInputRunning ? 'text-white bg-rose-600 hover:bg-rose-700' : 'text-gray-400 hover:text-rose-500 hover:bg-rose-50'
    }`;
    voiceInputButton.innerHTML = voiceInputRunning ? iconSvg('run', 'w-5 h-5 text-white') : iconSvg('mic', 'w-5 h-5');
    voiceInputButton.title = voiceInputRunning
      ? (latestVoiceTranscript ? `正在转写：${latestVoiceTranscript.slice(-80)}` : '语音输入已开启，正在加载或监听')
      : '语音输入';
  }

  async function toggleVoiceInput() {
    try {
      if (voiceInputRunning) {
        const payload = await postJson('/api/voice-input/stop', {});
        voiceInputRunning = false;
        updateVoiceButton();
        const transcript = (payload.voice_input && payload.voice_input.transcript || latestVoiceTranscript || '').trim();
        if (transcript) {
          inputElement.value = transcript;
          inputElement.focus();
          if (typeof window.autoResize === 'function') window.autoResize(inputElement);
        }
      } else {
        latestVoiceTranscript = '';
        await postJson('/api/voice-input/start', {});
        voiceInputRunning = true;
        updateVoiceButton();
        toast('语音输入已开启，再次点击结束');
      }
    } catch (error) {
      voiceInputRunning = false;
      updateVoiceButton();
      appendMessage('error', `语音输入失败：${error.message}`);
    }
  }

  window.sendMessage = function () {
    submitTask(inputElement.value, selectedFiles);
  };

  window.removeFile = function (index) {
    selectedFiles.splice(index, 1);
    renderFilePreviews();
  };

  window.insertPrompt = function (text) {
    inputElement.value = text;
    inputElement.focus();
    if (typeof window.autoResize === 'function') window.autoResize(inputElement);
  };

  window.triggerFunction = function (type) {
    const fallback = {
      file_parse: { prompt: '请使用 PARSE_DOCUMENT_WITH_OCR_PC 解析文件 {path}，返回 Markdown、content_list_v2、图片目录，并总结 OCR 解析结果。', needsFile: true },
      code_review: { prompt: '请读取代码文件 {path}，做一次代码 Review。', needsFile: true }
    };
    pendingFeature = fallback[type] || fallback.file_parse;
    fileInput.click();
  };

  fileInput.addEventListener('change', event => {
    event.stopImmediatePropagation();
    const incoming = Array.from(event.target.files || []);
    if (!incoming.length) return;
    if (pendingFeature) {
      const feature = pendingFeature;
      pendingFeature = null;
      uploadFiles(incoming)
        .then(uploaded => submitTask(feature.prompt.replaceAll('{path}', uploaded[0].path), uploaded))
        .catch(error => appendMessage('error', `文件功能执行失败：${error.message}`));
      return;
    }
    selectedFiles = selectedFiles.concat(incoming);
    renderFilePreviews();
    fileInput.value = '';
  }, true);

  const dropZone = document.getElementById('drop-zone');
  dropZone.addEventListener('drop', event => {
    event.stopImmediatePropagation();
    const incoming = Array.from(event.dataTransfer.files || []);
    if (!incoming.length) return;
    selectedFiles = selectedFiles.concat(incoming);
    renderFilePreviews();
  }, true);

  if (skillSaveButton) {
    skillSaveButton.removeAttribute('onclick');
    skillSaveButton.addEventListener('click', saveSkill);
  }
  if (meetingToggleButton) meetingToggleButton.addEventListener('click', toggleMeeting);
  if (meetingCollapseButton) {
    meetingCollapseButton.addEventListener('click', () => {
      meetingCollapsed = !meetingCollapsed;
      localStorage.setItem('agentMeetingCollapsed', meetingCollapsed ? '1' : '0');
      applyMeetingCollapsed();
    });
  }
  if (voiceInputButton) voiceInputButton.addEventListener('click', toggleVoiceInput);
  if (modelSelect) modelSelect.addEventListener('change', event => switchModel(event.target.value));
  if (refreshContextsButton) refreshContextsButton.addEventListener('click', () => {
    loadActiveContext();
    loadContexts();
  });

  applyResponsiveDensity();
  window.addEventListener('resize', applyResponsiveDensity);
  window.addEventListener('orientationchange', applyResponsiveDensity);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', applyResponsiveDensity);
  }

  loadTasks();
  loadFeatures();
  loadSkill();
  loadModels();
  loadActiveContext();
  loadContexts();
  applyMeetingCollapsed();
  refreshMeetingStatus();
  refreshSystemStatus();
  setInterval(refreshMeetingStatus, 1000);
  setInterval(refreshVoiceInputStatus, 1000);
  setInterval(refreshSystemStatus, 3000);
})();

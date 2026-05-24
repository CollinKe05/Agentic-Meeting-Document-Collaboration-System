(function () {
  const inputElement = document.getElementById('prompt-input');
  const chatMessages = document.getElementById('chat-messages');
  const fileInput = document.getElementById('file-input');
  const filePreviewArea = document.getElementById('file-preview-area');
  const thoughtProcessPanel = document.getElementById('agent-thought-process');
  const thoughtStepsContainer = document.getElementById('thought-steps');
  const taskList = document.getElementById('task-list');
  const sendButton = document.getElementById('send-btn');
  const skillEditor = document.querySelector('textarea[placeholder^="在此定义Agent技能"]');
  const skillSaveButton = document.getElementById('save-skill-button') || document.querySelector('button[onclick*="已保存技能配置"]');
  const featuresPanel = document.querySelector('main > aside:last-child .p-3.overflow-y-auto');

  let selectedFiles = [];
  let pendingFeature = null;
  let activeEventSource = null;
  let currentSkillName = 'ui_skill.md';
  let currentTaskDoneShown = false;

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

  function addThoughtStep(event) {
    if (!thoughtProcessPanel || !thoughtStepsContainer) return;
    thoughtProcessPanel.classList.remove('hidden');
    const step = document.createElement('div');
    step.className = 'flex items-start gap-2 animate-fade-in-up';
    const isError = event.type === 'ERROR';
    step.innerHTML = `
      <div class="mt-0.5 shrink-0">${iconSvg(isError ? 'x' : 'ok', `w-4 h-4 ${isError ? 'text-red-500' : 'text-indigo-500'}`)}</div>
      <span class="text-gray-600"><strong>${escapeHtml(event.title || event.type)}</strong>${event.message ? `：${escapeHtml(event.message)}` : ''}</span>
    `;
    thoughtStepsContainer.appendChild(step);
    thoughtProcessPanel.scrollTop = thoughtProcessPanel.scrollHeight;
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
      if (data.type === 'TASK_DONE') {
        currentTaskDoneShown = true;
        appendMessage('agent', data.message || '任务完成。');
        setSendBusy(false);
        loadTasks();
      }
      if (data.type === 'ERROR') {
        appendMessage('error', data.message || '任务失败。');
        setSendBusy(false);
        loadTasks();
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
      file_parse: { prompt: '请读取并解析本地文件 {path}，提取关键信息。', needsFile: true },
      code_review: { prompt: '请读取代码文件 {path}，做一次代码 Review。', needsFile: true }
    };
    pendingFeature = fallback[type] || fallback.file_parse;
    fileInput.click();
  };

  fileInput.addEventListener('change', event => {
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
  }, true);

  const dropZone = document.getElementById('drop-zone');
  dropZone.addEventListener('drop', event => {
    const incoming = Array.from(event.dataTransfer.files || []);
    if (!incoming.length) return;
    selectedFiles = selectedFiles.concat(incoming);
    renderFilePreviews();
  });

  if (skillSaveButton) {
    skillSaveButton.removeAttribute('onclick');
    skillSaveButton.addEventListener('click', saveSkill);
  }

  loadTasks();
  loadFeatures();
  loadSkill();
})();

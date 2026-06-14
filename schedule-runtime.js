(function () {
  const API_URL = '/api/todo/tasks';
  const FILE_PREVIEW = window.location.protocol === 'file:';
  document.querySelectorAll('[data-agent-home]').forEach(link => {
    link.href = FILE_PREVIEW ? 'index.html' : '/';
  });
  const state = {
    tasks: [],
    selectedDate: dateKey(new Date()),
    calendarDate: new Date(),
    editingId: null,
    viewMode: localStorage.getItem('scheduleViewMode') || 'day'
  };

  const el = {
    calendarTitle: document.getElementById('calendar-title'),
    calendarDays: document.getElementById('calendar-days'),
    calendarPrev: document.getElementById('calendar-prev'),
    calendarNext: document.getElementById('calendar-next'),
    todoContainer: document.getElementById('todo-container'),
    todoCount: document.getElementById('todo-count'),
    scheduleContainer: document.getElementById('schedule-container'),
    scheduleHeading: document.getElementById('schedule-heading'),
    scheduleDateLabel: document.getElementById('schedule-date-label'),
    calendarView: document.getElementById('calendar-view'),
    viewButtons: Array.from(document.querySelectorAll('.view-mode-btn')),
    refresh: document.getElementById('refresh-schedule'),
    clock: document.getElementById('schedule-clock'),
    themeToggle: document.getElementById('theme-toggle'),
    fullscreenToggle: document.getElementById('fullscreen-toggle'),
    agentInput: document.getElementById('agent-command-input'),
    sendAgent: document.getElementById('send-agent-command'),
    title: document.getElementById('task-title'),
    type: document.getElementById('task-type'),
    date: document.getElementById('task-date'),
    clearDate: document.getElementById('clear-task-date'),
    startTime: document.getElementById('task-start-time'),
    endTime: document.getElementById('task-end-time'),
    priority: document.getElementById('task-priority'),
    category: document.getElementById('task-category'),
    description: document.getElementById('task-description'),
    save: document.getElementById('save-task'),
    cancel: document.getElementById('cancel-edit'),
    toastContainer: document.getElementById('toast-container')
  };

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function dateKey(date) {
    return [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0')
    ].join('-');
  }

  function parseTaskDate(task) {
    const match = String(task.due_date || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (!match) return null;
    return {
      key: `${match[1]}-${match[2]}-${match[3]}`,
      time: match[4] ? `${match[4]}:${match[5]}` : '',
      date: new Date(+match[1], +match[2] - 1, +match[3], +(match[4] || 0), +(match[5] || 0))
    };
  }

  function normalizePriority(priority) {
    const value = String(priority || '').trim();
    if (value === '高' || value.toLowerCase() === 'high') return '高';
    if (value === '低' || value.toLowerCase() === 'low') return '低';
    return '中';
  }

  function priorityClasses(priority) {
    const value = normalizePriority(priority);
    if (value === '高') return {
      text: 'text-red-600',
      dot: 'bg-red-500',
      badge: 'border-red-100 bg-red-50 text-red-600'
    };
    if (value === '低') return {
      text: 'text-emerald-600',
      dot: 'bg-emerald-500',
      badge: 'border-emerald-100 bg-emerald-50 text-emerald-600'
    };
    return {
      text: 'text-blue-600',
      dot: 'bg-blue-500',
      badge: 'border-blue-100 bg-blue-50 text-blue-600'
    };
  }

  function toast(message, type = 'success') {
    const item = document.createElement('div');
    const border = type === 'error' ? 'border-red-500' : type === 'agent' ? 'border-blue-500' : 'border-emerald-500';
    item.className = `rounded-lg border-l-4 ${border} bg-gray-900 px-4 py-3 text-xs text-white shadow-xl`;
    item.textContent = message;
    el.toastContainer.appendChild(item);
    setTimeout(() => item.remove(), 3500);
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || payload.message || `请求失败 (${response.status})`);
    }
    return payload;
  }

  async function loadTasks(quiet = false) {
    if (!quiet) {
      el.scheduleContainer.innerHTML = '<p class="py-16 text-center text-sm text-gray-400">正在加载日程...</p>';
    }
    try {
      const payload = await request(`${API_URL}?limit=1000`);
      state.tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
      render();
    } catch (error) {
      el.scheduleContainer.innerHTML = `<p class="py-16 text-center text-sm text-red-500">${escapeHtml(error.message)}</p>`;
      toast(error.message, 'error');
    }
  }

  function render() {
    renderCalendar();
    renderTodos();
    renderMainView();
  }

  function renderCalendar() {
    const year = state.calendarDate.getFullYear();
    const month = state.calendarDate.getMonth();
    el.calendarTitle.textContent = `${year} 年 ${month + 1} 月`;

    const first = new Date(year, month, 1);
    const start = new Date(year, month, 1 - ((first.getDay() + 6) % 7));
    const taskDates = new Set(
      state.tasks.filter(task => !task.completed).map(task => parseTaskDate(task)?.key).filter(Boolean)
    );
    const today = dateKey(new Date());
    const cells = [];

    for (let index = 0; index < 42; index += 1) {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      const key = dateKey(date);
      const selected = key === state.selectedDate;
      const outside = date.getMonth() !== month;
      const classes = selected
        ? 'bg-blue-600 text-white font-semibold shadow-sm'
        : key === today
          ? 'bg-blue-50 text-blue-700 font-semibold'
          : outside
            ? 'text-gray-300 hover:bg-gray-50'
            : 'text-gray-700 hover:bg-gray-100';
      cells.push(`
        <button type="button" data-calendar-date="${key}" class="relative aspect-square rounded-full transition-colors ${classes}">
          ${date.getDate()}
          ${taskDates.has(key) && !selected ? '<span class="absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-red-500"></span>' : ''}
        </button>
      `);
    }
    el.calendarDays.innerHTML = cells.join('');
  }

  function renderTodos() {
    const incomplete = state.tasks.filter(task => !task.completed);
    const completed = state.tasks.filter(task => task.completed).slice(0, 8);
    const tasks = [...incomplete, ...completed];
    el.todoCount.textContent = `${incomplete.length} 项未完成`;

    if (!tasks.length) {
      el.todoContainer.innerHTML = '<p class="py-8 text-center text-xs text-gray-400">暂无待办事项</p>';
      return;
    }

    el.todoContainer.innerHTML = tasks.map(task => {
      const parsed = parseTaskDate(task);
      const info = parsed ? `${parsed.key} ${parsed.time}`.trim() : '未设置时间';
      const priority = normalizePriority(task.priority);
      return `
        <div class="group flex items-start gap-3 rounded-lg border border-gray-100 p-2.5 hover:bg-gray-50">
          <input data-action="toggle" data-task-id="${task.id}" type="checkbox" ${task.completed ? 'checked' : ''} class="mt-0.5 h-4 w-4 cursor-pointer rounded border-gray-300 text-blue-600">
          <button data-action="edit" data-task-id="${task.id}" class="min-w-0 flex-1 text-left">
            <p class="truncate text-xs font-medium ${task.completed ? 'text-gray-400 line-through' : 'text-gray-800'}">${escapeHtml(task.title)}</p>
            <p class="mt-1 text-[10px] text-gray-500">${escapeHtml(info)} · ${priority}优先级</p>
          </button>
          <button data-action="delete" data-task-id="${task.id}" class="h-6 w-6 rounded text-gray-300 opacity-0 hover:bg-red-50 hover:text-red-500 group-hover:opacity-100" title="删除">×</button>
        </div>
      `;
    }).join('');
  }

  function renderMainView() {
    el.viewButtons.forEach(button => {
      button.classList.toggle('view-tab-active', button.dataset.viewMode === state.viewMode);
    });
    localStorage.setItem('scheduleViewMode', state.viewMode);

    if (state.viewMode === 'day') {
      el.scheduleContainer.classList.remove('hidden');
      el.calendarView.classList.add('hidden');
      renderDayView();
      return;
    }

    el.scheduleContainer.classList.add('hidden');
    el.calendarView.classList.remove('hidden');
    if (state.viewMode === 'list') renderListView();
    if (state.viewMode === 'month') renderMonthView();
    if (state.viewMode === 'week') renderWeekView();
  }

  function renderDayView() {
    const selected = new Date(`${state.selectedDate}T00:00:00`);
    el.scheduleHeading.textContent = state.selectedDate === dateKey(new Date()) ? '今日日程' : '选中日期日程';
    el.scheduleDateLabel.textContent = selected.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      weekday: 'long'
    });

    const tasks = state.tasks
      .filter(task => parseTaskDate(task)?.key === state.selectedDate)
      .sort((a, b) => String(a.due_date || '').localeCompare(String(b.due_date || '')));

    if (!tasks.length) {
      el.scheduleContainer.innerHTML = `
        <div class="flex h-full min-h-64 flex-col items-center justify-center text-center">
          <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 text-blue-500">
            <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
            </svg>
          </div>
          <p class="text-sm font-medium text-gray-600">这一天还没有日程</p>
          <p class="mt-1 text-xs text-gray-400">可以在右侧手动添加，或让 Agent 帮你安排</p>
        </div>
      `;
      return;
    }

    el.scheduleContainer.innerHTML = tasks.map(task => {
      const parsed = parseTaskDate(task);
      const color = priorityClasses(task.priority);
      return `
        <div class="timeline-item flex gap-4 ${task.completed ? 'opacity-60' : ''}">
          <div class="w-14 shrink-0 pt-0.5 text-right">
            <p class="text-sm font-semibold ${color.text}">${escapeHtml(parsed?.time || '待定')}</p>
          </div>
          <div class="timeline-dot z-10 shrink-0 pt-1">
            <div class="h-3 w-3 rounded-full ${color.dot} ring-4 ring-white"></div>
          </div>
          <article class="surface min-w-0 flex-1 rounded-lg border border-gray-200 bg-white p-4 hover:shadow-sm">
            <div class="flex items-start justify-between gap-3">
              <button data-action="edit" data-task-id="${task.id}" class="min-w-0 flex-1 text-left">
                <h3 class="ink text-sm font-medium text-gray-800 ${task.completed ? 'line-through' : ''}">${escapeHtml(task.title)}</h3>
                ${task.description ? `<p class="muted mt-1 whitespace-pre-line text-xs text-gray-500">${escapeHtml(task.description)}</p>` : ''}
              </button>
              <span class="shrink-0 rounded-md border px-2 py-0.5 text-[10px] ${color.badge}">${escapeHtml(normalizePriority(task.priority))}</span>
            </div>
            <div class="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
              <span class="muted text-[10px] text-gray-400">${escapeHtml(task.category || '未分类')}</span>
              <div class="flex gap-3 text-[10px]">
                <button data-action="toggle" data-task-id="${task.id}" class="text-gray-400 hover:text-emerald-600">${task.completed ? '恢复' : '完成'}</button>
                <button data-action="delete" data-task-id="${task.id}" class="text-gray-400 hover:text-red-600">删除</button>
              </div>
            </div>
          </article>
        </div>
      `;
    }).join('');
  }

  function taskCard(task, compact) {
    const parsed = parseTaskDate(task);
    const color = priorityClasses(task.priority);
    const time = parsed ? `${parsed.key} ${parsed.time}`.trim() : '未设置时间';
    return `
      <article class="surface rounded-lg border border-gray-200 bg-white ${compact ? 'p-2.5' : 'p-4'} ${task.completed ? 'opacity-60' : ''}">
        <div class="flex items-start justify-between gap-3">
          <button data-action="edit" data-task-id="${task.id}" class="min-w-0 flex-1 text-left">
            <h3 class="ink ${compact ? 'text-xs' : 'text-sm'} font-medium text-gray-800 ${task.completed ? 'line-through' : ''}">${escapeHtml(task.title)}</h3>
            <p class="muted mt-1 text-[10px] text-gray-500">${escapeHtml(time)} · ${escapeHtml(task.category || '未分类')}</p>
            ${!compact && task.description ? `<p class="muted mt-2 whitespace-pre-line text-xs text-gray-500">${escapeHtml(task.description)}</p>` : ''}
          </button>
          <span class="shrink-0 rounded-md border px-2 py-0.5 text-[10px] ${color.badge}">${escapeHtml(normalizePriority(task.priority))}</span>
        </div>
        <div class="mt-3 flex justify-end gap-3 border-t border-gray-100 pt-3 text-[10px]">
          <button data-action="toggle" data-task-id="${task.id}" class="text-gray-400 hover:text-emerald-600">${task.completed ? '恢复' : '完成'}</button>
          <button data-action="delete" data-task-id="${task.id}" class="text-gray-400 hover:text-red-600">删除</button>
        </div>
      </article>
    `;
  }

  function renderListView() {
    el.scheduleHeading.textContent = '全部任务';
    el.scheduleDateLabel.textContent = `共 ${state.tasks.length} 项，集中查看日程与待办`;
    el.calendarView.innerHTML = state.tasks.length
      ? `<div class="grid grid-cols-1 gap-3 xl:grid-cols-2">${state.tasks.map(task => taskCard(task, false)).join('')}</div>`
      : '<p class="py-16 text-center text-sm text-gray-400">暂无任务</p>';
  }

  function renderMonthView() {
    const year = state.calendarDate.getFullYear();
    const month = state.calendarDate.getMonth();
    const first = new Date(year, month, 1);
    const start = new Date(year, month, 1 - ((first.getDay() + 6) % 7));
    el.scheduleHeading.textContent = '月视图';
    el.scheduleDateLabel.textContent = `${year} 年 ${month + 1} 月`;

    const cells = [];
    for (let index = 0; index < 42; index += 1) {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      const key = dateKey(date);
      const tasks = state.tasks.filter(task => parseTaskDate(task)?.key === key);
      cells.push(`
        <button data-calendar-date="${key}" class="surface min-h-24 border-b border-r border-gray-100 p-2 text-left hover:bg-blue-50 ${date.getMonth() !== month ? 'bg-gray-50 text-gray-300' : 'bg-white'}">
          <span class="text-xs font-medium ${key === state.selectedDate ? 'text-blue-600' : ''}">${date.getDate()}</span>
          <span class="mt-2 block space-y-1">
            ${tasks.slice(0, 3).map(task => `<span class="block truncate rounded bg-gray-100 px-1.5 py-1 text-[10px] text-gray-600">${escapeHtml(task.title)}</span>`).join('')}
            ${tasks.length > 3 ? `<span class="block text-[10px] text-gray-400">还有 ${tasks.length - 3} 项</span>` : ''}
          </span>
        </button>
      `);
    }

    el.calendarView.innerHTML = `
      <div class="grid grid-cols-7 border-l border-t border-gray-100 text-center text-xs text-gray-400">
        ${['一', '二', '三', '四', '五', '六', '日'].map(day => `<div class="border-b border-r border-gray-100 py-2">${day}</div>`).join('')}
      </div>
      <div class="grid grid-cols-7 border-l border-gray-100">${cells.join('')}</div>
    `;
  }

  function renderWeekView() {
    const selected = new Date(`${state.selectedDate}T00:00:00`);
    const start = new Date(selected);
    start.setDate(selected.getDate() - ((selected.getDay() + 6) % 7));
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    el.scheduleHeading.textContent = '周视图';
    el.scheduleDateLabel.textContent = `${start.toLocaleDateString('zh-CN')} - ${end.toLocaleDateString('zh-CN')}`;

    const columns = [];
    for (let index = 0; index < 7; index += 1) {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      const key = dateKey(date);
      const tasks = state.tasks.filter(task => parseTaskDate(task)?.key === key);
      columns.push(`
        <section class="surface-muted min-w-0 rounded-lg border border-gray-200 bg-gray-50 p-2">
          <button data-calendar-date="${key}" class="surface mb-2 w-full rounded-lg py-2 text-center text-xs font-medium ${key === state.selectedDate ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'}">
            ${date.toLocaleDateString('zh-CN', { weekday: 'short', month: 'numeric', day: 'numeric' })}
          </button>
          <div class="space-y-2">${tasks.length ? tasks.map(task => taskCard(task, true)).join('') : '<p class="py-6 text-center text-[10px] text-gray-400">无日程</p>'}</div>
        </section>
      `);
    }
    el.calendarView.innerHTML = `<div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-7">${columns.join('')}</div>`;
  }

  function resetForm() {
    state.editingId = null;
    el.title.value = '';
    el.type.value = 'schedule';
    el.date.value = state.selectedDate;
    el.startTime.value = '';
    el.endTime.value = '';
    el.priority.value = '中';
    el.category.value = '';
    el.description.value = '';
    el.save.textContent = '添加日程';
    el.cancel.classList.add('hidden');
  }

  function startEdit(taskId) {
    const task = state.tasks.find(item => String(item.id) === String(taskId));
    if (!task) return;
    const parsed = parseTaskDate(task);
    state.editingId = task.id;
    el.title.value = task.title || '';
    el.type.value = task.category === '待办' || !parsed ? 'todo' : 'schedule';
    el.date.value = parsed?.key || '';
    el.startTime.value = parsed?.time || '';
    el.endTime.value = '';
    el.priority.value = normalizePriority(task.priority);
    el.category.value = task.category || '';
    el.description.value = task.description || '';
    el.save.textContent = '保存修改';
    el.cancel.classList.remove('hidden');
    el.title.focus();
  }

  async function saveTask() {
    if (FILE_PREVIEW) {
      toast('当前是本地预览模式，请启动 Agent UI 后再添加日程', 'agent');
      return;
    }
    const title = el.title.value.trim();
    if (!title) {
      toast('请填写标题', 'error');
      el.title.focus();
      return;
    }

    const date = el.date.value;
    const time = el.startTime.value;
    if (el.type.value === 'schedule' && (!date || !time)) {
      toast('日程需要填写日期和开始时间', 'error');
      return;
    }

    let description = el.description.value.trim();
    if (el.endTime.value && !description.includes(`结束时间：${el.endTime.value}`)) {
      description += `${description ? '\n' : ''}结束时间：${el.endTime.value}`;
    }

    const body = {
      title,
      description,
      priority: normalizePriority(el.priority.value),
      category: el.category.value.trim() || (el.type.value === 'todo' ? '待办' : '日程'),
      due_date: date ? `${date} ${time || '12:00'}:00` : null
    };
    const editingId = state.editingId;

    try {
      await request(editingId ? `${API_URL}/${editingId}` : API_URL, {
        method: editingId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      toast(editingId ? '日程已更新' : '日程已添加');
      resetForm();
      await loadTasks(true);
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function toggleTask(taskId) {
    const task = state.tasks.find(item => String(item.id) === String(taskId));
    if (!task) return;
    try {
      await request(`${API_URL}/${task.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completed: !task.completed })
      });
      await loadTasks(true);
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function deleteTask(taskId) {
    const task = state.tasks.find(item => String(item.id) === String(taskId));
    if (!task || !window.confirm(`确定删除“${task.title}”吗？`)) return;
    try {
      await request(`${API_URL}/${task.id}`, { method: 'DELETE' });
      if (String(state.editingId) === String(task.id)) resetForm();
      toast('日程已删除');
      await loadTasks(true);
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function sendAgentInstruction() {
    if (FILE_PREVIEW) {
      toast('当前是本地预览模式，请通过 Agent UI 使用日程联动', 'agent');
      return;
    }
    const prompt = el.agentInput.value.trim();
    if (!prompt) return;
    el.agentInput.disabled = true;
    el.sendAgent.disabled = true;
    toast('Agent 正在处理日程指令', 'agent');
    try {
      const payload = await request('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt })
      });
      el.agentInput.value = '';
      toast(payload.response || 'Agent 已处理完成', 'agent');
      await loadTasks(true);
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      el.agentInput.disabled = false;
      el.sendAgent.disabled = false;
      el.agentInput.focus();
    }
  }

  function handleTaskAction(event) {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    if (target.dataset.action === 'edit') startEdit(target.dataset.taskId);
    if (target.dataset.action === 'toggle') toggleTask(target.dataset.taskId);
    if (target.dataset.action === 'delete') deleteTask(target.dataset.taskId);
  }

  function selectCalendarDate(key) {
    state.selectedDate = key;
    const selected = new Date(`${key}T00:00:00`);
    state.calendarDate = new Date(selected.getFullYear(), selected.getMonth(), 1);
    el.date.value = key;
    render();
  }

  function applyTheme(theme) {
    const dark = theme === 'dark';
    document.body.classList.toggle('dark-theme', dark);
    localStorage.setItem('scheduleTheme', dark ? 'dark' : 'light');
    el.themeToggle.title = dark ? '切换浅色主题' : '切换深色主题';
  }

  function updateClock() {
    el.clock.textContent = new Date().toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await document.documentElement.requestFullscreen();
      }
    } catch (error) {
      toast(`全屏切换失败：${error.message}`, 'error');
    }
  }

  window.agentApiInsertSchedule = async function (data) {
    await request(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: data.title,
        description: data.desc || '',
        priority: normalizePriority(data.priority),
        category: data.tag || '日程',
        due_date: `${data.date || state.selectedDate} ${data.time || '12:00'}:00`
      })
    });
    await loadTasks(true);
  };

  window.agentApiInsertTodo = async function (data) {
    await request(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: data.title,
        description: data.info || '',
        priority: normalizePriority(data.priority),
        category: '待办',
        due_date: data.due_date || null
      })
    });
    await loadTasks(true);
  };

  el.calendarPrev.addEventListener('click', () => {
    if (state.viewMode === 'week' || state.viewMode === 'day') {
      const selected = new Date(`${state.selectedDate}T00:00:00`);
      selected.setDate(selected.getDate() - (state.viewMode === 'week' ? 7 : 1));
      selectCalendarDate(dateKey(selected));
      return;
    }
    state.calendarDate = new Date(state.calendarDate.getFullYear(), state.calendarDate.getMonth() - 1, 1);
    render();
  });

  el.calendarNext.addEventListener('click', () => {
    if (state.viewMode === 'week' || state.viewMode === 'day') {
      const selected = new Date(`${state.selectedDate}T00:00:00`);
      selected.setDate(selected.getDate() + (state.viewMode === 'week' ? 7 : 1));
      selectCalendarDate(dateKey(selected));
      return;
    }
    state.calendarDate = new Date(state.calendarDate.getFullYear(), state.calendarDate.getMonth() + 1, 1);
    render();
  });

  el.calendarDays.addEventListener('click', event => {
    const button = event.target.closest('[data-calendar-date]');
    if (button) selectCalendarDate(button.dataset.calendarDate);
  });

  el.todoContainer.addEventListener('click', handleTaskAction);
  el.scheduleContainer.addEventListener('click', handleTaskAction);
  el.calendarView.addEventListener('click', event => {
    handleTaskAction(event);
    const dateButton = event.target.closest('[data-calendar-date]');
    if (dateButton && !event.target.closest('[data-action]')) {
      selectCalendarDate(dateButton.dataset.calendarDate);
    }
  });

  el.viewButtons.forEach(button => {
    button.addEventListener('click', () => {
      state.viewMode = button.dataset.viewMode;
      renderMainView();
    });
  });

  document.querySelectorAll('[data-agent-example]').forEach(button => {
    button.addEventListener('click', () => {
      el.agentInput.value = button.dataset.agentExample;
      el.agentInput.focus();
    });
  });

  el.refresh.addEventListener('click', () => loadTasks(false));
  el.save.addEventListener('click', saveTask);
  el.cancel.addEventListener('click', resetForm);
  el.clearDate.addEventListener('click', () => {
    el.date.value = '';
    el.startTime.value = '';
    el.endTime.value = '';
  });
  el.themeToggle.addEventListener('click', () => {
    applyTheme(document.body.classList.contains('dark-theme') ? 'light' : 'dark');
  });
  el.fullscreenToggle.addEventListener('click', toggleFullscreen);
  el.sendAgent.addEventListener('click', sendAgentInstruction);
  el.agentInput.addEventListener('keydown', event => {
    if (event.key === 'Enter') sendAgentInstruction();
  });

  applyTheme(localStorage.getItem('scheduleTheme') === 'dark' ? 'dark' : 'light');
  updateClock();
  setInterval(updateClock, 1000);
  resetForm();
  if (FILE_PREVIEW) {
    state.tasks = [];
    render();
    toast('当前为界面预览；启动 Agent UI 后可读写真实日程', 'agent');
  } else {
    loadTasks(false);
  }
})();

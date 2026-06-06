document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const clockElement = document.getElementById('clock'); // Added clock element
    const taskListUl = document.getElementById('task-list');
    const taskForm = document.getElementById('task-form');
    const formTitle = document.getElementById('form-title');
    const taskIdInput = document.getElementById('task-id');
    const taskTitleInput = document.getElementById('task-title');
    const taskDescriptionInput = document.getElementById('task-description');
    const taskPriorityInput = document.getElementById('task-priority');
    const taskCategoryInput = document.getElementById('task-category');
    const taskDueDateInput = document.getElementById('task-due-date');
    const saveTaskBtn = document.getElementById('save-task-btn');
    // 重新获取所有动态插入的按钮
    const showFormBtn = document.getElementById('show-form-btn');
    const closeFormBtn = document.getElementById('close-form-btn');
    const taskFormSection = document.getElementById('task-form-section');
    const cancelEditBtn = document.getElementById('cancel-edit-btn');
    const taskListContainer = document.getElementById('task-list-container'); // Added
    const calendarViewContainer = document.getElementById('calendar-view-container'); // Added
    const showListBtn = document.getElementById('show-list-btn'); // Added
    const showCalendarBtn = document.getElementById('show-calendar-btn'); // Added
    const calendarMonthBtn = document.getElementById('calendar-month-btn'); // Added
    const calendarWeekBtn = document.getElementById('calendar-week-btn'); // Added
    const calendarDayBtn = document.getElementById('calendar-day-btn'); // Added
    const calendarGrid = document.getElementById('calendar-grid'); // Added
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const fullscreenBtn = document.getElementById('fullscreen-btn'); // 全屏按钮
    const exitFullscreenBtn = document.getElementById('exit-fullscreen-btn'); // 退出全屏按钮
    const refreshBtn = document.getElementById('refresh-btn'); // 刷新按钮
    const THEME_STORAGE_KEY = 'todoTheme';

    function applyTheme(theme) {
        if (theme === 'dark') {
            document.body.classList.add('dark-theme');
            themeToggleBtn.textContent = '浅色主题';
        } else {
            document.body.classList.remove('dark-theme');
            themeToggleBtn.textContent = '深色主题';
        }
    }

    function toggleTheme() {
        const currentTheme = document.body.classList.contains('dark-theme') ? 'dark' : 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
        try {
            localStorage.setItem(THEME_STORAGE_KEY, newTheme);
        } catch (e) {
            console.warn('无法保存主题偏好:', e);
        }
    }

    function loadThemePreference() {
        let preferredTheme = 'light';
        try {
            const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
            if (storedTheme === 'dark') {
                preferredTheme = 'dark';
            }
        } catch (e) {
            console.warn('无法读取主题偏好:', e);
        }
        applyTheme(preferredTheme);
    }

    const API_BASE_URL = '/api'; // Relative URL

    // --- State ---
    let editingTaskId = null; // null when adding, task ID when editing
    let currentView = 'list'; // 'list' or 'calendar'
    let calendarDisplayMode = 'month'; // 'month', 'week', 'day'
    let allTasks = []; // Store all tasks

    // --- Utility Functions ---
    const formatDateForInput = (isoString) => {
        if (!isoString) return '';
        // SQLite stores 'YYYY-MM-DD HH:MM:SS'
        // datetime-local input needs 'YYYY-MM-DDTHH:MM'
        try {
            // 直接处理字符串，避免时区转换
            const parts = isoString.split(' ');
            if (parts.length >= 2) {
                const datePart = parts[0]; // YYYY-MM-DD
                const timePart = parts[1].substring(0, 5); // HH:MM (去掉秒)
                return `${datePart}T${timePart}`;
            }
            return '';
        } catch (e) {
            console.error("Error parsing date:", isoString, e);
            return ''; // Return empty if parsing fails
        }
    };

    const formatDateForDisplay = (isoString) => {
         if (!isoString) return '无';
         try {
             // 直接处理字符串而不是转换日期对象，避免时区问题
             const parts = isoString.split(' ');
             if (parts.length >= 2) {
                const datePart = parts[0]; // YYYY-MM-DD
                const timePart = parts[1].substring(0, 5); // HH:MM (去掉秒)
                
                // 格式化日期部分
                const dateParts = datePart.split('-');
                const year = dateParts[0];
                const month = dateParts[1];
                const day = dateParts[2];
                
                return `${year}/${month}/${day} ${timePart}`;
             }
             return isoString; // 如果无法解析，则返回原始字符串
         } catch (e) {
             console.error("Error formatting display date:", isoString, e);
             return '无效日期';
         }
     };

    const formatDateForStorage = (inputString) => {
        if (!inputString) return null;
        // Input is 'YYYY-MM-DDTHH:MM'
        // Convert to 'YYYY-MM-DD HH:MM:SS' for SQLite
        // 不添加Z，不做时区转换，直接使用本地时间
        return inputString.replace('T', ' ') + ':00';
    };

    // --- Clock Function ---
    function updateClock() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('zh-CN');
        const dateString = now.toLocaleDateString('zh-CN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        if (clockElement) {
            clockElement.textContent = `${dateString} ${timeString}`;
        }
    }


    // --- API Call Functions ---
    const apiCall = async (url, method = 'GET', body = null) => {
        const options = {
            method,
            headers: {},
        };
        if (body) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }

        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
                console.error(`HTTP error! status: ${response.status}`, errorData);
                throw new Error(errorData.message || `Request failed with status ${response.status}`);
            }
             // Handle empty response body for methods like DELETE or PUT
             if (response.status === 204 || method === 'DELETE' || method === 'PUT') {
                 return { success: true }; // Or specific success message if available
             }
            return await response.json();
        } catch (error) {
            console.error(`API call failed: ${method} ${url}`, error);
            alert(`操作失败: ${error.message}`);
            throw error; // Re-throw to handle in calling function if needed
        }
    };

    // --- Core Logic Functions ---
    async function fetchTasks() {
        console.log("START fetchTasks"); // Add log
        // Add placeholder to task list while fetching
        taskListUl.innerHTML = '<li class="task-item placeholder">加载任务中...</li>';
        // Clear calendar grid or show loading state if calendar is visible
        if (currentView === 'calendar') {
             calendarGrid.innerHTML = '<p class="placeholder">加载任务数据...</p>';
        }
        try {
            allTasks = await apiCall(`${API_BASE_URL}/tasks`);
            console.log(`fetchTasks successful, ${allTasks.length} tasks loaded.`); // Add log
            renderTasks(allTasks); // Render list view
            if (currentView === 'calendar') {
                console.log("Calendar is current view, calling renderCalendar from fetchTasks."); // Add log
                renderCalendar();
            }
        } catch (error) {
            console.error("fetchTasks failed:", error); // Log error
            taskListUl.innerHTML = '<li class="task-item error">无法加载任务列表</li>';
            allTasks = [];
             if (currentView === 'calendar') {
                 // Render calendar structure but indicate error?
                 calendarGrid.innerHTML = '<p class="error">无法加载任务数据以显示日历。</p>'; // Show error in calendar
             }
        } finally {
             console.log("END fetchTasks"); // Add log
        }
    }

    function renderTasks(tasks) {
        taskListUl.innerHTML = ''; // Clear list
        if (!tasks || tasks.length === 0) {
            taskListUl.innerHTML = '<li class="task-item placeholder">暂无任务</li>';
            return;
        }

        tasks.forEach(task => {
            const li = document.createElement('li');
            li.classList.add('task-item');
            li.classList.add(`priority-${task.priority}`);
            if (task.completed) {
                li.classList.add('completed');
            }
            li.dataset.taskId = task.id;

            const dueDateDisplay = formatDateForDisplay(task.due_date);
            const createdAtDisplay = formatDateForDisplay(task.created_at);

            li.innerHTML = `
                <div class="task-details">
                    <strong>${escapeHTML(task.title)}</strong>
                    ${task.description ? `<p><small>${escapeHTML(task.description)}</small></p>` : ''}
                    <small>
                        优先级: ${escapeHTML(task.priority)} |
                        分类: ${escapeHTML(task.category || '无')} |
                        截止: ${escapeHTML(dueDateDisplay)} |
                        创建于: ${escapeHTML(createdAtDisplay)}
                    </small>
                </div>
                <div class="task-actions">
                    <button class="complete-btn" title="${task.completed ? '标记为未完成' : '标记为完成'}">${task.completed ? '撤销' : '完成'}</button>
                    <button class="edit-btn" title="编辑任务">编辑</button>
                    <button class="delete-btn" title="删除任务">删除</button>
                </div>
            `;

            // Add event listeners using event delegation on the parent ul
            taskListUl.appendChild(li);
        });
    }

    // --- Calendar Rendering ---
    function renderCalendar() {
        if (calendarDisplayMode === 'month') {
            prevMonthBtn.textContent = '上个月';
            nextMonthBtn.textContent = '下个月';
            renderMonthView();
        } else if (calendarDisplayMode === 'week') {
            prevMonthBtn.textContent = '上一周';
            nextMonthBtn.textContent = '下一周';
            renderWeekView();
        } else if (calendarDisplayMode === 'day') {
            prevMonthBtn.textContent = '前一天';
            nextMonthBtn.textContent = '后一天';
            renderDayView();
        }
        [calendarMonthBtn, calendarWeekBtn, calendarDayBtn].forEach(btn => {
            btn.classList.remove('active');
        });
        if (calendarDisplayMode === 'month') calendarMonthBtn.classList.add('active');
        else if (calendarDisplayMode === 'week') calendarWeekBtn.classList.add('active');
        else if (calendarDisplayMode === 'day') calendarDayBtn.classList.add('active');
    }

    // 月份切换按钮支持
const prevMonthBtn = document.createElement('button');
prevMonthBtn.textContent = '上个月';
const nextMonthBtn = document.createElement('button');
nextMonthBtn.textContent = '下个月';
const calendarHeader = document.createElement('div');
calendarHeader.className = 'calendar-header';
calendarHeader.appendChild(prevMonthBtn);
const calendarTitle = document.createElement('span');
calendarTitle.id = 'calendar-title';
calendarHeader.appendChild(calendarTitle);
calendarHeader.appendChild(nextMonthBtn);

// 在renderMonthView中插入header
function renderMonthView() {
    calendarGrid.innerHTML = '';
    calendarGrid.appendChild(calendarHeader);
    const year = window.calendarCurrentDate ? window.calendarCurrentDate.getFullYear() : new Date().getFullYear();
    const month = window.calendarCurrentDate ? window.calendarCurrentDate.getMonth() : new Date().getMonth();
    // 用于今天定位，直接获取当前系统日期
    const today = new Date();
    today.setHours(0,0,0,0); // 避免时区误差
    calendarTitle.textContent = `${year}年${month + 1}月`;
    const todayInfo = document.createElement('div');
    todayInfo.className = 'calendar-today-info';
    todayInfo.innerHTML = `<span class="today-dot"></span> 今天：${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日`;
    calendarGrid.appendChild(todayInfo);
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startDay = firstDay.getDay();
    const daysInMonth = lastDay.getDate();
    const daysOfWeek = ['日', '一', '二', '三', '四', '五', '六'];
    let html = '<table class="calendar-table"><thead><tr>';
    daysOfWeek.forEach(d => html += `<th>${d}</th>`);
    html += '</tr></thead><tbody><tr>';
    for (let i = 0; i < startDay; i++) html += '<td></td>';
    for (let day = 1; day <= daysInMonth; day++) {
        const date = new Date(year, month, day);
        date.setHours(0,0,0,0); // 避免时区误差
        
        // 使用本地日期字符串格式而不是ISO格式，避免时区转换问题
        const calendarYear = date.getFullYear();
        const calendarMonth = date.getMonth() + 1;
        const calendarDay = date.getDate();
        
        // 日历单元格的日期格式化为YYYY-MM-DD
        const dateStr = `${calendarYear}-${String(calendarMonth).padStart(2, '0')}-${String(calendarDay).padStart(2, '0')}`;
        
        const isToday = (date.getTime() === today.getTime());
        const nearTodayStrs = [
            new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1).toISOString().split('T')[0],
            new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1).toISOString().split('T')[0]
        ];
        
        // 修复时区问题：使用日期的本地部分进行比较，避免时区影响
        const tasks = allTasks.filter(t => {
            if (!t.due_date) return false;
            
            // 从任务的due_date字符串中提取日期部分
            const taskDateStr = t.due_date.split(' ')[0]; // 获取YYYY-MM-DD部分
            
            return taskDateStr === dateStr;
        });
        html += `<td class="${isToday ? 'today' : ''}" data-date="${dateStr}">`;
        html += `<div class="day-number">${day}${isToday ? '<span class=\'today-label\'>今天</span>' : ''}</div>`;
        tasks.forEach(task => {
            const isNearToday = nearTodayStrs.includes(dateStr) && !isToday;
            // 计算距今天数
            const diffDays = Math.floor((date - today) / (1000 * 60 * 60 * 24));
            let diffLabel = '';
            if (diffDays > 0) diffLabel = `（还有${diffDays}天）`;
            else if (diffDays < 0) diffLabel = `（已过去${-diffDays}天）`;
            html += `<div class="calendar-task priority-${task.priority}${task.completed ? ' completed' : ''}${isNearToday ? ' near-today' : ''}" title="${task.title}${diffLabel ? ' ' + diffLabel : ''}">${task.title}${diffLabel ? `<span class='diff-label'>${diffLabel}</span>` : ''}</div>`;
        });
        html += '</td>';
        if ((startDay + day) % 7 === 0 && day !== daysInMonth) html += '</tr><tr>';
    }
    const lastCell = (startDay + daysInMonth) % 7;
    if (lastCell !== 0) for (let i = lastCell; i < 7; i++) html += '<td></td>';
    html += '</tr></tbody></table>';
    const tableDiv = document.createElement('div');
    tableDiv.innerHTML = html;
    calendarGrid.appendChild(tableDiv.firstChild);
    // 任务点击弹窗显示详情和距今天数
    calendarGrid.querySelectorAll('.calendar-task').forEach(el => {
        el.onclick = function(e) {
            e.stopPropagation();
            const title = this.textContent.replace(/（.*?天）/, '');
            const diff = this.querySelector('.diff-label')?.textContent || '';
            alert(`任务：${title}\n${diff ? diff.replace(/[（）]/g, '') : ''}`);
        };
    });
}

// 月份切换事件
prevMonthBtn.onclick = () => {
    if (!window.calendarCurrentDate) window.calendarCurrentDate = new Date();
    if (calendarDisplayMode === 'month') {
        window.calendarCurrentDate.setMonth(window.calendarCurrentDate.getMonth() - 1);
    } else if (calendarDisplayMode === 'week') {
        window.calendarCurrentDate.setDate(window.calendarCurrentDate.getDate() - 7);
    } else if (calendarDisplayMode === 'day') {
        window.calendarCurrentDate.setDate(window.calendarCurrentDate.getDate() - 1);
    }
    renderCalendar();
};
nextMonthBtn.onclick = () => {
    if (!window.calendarCurrentDate) window.calendarCurrentDate = new Date();
    if (calendarDisplayMode === 'month') {
        window.calendarCurrentDate.setMonth(window.calendarCurrentDate.getMonth() + 1);
    } else if (calendarDisplayMode === 'week') {
        window.calendarCurrentDate.setDate(window.calendarCurrentDate.getDate() + 7);
    } else if (calendarDisplayMode === 'day') {
        window.calendarCurrentDate.setDate(window.calendarCurrentDate.getDate() + 1);
    }
    renderCalendar();
};

// 周视图和日视图基础实现
function renderWeekView() {
    calendarGrid.innerHTML = '';
    // header
    calendarGrid.appendChild(calendarHeader);
    // 计算当前周的起始日期（以周日为一周的第一天）
    const today = window.calendarCurrentDate ? new Date(window.calendarCurrentDate) : new Date();
    const weekStart = new Date(today);
    weekStart.setDate(today.getDate() - today.getDay());
    const daysOfWeek = ['日', '一', '二', '三', '四', '五', '六'];
    let html = '<table class="calendar-table"><thead><tr>';
    daysOfWeek.forEach(d => html += `<th>${d}</th>`);
    html += '</tr></thead><tbody><tr>';
    for (let i = 0; i < 7; i++) {
        const date = new Date(weekStart);
        date.setDate(weekStart.getDate() + i);
        
        // 使用本地日期字符串格式而不是ISO格式，避免时区转换问题
        const calendarYear = date.getFullYear();
        const calendarMonth = date.getMonth() + 1;
        const calendarDay = date.getDate();
        
        // 日历单元格的日期格式化为YYYY-MM-DD
        const dateStr = `${calendarYear}-${String(calendarMonth).padStart(2, '0')}-${String(calendarDay).padStart(2, '0')}`;
        
        // 检查是否是今天
        const nowDate = new Date();
        const isToday = (
            date.getDate() === nowDate.getDate() && 
            date.getMonth() === nowDate.getMonth() && 
            date.getFullYear() === nowDate.getFullYear()
        );
        
        // 修复时区问题：使用日期的本地部分进行比较，避免时区影响
        const tasks = allTasks.filter(t => {
            if (!t.due_date) return false;
            
            // 从任务的due_date字符串中提取日期部分
            const taskDateStr = t.due_date.split(' ')[0]; // 获取YYYY-MM-DD部分
            
            return taskDateStr === dateStr;
        });
        html += `<td class="${isToday ? 'today' : ''}">`;
        html += `<div class="day-number">${date.getMonth() + 1}/${date.getDate()}</div>`;
        tasks.forEach(task => {
            html += `<div class="calendar-task priority-${task.priority}${task.completed ? ' completed' : ''}">${task.title}</div>`;
        });
        html += '</td>';
    }
    html += '</tr></tbody></table>';
    const tableDiv = document.createElement('div');
    tableDiv.innerHTML = html;
    calendarGrid.appendChild(tableDiv.firstChild);
    // 设置标题
    calendarTitle.textContent = `${weekStart.getFullYear()}年${weekStart.getMonth() + 1}月第${getWeekNumber(today)}周`;
}

function getWeekNumber(date) {
    const firstDay = new Date(date.getFullYear(), 0, 1);
    const dayOfYear = ((date - firstDay + 86400000) / 86400000);
    return Math.ceil((dayOfYear + firstDay.getDay()) / 7);
}

function renderDayView() {
    calendarGrid.innerHTML = '';
    calendarGrid.appendChild(calendarHeader);
    const today = window.calendarCurrentDate ? new Date(window.calendarCurrentDate) : new Date();
    
    // 使用本地日期字符串格式而不是ISO格式，避免时区转换问题
    const calendarYear = today.getFullYear();
    const calendarMonth = today.getMonth() + 1;
    const calendarDay = today.getDate();
    
    // 日历单元格的日期格式化为YYYY-MM-DD
    const dateStr = `${calendarYear}-${String(calendarMonth).padStart(2, '0')}-${String(calendarDay).padStart(2, '0')}`;
    
    // 修复时区问题：使用日期的本地部分进行比较，避免时区影响
    const tasks = allTasks.filter(t => {
        if (!t.due_date) return false;
        
        // 从任务的due_date字符串中提取日期部分
        const taskDateStr = t.due_date.split(' ')[0]; // 获取YYYY-MM-DD部分
        
        return taskDateStr === dateStr;
    });
    
    let html = `<div class="day-view-title">${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日</div>`;
    if (tasks.length === 0) {
        html += '<div class="placeholder">今日暂无任务</div>';
    } else {
        html += '<ul class="day-task-list">';
        tasks.forEach(task => {
            html += `<li class="calendar-task priority-${task.priority}${task.completed ? ' completed' : ''}">${task.title}</li>`;
        });
        html += '</ul>';
    }
    const dayDiv = document.createElement('div');
    dayDiv.innerHTML = html;
    calendarGrid.appendChild(dayDiv);
    calendarTitle.textContent = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日`;
}

    // --- View Switching Logic ---
    function switchView(viewToShow) {
        currentView = viewToShow;
        // 隐藏所有主内容区
        document.querySelectorAll('.content-area > section').forEach(sec => sec.style.display = 'none');
        if (viewToShow === 'list') {
            document.getElementById('task-list-container').style.display = 'block';
            showListBtn.classList.add('active');
            showCalendarBtn.classList.remove('active');
        } else if (viewToShow === 'calendar') {
            document.getElementById('calendar-view-container').style.display = 'block';
            showListBtn.classList.remove('active');
            showCalendarBtn.classList.add('active');
            renderCalendar();
        }
    }

    // --- Form Submission, Toggle, Delete, Edit Functions ---
    async function handleFormSubmit(event) {
        event.preventDefault();
        const taskId = taskIdInput.value;
        const taskData = {
            title: taskTitleInput.value,
            description: taskDescriptionInput.value,
            priority: taskPriorityInput.value,
            category: taskCategoryInput.value,
            due_date: formatDateForStorage(taskDueDateInput.value),
        };

        if (editingTaskId) {
            // Editing existing task
            try {
                await apiCall(`${API_BASE_URL}/tasks/${editingTaskId}`, 'PUT', taskData);
                resetForm();
                fetchTasks();
            } catch (error) {
                console.error("Error updating task:", error);
            }
        } else {
            // Adding new task
            try {
                await apiCall(`${API_BASE_URL}/tasks`, 'POST', taskData);
                resetForm();
                fetchTasks();
            } catch (error) {
                console.error("Error adding task:", error);
            }
        }
    }

    function resetForm() {
        editingTaskId = null;
        formTitle.textContent = '添加新任务';
        taskForm.reset();
        saveTaskBtn.textContent = '添加任务';
    }

    function escapeHTML(html) {
        const text = document.createElement('textarea');
        text.textContent = html;
        return text.innerHTML;
    }

    // --- 全屏相关功能
    function enterFullscreen() {
        const docEl = document.documentElement;
        let fullscreenPromise;
        
        try {
            if (docEl.requestFullscreen) {
                fullscreenPromise = docEl.requestFullscreen();
            } else if (docEl.mozRequestFullScreen) { // Firefox
                fullscreenPromise = docEl.mozRequestFullScreen();
            } else if (docEl.webkitRequestFullscreen) { // Chrome, Safari, Opera
                fullscreenPromise = docEl.webkitRequestFullscreen();
            } else if (docEl.msRequestFullscreen) { // IE/Edge
                fullscreenPromise = docEl.msRequestFullscreen();
            }
            
            if (fullscreenPromise) {
                fullscreenPromise.then(() => {
                    fullscreenBtn.style.display = 'none';
                    exitFullscreenBtn.style.display = 'inline-block';
                    console.log("全屏模式已启用");
                }).catch(err => {
                    console.warn("进入全屏失败:", err);
                });
            } else {
                fullscreenBtn.style.display = 'none';
                exitFullscreenBtn.style.display = 'inline-block';
            }
        } catch (err) {
            console.warn("进入全屏出错:", err);
        }
    }
    
    function showFullscreenPrompt() {
        // 创建一个悬浮提示，引导用户点击全屏
        const prompt = document.createElement('div');
        prompt.className = 'fullscreen-prompt';
        prompt.innerHTML = '点击这里<span class="arrow">⬆</span>全屏显示';
        prompt.style.position = 'fixed';
        prompt.style.top = '60px';
        prompt.style.left = '50%';
        prompt.style.transform = 'translateX(-50%)';
        prompt.style.padding = '10px 15px';
        prompt.style.background = 'rgba(0, 123, 255, 0.9)';
        prompt.style.color = 'white';
        prompt.style.borderRadius = '5px';
        prompt.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        prompt.style.zIndex = '9999';
        prompt.style.animation = 'pulse 1.5s infinite';
        prompt.style.cursor = 'pointer';
        
        // 添加脉动动画
        const style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {
                0% { transform: translateX(-50%) scale(1); }
                50% { transform: translateX(-50%) scale(1.1); }
                100% { transform: translateX(-50%) scale(1); }
            }
            .fullscreen-prompt .arrow {
                display: inline-block;
                animation: bounce 1s infinite;
                margin-right: 5px;
            }
            @keyframes bounce {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-10px); }
            }
        `;
        document.head.appendChild(style);
        
        // 点击提示也会触发全屏
        prompt.addEventListener('click', () => {
            enterFullscreen();
            document.body.removeChild(prompt);
        });
        
        // 5秒后自动消失
        setTimeout(() => {
            if (document.body.contains(prompt)) {
                document.body.removeChild(prompt);
            }
        }, 5000);
        
        document.body.appendChild(prompt);
    }
    
    function exitFullscreen() {
        try {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.mozCancelFullScreen) { // Firefox
                document.mozCancelFullScreen();
            } else if (document.webkitExitFullscreen) { // Chrome, Safari, Opera
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) { // IE/Edge
                document.msExitFullscreen();
            }
        } catch (err) {
            console.warn("退出全屏出错:", err);
        } finally {
            fullscreenBtn.style.display = 'inline-block';
            exitFullscreenBtn.style.display = 'none';
        }
    }
    
    // 监听全屏状态变化
    document.addEventListener('fullscreenchange', updateFullscreenButtons);
    document.addEventListener('webkitfullscreenchange', updateFullscreenButtons);
    document.addEventListener('mozfullscreenchange', updateFullscreenButtons);
    document.addEventListener('MSFullscreenChange', updateFullscreenButtons);
    
    function updateFullscreenButtons() {
        if (document.fullscreenElement || 
            document.webkitFullscreenElement || 
            document.mozFullScreenElement ||
            document.msFullscreenElement) {
            fullscreenBtn.style.display = 'none';
            exitFullscreenBtn.style.display = 'inline-block';
        } else {
            fullscreenBtn.style.display = 'inline-block';
            exitFullscreenBtn.style.display = 'none';
        }
    }
    
    // 绑定全屏按钮事件
    fullscreenBtn.addEventListener('click', enterFullscreen);
    exitFullscreenBtn.addEventListener('click', exitFullscreen);

    // --- Event Listeners ---
    // 显示表单
    if (showFormBtn) {
        showFormBtn.onclick = () => {
            showFormBtn.style.display = 'none';
            taskFormSection.style.display = 'block';
            setTimeout(() => {
                const titleInput = document.getElementById('task-title');
                if (titleInput) titleInput.focus();
            }, 100);
        };
    }
    // 收起表单
    function hideTaskForm() {
        taskFormSection.style.display = 'none';
        showFormBtn.style.display = 'inline-block';
    }
    if (closeFormBtn) closeFormBtn.onclick = hideTaskForm;
    if (cancelEditBtn) cancelEditBtn.onclick = hideTaskForm;
    if (taskForm) {
        taskForm.addEventListener('submit', () => {
            setTimeout(hideTaskForm, 200);
        });
    }
    // 日期时间选择器相关元素
    const taskDueDateDate = document.getElementById('task-due-date-date');
    const taskDueDateTime = document.getElementById('task-due-date-time');
    const clearDateBtn = document.getElementById('clear-date-btn');

    // 合成日期时间到隐藏字段
    function updateCombinedDateTime() {
        if (taskDueDateDate && taskDueDateDate.value) {
            const dateValue = taskDueDateDate.value.trim(); // YYYY-MM-DD
            const timeValue = (taskDueDateTime && taskDueDateTime.value) ? taskDueDateTime.value.trim() : '12:00';
            
            // 验证日期格式
            const datePattern = /^\d{4}-\d{2}-\d{2}$/;
            const timePattern = /^\d{2}:\d{2}$/;
            
            if (datePattern.test(dateValue) && timePattern.test(timeValue)) {
                taskDueDateInput.value = `${dateValue}T${timeValue}`;
            } else {
                console.warn('日期或时间格式不符合要求', dateValue, timeValue);
                taskDueDateInput.value = '';
            }
        } else {
            taskDueDateInput.value = '';
        }
    }
    if (taskDueDateDate) taskDueDateDate.addEventListener('change', updateCombinedDateTime);
    if (taskDueDateDate) taskDueDateDate.addEventListener('blur', updateCombinedDateTime);
    if (taskDueDateTime) taskDueDateTime.addEventListener('change', updateCombinedDateTime);
    if (taskDueDateTime) taskDueDateTime.addEventListener('blur', updateCombinedDateTime);
    if (clearDateBtn) {
        clearDateBtn.addEventListener('click', () => {
            if (taskDueDateDate) taskDueDateDate.value = '';
            if (taskDueDateTime) taskDueDateTime.value = '12:00';
            taskDueDateInput.value = '';
        });
    }
    // 表单提交前合成
    if (taskForm) {
        taskForm.addEventListener('submit', updateCombinedDateTime);
    }
    // 创建自定义日期选择器
    function createCustomDatepicker() {
        // 创建日期选择器容器
        const datepickerContainer = document.createElement('div');
        datepickerContainer.className = 'datepicker-container';
        datepickerContainer.id = 'custom-datepicker';
        
        // 添加日期选择器标题和导航
        const header = document.createElement('div');
        header.className = 'datepicker-header';
        
        const monthYearDisplay = document.createElement('div');
        monthYearDisplay.className = 'datepicker-month-year';
        header.appendChild(monthYearDisplay);
        
        const nav = document.createElement('div');
        nav.className = 'datepicker-nav';
        
        const prevButton = document.createElement('button');
        prevButton.type = 'button';
        prevButton.innerHTML = '&lt;';
        prevButton.title = '上个月';
        nav.appendChild(prevButton);
        
        const nextButton = document.createElement('button');
        nextButton.type = 'button';
        nextButton.innerHTML = '&gt;';
        nextButton.title = '下个月';
        nav.appendChild(nextButton);
        
        header.appendChild(nav);
        datepickerContainer.appendChild(header);
        
        // 创建日历表格
        const calendar = document.createElement('table');
        calendar.className = 'datepicker-calendar';
        datepickerContainer.appendChild(calendar);
        
        // 添加底部确认按钮
        const footer = document.createElement('div');
        footer.className = 'datepicker-footer';
        
        const todayButton = document.createElement('button');
        todayButton.type = 'button';
        todayButton.textContent = '今天';
        todayButton.className = 'datepicker-today';
        footer.appendChild(todayButton);
        
        datepickerContainer.appendChild(footer);
        
        // 将日期选择器添加到body
        document.body.appendChild(datepickerContainer);
        
        // 日期选择器变量
        let currentDate = new Date();
        let currentMonth = currentDate.getMonth();
        let currentYear = currentDate.getFullYear();
        let selectedDate = null;
        
        // 更新日历显示
        function updateCalendar() {
            // 设置月份和年份显示
            const months = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'];
            monthYearDisplay.textContent = `${months[currentMonth]} ${currentYear}`;
            
            // 清空日历
            calendar.innerHTML = '';
            
            // 创建表头
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            
            ['日', '一', '二', '三', '四', '五', '六'].forEach(day => {
                const th = document.createElement('th');
                th.textContent = day;
                headerRow.appendChild(th);
            });
            
            thead.appendChild(headerRow);
            calendar.appendChild(thead);
            
            // 创建日历主体
            const tbody = document.createElement('tbody');
            
            // 获取当月第一天是星期几
            const firstDay = new Date(currentYear, currentMonth, 1);
            const startingDay = firstDay.getDay();
            
            // 获取当月天数
            const lastDay = new Date(currentYear, currentMonth + 1, 0);
            const monthLength = lastDay.getDate();
            
            // 获取上个月的最后几天
            const prevMonthLastDay = new Date(currentYear, currentMonth, 0);
            const prevMonthLength = prevMonthLastDay.getDate();
            
            // 今天日期，用于高亮显示
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            
            // 创建行和单元格
            let date = 1;
            let nextMonthDate = 1;
            
            for (let i = 0; i < 6; i++) {
                // 如果已经超过了当月天数，并且下个月的日期也超过了7天，就不再创建新行
                if (date > monthLength && nextMonthDate > 7) break;
                
                const row = document.createElement('tr');
                
                for (let j = 0; j < 7; j++) {
                    const cell = document.createElement('td');
                    
                    // 上个月的日期
                    if (i === 0 && j < startingDay) {
                        const prevDay = prevMonthLength - startingDay + j + 1;
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.textContent = prevDay;
                        btn.className = 'out-of-month';
                        
                        btn.dataset.date = `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(prevDay).padStart(2, '0')}`;
                        if (currentMonth === 0) {
                            btn.dataset.date = `${currentYear - 1}-12-${String(prevDay).padStart(2, '0')}`;
                        } else {
                            btn.dataset.date = `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(prevDay).padStart(2, '0')}`;
                        }
                        
                        cell.appendChild(btn);
                    }
                    // 当月的日期
                    else if (date <= monthLength) {
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.textContent = date;
                        
                        // 检查是否是今天
                        const currentDate = new Date(currentYear, currentMonth, date);
                        currentDate.setHours(0, 0, 0, 0);
                        
                        if (currentDate.getTime() === today.getTime()) {
                            btn.classList.add('today');
                        }
                        
                        // 检查是否是选中日期
                        if (selectedDate && 
                            selectedDate.getFullYear() === currentYear && 
                            selectedDate.getMonth() === currentMonth && 
                            selectedDate.getDate() === date) {
                            btn.classList.add('selected');
                        }
                        
                        // 格式化日期为YYYY-MM-DD格式
                        btn.dataset.date = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(date).padStart(2, '0')}`;
                        
                        cell.appendChild(btn);
                        date++;
                    }
                    // 下个月的日期
                    else {
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.textContent = nextMonthDate;
                        btn.className = 'out-of-month';
                        
                        if (currentMonth === 11) {
                            btn.dataset.date = `${currentYear + 1}-01-${String(nextMonthDate).padStart(2, '0')}`;
                        } else {
                            btn.dataset.date = `${currentYear}-${String(currentMonth + 2).padStart(2, '0')}-${String(nextMonthDate).padStart(2, '0')}`;
                        }
                        
                        cell.appendChild(btn);
                        nextMonthDate++;
                    }
                    
                    row.appendChild(cell);
                }
                
                tbody.appendChild(row);
            }
            
            calendar.appendChild(tbody);
            
            // 为日期按钮添加点击事件
            const dateButtons = calendar.querySelectorAll('button');
            dateButtons.forEach(button => {
                button.addEventListener('click', function() {
                    const dateStr = this.dataset.date;
                    selectedDate = new Date(dateStr.replace(/-/g, '/'));
                    
                    // 更新输入框值
                    taskDueDateDate.value = dateStr;
                    // 触发change事件，更新隐藏字段
                    const changeEvent = new Event('change');
                    taskDueDateDate.dispatchEvent(changeEvent);
                    
                    // 隐藏日期选择器
                    hideDatepicker();
                });
            });
        }
        
        // 切换到上个月
        prevButton.addEventListener('click', function() {
            currentMonth--;
            if (currentMonth < 0) {
                currentMonth = 11;
                currentYear--;
            }
            updateCalendar();
        });
        
        // 切换到下个月
        nextButton.addEventListener('click', function() {
            currentMonth++;
            if (currentMonth > 11) {
                currentMonth = 0;
                currentYear++;
            }
            updateCalendar();
        });
        
        // 点击今天按钮
        todayButton.addEventListener('click', function() {
            const today = new Date();
            currentMonth = today.getMonth();
            currentYear = today.getFullYear();
            selectedDate = today;
            
            // 更新输入框值
            const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
            taskDueDateDate.value = dateStr;
            // 触发change事件，更新隐藏字段
            const changeEvent = new Event('change');
            taskDueDateDate.dispatchEvent(changeEvent);
            
            updateCalendar();
            hideDatepicker();
        });
        
        // 显示日期选择器
        function showDatepicker() {
            updateCalendar();
            
            // 定位日期选择器
            const inputRect = taskDueDateDate.getBoundingClientRect();
            datepickerContainer.style.top = `${inputRect.bottom + window.scrollY}px`;
            datepickerContainer.style.left = `${inputRect.left + window.scrollX}px`;
            
            // 显示日期选择器
            datepickerContainer.classList.add('visible');
            
            // 添加点击其他区域关闭日期选择器的事件
            setTimeout(() => {
                document.addEventListener('click', outsideClickHandler);
            }, 10);
        }
        
        // 隐藏日期选择器
        function hideDatepicker() {
            datepickerContainer.classList.remove('visible');
            document.removeEventListener('click', outsideClickHandler);
        }
        
        // 点击日期选择器外部区域关闭日期选择器
        function outsideClickHandler(event) {
            if (!datepickerContainer.contains(event.target) && event.target !== taskDueDateDate) {
                hideDatepicker();
            }
        }
        
        // 为日期输入框添加点击事件
        taskDueDateDate.addEventListener('click', function(e) {
            e.preventDefault(); // 阻止默认行为
            showDatepicker();
        });
        
        // 为输入框添加手动输入验证
        taskDueDateDate.addEventListener('input', function(e) {
            const value = e.target.value;
            const datePattern = /^\d{4}-\d{2}-\d{2}$/;
            
            if (value && !datePattern.test(value)) {
                e.target.setCustomValidity('请使用YYYY-MM-DD格式');
            } else {
                e.target.setCustomValidity('');
                
                // 如果是有效日期，更新selectedDate
                if (value) {
                    selectedDate = new Date(value.replace(/-/g, '/'));
                    currentYear = selectedDate.getFullYear();
                    currentMonth = selectedDate.getMonth();
                }
            }
        });
        
        // 初始化日历
        updateCalendar();
        
        // 返回API
        return {
            showDatepicker,
            hideDatepicker,
            updateCalendar
        };
    }
    
    // 初始化自定义日期选择器
    let datepicker;
    if (taskDueDateDate) {
        datepicker = createCustomDatepicker();
    }
    // 编辑任务时拆分日期和时间
    window.startEditTask = function(task) {
        editingTaskId = task.id;
        formTitle.textContent = '编辑任务';
        taskIdInput.value = task.id;
        taskTitleInput.value = task.title;
        taskDescriptionInput.value = task.description;
        taskPriorityInput.value = task.priority;
        taskCategoryInput.value = task.category;
        // 拆分日期和时间
        if (task.due_date) {
            const dateTimeValue = formatDateForInput(task.due_date);
            if (dateTimeValue) {
                const [datePart, timePart] = dateTimeValue.split('T');
                if (taskDueDateDate) taskDueDateDate.value = datePart;
                if (taskDueDateTime) taskDueDateTime.value = timePart || '12:00';
                taskDueDateInput.value = dateTimeValue;
            } else {
                if (taskDueDateDate) taskDueDateDate.value = '';
                if (taskDueDateTime) taskDueDateTime.value = '12:00';
                taskDueDateInput.value = '';
            }
        } else {
            if (taskDueDateDate) taskDueDateDate.value = '';
            if (taskDueDateTime) taskDueDateTime.value = '12:00';
            taskDueDateInput.value = '';
        }
        saveTaskBtn.textContent = '保存任务';
        showFormBtn.style.display = 'none';
        taskFormSection.style.display = 'block';
        setTimeout(() => {
            const titleInput = document.getElementById('task-title');
            if (titleInput) titleInput.focus();
        }, 100);
    };

    // 初始化时间选择器
    if (taskDueDateTime) {
        // 为时间输入框添加验证和格式化
        taskDueDateTime.addEventListener('input', function(e) {
            const value = e.target.value;
            const timePattern = /^\d{2}:\d{2}$/;
            
            if (value && !timePattern.test(value)) {
                e.target.setCustomValidity('请使用HH:MM格式，例如13:30');
            } else {
                e.target.setCustomValidity('');
                
                // 如果有效，确保格式正确
                if (value) {
                    const [hours, minutes] = value.split(':');
                    if (parseInt(hours) >= 24 || parseInt(minutes) >= 60) {
                        e.target.setCustomValidity('时间格式无效，小时应小于24，分钟应小于60');
                    }
                }
            }
        });
        
        // 添加时间格式提示
        const timeHelperText = document.createElement('div');
        timeHelperText.className = 'date-helper-text';
        timeHelperText.textContent = '时间格式：小时:分钟，例如13:30';
        taskDueDateTime.parentNode.appendChild(timeHelperText);
        
        // 在失焦时自动格式化
        taskDueDateTime.addEventListener('blur', function() {
            const value = this.value.trim();
            
            // 如果为空，设置默认值
            if (!value) {
                this.value = '12:00';
                return;
            }
            
            // 尝试解析输入的时间
            let hours, minutes;
            
            // 处理只有数字的情况
            if (/^\d{1,4}$/.test(value)) {
                if (value.length === 4) {
                    // 例如"1430"解析为"14:30"
                    hours = value.substring(0, 2);
                    minutes = value.substring(2, 4);
                } else if (value.length === 3) {
                    // 例如"130"解析为"01:30"
                    hours = '0' + value.substring(0, 1);
                    minutes = value.substring(1, 3);
                } else if (value.length === 2) {
                    // 例如"14"解析为"14:00"
                    hours = value;
                    minutes = '00';
                } else {
                    // 例如"1"解析为"01:00"
                    hours = '0' + value;
                    minutes = '00';
                }
            }
            // 处理带冒号的情况
            else if (/^\d{1,2}:\d{1,2}$/.test(value)) {
                const parts = value.split(':');
                hours = parts[0];
                minutes = parts[1];
                
                // 补全格式
                if (hours.length === 1) hours = '0' + hours;
                if (minutes.length === 1) minutes = '0' + minutes;
            }
            // 其他无法解析的情况
            else {
                this.value = '12:00';
                return;
            }
            
            // 验证小时和分钟的范围
            hours = Math.min(Math.max(parseInt(hours), 0), 23);
            minutes = Math.min(Math.max(parseInt(minutes), 0), 59);
            
            // 格式化为HH:MM
            this.value = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            
            // 触发change事件，更新隐藏字段
            const changeEvent = new Event('change');
            this.dispatchEvent(changeEvent);
        });
    }

    taskForm.addEventListener('submit', handleFormSubmit);
    // View Switcher Listeners
    showListBtn.addEventListener('click', () => switchView('list'));
    showCalendarBtn.addEventListener('click', () => switchView('calendar'));

    // Calendar Mode Switcher Listeners
    calendarMonthBtn.addEventListener('click', () => {
        calendarDisplayMode = 'month';
        renderCalendar();
    });
    calendarWeekBtn.addEventListener('click', () => {
        calendarDisplayMode = 'week';
        renderCalendar();
    });
    calendarDayBtn.addEventListener('click', () => {
        calendarDisplayMode = 'day';
        renderCalendar();
    });

    themeToggleBtn.addEventListener('click', toggleTheme);
    
    // 添加刷新页面的功能
    function refreshPage() {
        // 添加一个加载类到刷新按钮，显示它正在工作
        const refreshButton = document.getElementById('refresh-btn');
        
        refreshButton.classList.add('refreshing');
        refreshButton.disabled = true;
        const originalText = refreshButton.textContent;
        refreshButton.textContent = '刷新中...';
        
        // 显示加载提示
        const loadingToast = document.createElement('div');
        loadingToast.className = 'toast loading-toast';
        loadingToast.innerHTML = '<span class="toast-text">正在刷新数据...</span>';
        document.body.appendChild(loadingToast);
        
        // 刷新数据
        Promise.all([
            fetchTasks(),
            // 可以在这里添加其他需要刷新的数据
        ]).then(() => {
            // 修改提示为成功信息
            loadingToast.innerHTML = '<span class="toast-icon">✓</span><span class="toast-text">刷新成功！</span>';
            loadingToast.className = 'toast success-toast';
            
            // 移除加载提示
            setTimeout(() => {
                loadingToast.className = 'toast success-toast fade-out';
                setTimeout(() => {
                    if (document.body.contains(loadingToast)) {
                        document.body.removeChild(loadingToast);
                    }
                }, 500);
            }, 1200);
            
            // 恢复按钮状态
            setTimeout(() => {
                refreshButton.classList.remove('refreshing');
                refreshButton.disabled = false;
                refreshButton.textContent = originalText;
            }, 800);
        }).catch(error => {
            console.error('刷新数据时出错:', error);
            loadingToast.innerHTML = '<span class="toast-icon">✗</span><span class="toast-text">刷新失败，请稍后再试</span>';
            loadingToast.className = 'toast error-toast';
            
            // 移除错误提示
            setTimeout(() => {
                if (document.body.contains(loadingToast)) {
                    loadingToast.className = 'toast error-toast fade-out';
                    setTimeout(() => {
                        document.body.removeChild(loadingToast);
                    }, 500);
                }
            }, 2500);
            
            // 恢复按钮状态
            refreshButton.classList.remove('refreshing');
            refreshButton.disabled = false;
            refreshButton.textContent = originalText;
        });
    }
    
    // 绑定刷新按钮点击事件
    refreshBtn.addEventListener('click', refreshPage);

    // 优化任务列表删除按钮事件绑定，使用事件委托
    // 在DOMContentLoaded内添加：
    taskListUl.addEventListener('click', (e) => {
        const target = e.target;
        if (target.classList.contains('delete-btn')) {
            const li = target.closest('.task-item');
            if (li && li.dataset.taskId) {
                if (confirm('确定要删除此任务吗？')) {
                    apiCall(`${API_BASE_URL}/tasks/${li.dataset.taskId}`, 'DELETE').then(() => fetchTasks());
                }
            }
        }
        if (target.classList.contains('complete-btn')) {
            const li = target.closest('.task-item');
            if (li && li.dataset.taskId) {
                const isCompleted = li.classList.contains('completed') ? 0 : 1;
                apiCall(`${API_BASE_URL}/tasks/${li.dataset.taskId}`, 'PUT', { completed: isCompleted }).then(() => fetchTasks());
            }
        }
        if (target.classList.contains('edit-btn')) {
            const li = target.closest('.task-item');
            if (li && li.dataset.taskId) {
                const task = allTasks.find(t => t.id == li.dataset.taskId);
                if (task) startEditTask(task);
            }
        }
    });

    // 让日历视图的“返回任务列表”按钮切换回列表视图
const calendarListBtn = document.querySelector('#calendar-view-container .view-switcher #show-list-btn');
if (calendarListBtn) {
    calendarListBtn.addEventListener('click', () => switchView('list'));
}

    // --- Initial Load ---
    updateClock(); // Initial clock update
    setInterval(updateClock, 1000); // Update clock every second
    switchView('list'); // Start in list view
    fetchTasks(); // Initial task fetch
    loadThemePreference();

});
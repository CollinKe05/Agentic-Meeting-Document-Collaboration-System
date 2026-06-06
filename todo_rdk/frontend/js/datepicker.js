// 自定义日期选择器实现
document.addEventListener('DOMContentLoaded', function() {
    // 获取日期和时间输入框
    const taskDueDateDate = document.getElementById('task-due-date-date');
    const taskDueDateTime = document.getElementById('task-due-date-time');
    const taskDueDateInput = document.getElementById('task-due-date');
    
    // 如果存在日期输入框，初始化自定义日期选择器
    if (taskDueDateDate) {
        // 创建自定义日期选择器
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
            
            ['日', '一', '二', '三', '四', '五', '六'].forEach((day, index) => {
                const th = document.createElement('th');
                th.textContent = day;
                if (index === 0 || index === 6) {
                    th.className = 'weekend-header';
                }
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
                        
                        // 检查是否是周末
                        const dayOfWeek = currentDate.getDay();
                        if (dayOfWeek === 0 || dayOfWeek === 6) {
                            btn.classList.add('weekend');
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
    }
    
    // 为时间输入框添加增强功能
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
        // timeHelperText.textContent = '时间格式：小时:分钟，例如13:30';
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
    
    // 合成日期时间到隐藏字段的功能
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
    
    // 添加事件监听
    if (taskDueDateDate) {
        taskDueDateDate.addEventListener('change', updateCombinedDateTime);
        taskDueDateDate.addEventListener('blur', updateCombinedDateTime);
    }
    
    if (taskDueDateTime) {
        taskDueDateTime.addEventListener('change', updateCombinedDateTime);
        taskDueDateTime.addEventListener('blur', updateCombinedDateTime);
    }
    
    // 清除日期的按钮功能
    const clearDateBtn = document.getElementById('clear-date-btn');
    if (clearDateBtn) {
        clearDateBtn.addEventListener('click', function() {
            if (taskDueDateDate) taskDueDateDate.value = '';
            if (taskDueDateTime) taskDueDateTime.value = '12:00';
            if (taskDueDateInput) taskDueDateInput.value = '';
        });
    }
    
    // 获取任务表单并添加提交前处理
    const taskForm = document.getElementById('task-form');
    if (taskForm) {
        taskForm.addEventListener('submit', updateCombinedDateTime);
    }
});

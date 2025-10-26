// 全局变量
let currentUser = null;
let exportHistory = [];

// DOM元素
const profileTabs = document.querySelectorAll('.profile-tab');
const tabContents = document.querySelectorAll('.profile-tab-content');
const passwordForm = document.getElementById('password-form');
const exportsList = document.getElementById('exports-list');
const refreshExportsBtn = document.getElementById('refresh-exports');
const reExportModal = document.getElementById('re-export-modal');
const reExportModalClose = document.getElementById('re-export-modal-close');
const reExportBtn = document.getElementById('re-export-btn');
const backToMainBtn = document.getElementById('back-to-main');
const loading = document.getElementById('loading');
const message = document.getElementById('message');
const messageText = document.getElementById('message-text');
const messageClose = document.getElementById('message-close');

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeProfile();
});

// 初始化用户中心
async function initializeProfile() {
    try {
        // 检查登录状态
        await checkLoginStatus();
        
        // 确保用户信息已加载
        if (!currentUser) {
            console.error('用户信息未正确加载');
            return;
        }
        
        setupEventListeners();
        
        // 加载用户信息
        await loadUserInfo();
        
        // 加载导出记录
        await loadExportHistory();
    } catch (error) {
        console.error('Profile页面初始化失败:', error);
    }
}

// 检查登录状态
async function checkLoginStatus() {
    try {
        const response = await fetch('/api/auth/current');
        const result = await response.json();
        
        if (result.success) {
            currentUser = result.user;
            
            // 立即更新页面上的用户名显示
            const usernameElement = document.getElementById('current-username');
            if (usernameElement) {
                usernameElement.textContent = currentUser.username;
            }
        } else {
            window.location.href = '/login';
        }
    } catch (error) {
        console.error('检查登录状态时发生错误:', error);
        window.location.href = '/login';
    }
}

// 设置事件监听器
function setupEventListeners() {
    // 标签页切换
    profileTabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
    
    // 密码修改表单
    passwordForm.addEventListener('submit', handlePasswordChange);
    
    // 刷新导出记录
    refreshExportsBtn.addEventListener('click', loadExportHistory);
    
    // 返回主页
    backToMainBtn.addEventListener('click', () => {
        window.location.href = '/';
    });
    
    // 重新导出模态框
    reExportModalClose.addEventListener('click', closeReExportModal);
    reExportModal.addEventListener('click', (e) => {
        if (e.target === reExportModal) closeReExportModal();
    });
    
    // 重新导出按钮
    reExportBtn.addEventListener('click', handleReExport);
    
    // 消息关闭
    messageClose.addEventListener('click', hideMessage);
}

// 切换标签页
function switchTab(tabName) {
    // 移除所有活动状态
    profileTabs.forEach(tab => tab.classList.remove('active'));
    tabContents.forEach(content => content.classList.remove('active'));
    
    // 激活选中的标签页
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');
}

// 加载用户信息
async function loadUserInfo() {
    if (!currentUser) {
        console.error('没有当前用户信息，跳过加载');
        return;
    }
    
    try {
        // 更新用户名
        const usernameElement = document.getElementById('profile-username');
        if (usernameElement) {
            usernameElement.textContent = currentUser.username;
        }
        
        // 更新邮箱
        const emailElement = document.getElementById('profile-email');
        if (emailElement) {
            emailElement.textContent = currentUser.email || '未设置';
        }
        
        // 更新创建时间
        const createdElement = document.getElementById('profile-created');
        if (createdElement) {
            createdElement.textContent = formatDate(currentUser.created_at);
        }
    } catch (error) {
        console.error('加载用户信息时发生错误:', error);
    }
}

// 处理密码修改
async function handlePasswordChange(e) {
    e.preventDefault();
    
    const formData = new FormData(passwordForm);
    const oldPassword = formData.get('old_password');
    const newPassword = formData.get('new_password');
    const confirmPassword = formData.get('confirm_password');
    
    // 验证密码
    if (newPassword !== confirmPassword) {
        showMessage('新密码和确认密码不匹配', 'error');
        return;
    }
    
    if (newPassword.length < 6) {
        showMessage('新密码至少需要6个字符', 'error');
        return;
    }
    
    try {
        showLoading(true);
        
        const response = await fetch('/api/user/reset-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showMessage('密码修改成功', 'success');
            passwordForm.reset();
        } else {
            showMessage('密码修改失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('密码修改失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 加载导出记录
async function loadExportHistory() {
    try {
        showLoading(true);
        
        const response = await fetch('/api/user/exports');
        const result = await response.json();
        
        if (result.success) {
            exportHistory = result.exports;
            displayExportHistory();
        } else {
            showMessage('加载导出记录失败: ' + result.message, 'error');
        }
    } catch (error) {
        console.error('加载导出记录时发生错误:', error);
        showMessage('加载导出记录失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 显示导出记录
function displayExportHistory() {
    if (exportHistory.length === 0) {
        exportsList.innerHTML = '<div class="no-exports">暂无导出记录</div>';
        return;
    }
    
    exportsList.innerHTML = exportHistory.map(exportItem => `
        <div class="export-item">
            <div class="export-info">
                <div class="export-title">${exportItem.title}</div>
                <div class="export-meta">
                    <span><i class="fas fa-file"></i> ${exportItem.export_format.toUpperCase()}</span>
                    <span><i class="fas fa-list"></i> ${exportItem.export_mode === 'questions' ? '仅试题' : '试题+答案'}</span>
                    <span><i class="fas fa-clock"></i> ${formatDate(exportItem.created_at)}</span>
                    <span><i class="fas fa-hashtag"></i> ${exportItem.question_ids.length} 道题目</span>
                </div>
            </div>
            <div class="export-actions">
                <button class="btn-re-export" onclick="openReExportModal(${exportItem.id})">
                    <i class="fas fa-redo"></i> 重新导出
                </button>
            </div>
        </div>
    `).join('');
}

// 打开重新导出模态框
async function openReExportModal(exportId) {
    try {
        showLoading(true);
        
        const response = await fetch(`/api/user/re-export/${exportId}`);
        const result = await response.json();
        
        if (result.success) {
            const exportData = result.export;
            const questions = result.questions;
            
            // 设置标题
            document.getElementById('re-export-title').value = exportData.title;
            
            // 设置导出模式
            document.querySelector(`input[name="re-export-mode"][value="${exportData.export_mode}"]`).checked = true;
            
            // 设置导出格式
            document.querySelector(`input[name="re-export-format"][value="${exportData.export_format}"]`).checked = true;
            
            // 显示题目列表
            displayReExportQuestions(questions);
            
            // 存储当前导出的题目数据
            window.currentReExportQuestions = questions;
            
            reExportModal.style.display = 'block';
        } else {
            showMessage('加载导出数据失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('加载导出数据失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 显示重新导出的题目
function displayReExportQuestions(questions) {
    const container = document.getElementById('re-export-items');
    
    if (questions.length === 0) {
        container.innerHTML = '<div class="no-results">没有题目</div>';
        return;
    }
    
    container.innerHTML = questions.map((question, index) => {
        // 安全地处理题目内容，避免HTML注入
        const content = question.latex_content || '题目内容';
        const preview = content.length > 80 ? content.substring(0, 80) + '...' : content;
        
        return `
            <div class="cart-item" data-index="${index}">
                <div class="cart-item-content">
                    <div class="cart-item-title">题目 ${index + 1}</div>
                    <div class="cart-item-preview">${escapeHtml(preview)}</div>
                </div>
            </div>
        `;
    }).join('');
}

// HTML转义函数
function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
}

// 关闭重新导出模态框
function closeReExportModal() {
    reExportModal.style.display = 'none';
    window.currentReExportQuestions = null;
}

// 处理重新导出
async function handleReExport() {
    if (!window.currentReExportQuestions || window.currentReExportQuestions.length === 0) {
        showMessage('没有题目可导出', 'error');
        return;
    }
    
    const title = document.getElementById('re-export-title').value || '数学试卷';
    const mode = document.querySelector('input[name="re-export-mode"]:checked').value;
    const format = document.querySelector('input[name="re-export-format"]:checked').value;
    
    try {
        showLoading(true);
        
        const response = await fetch('/api/export-paper', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                questions: window.currentReExportQuestions,
                title: title,
                mode: mode,
                format: format
            })
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${title}_${new Date().getTime()}.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            showMessage('重新导出成功！', 'success');
            closeReExportModal();
        } else {
            const result = await response.json();
            showMessage('重新导出失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('重新导出失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 格式化日期
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 显示加载状态
function showLoading(show) {
    if (show) {
        loading.classList.remove('hidden');
    } else {
        loading.classList.add('hidden');
    }
}

// 显示消息
function showMessage(text, type) {
    messageText.textContent = text;
    message.className = `message ${type}`;
    message.classList.remove('hidden');
    
    // 3秒后自动隐藏
    setTimeout(() => {
        hideMessage();
    }, 3000);
}

// 隐藏消息
function hideMessage() {
    message.classList.add('hidden');
}

// 全局函数
window.openReExportModal = openReExportModal;

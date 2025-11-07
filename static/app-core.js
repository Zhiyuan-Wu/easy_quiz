// 应用核心：初始化逻辑与通用工具函数
// 此文件负责共享状态、事件绑定以及跨模块复用的函数

// 全局状态变量（供各模块使用）
let currentPage = 1;
let totalPages = 1;
let availableTags = [];
let currentQuestions = [];
let questionsTotal = 0;
let uploadedImages = [];
let parsedQuestions = [];
let cart = [];
let currentUser = null;
let studentList = [];
let selectedStudent = null;
let homeworkState = {
    student: null,
    exportId: null,
    paperTitle: '',
    results: [],
    raw: null
};
let exportHistoryCache = null;

const modalState = {
    questionId: null,
    original: null,
    isEditing: false,
    aiSuggested: false,
    draft: {
        latex_content: '',
        reference_answer: '',
        question_type: '解答题'
    }
};

let saveEditLoading = false;
let aiVariantLoading = false;

// DOM 元素缓存
const navTabs = document.querySelectorAll('.nav-tab');
const tabContents = document.querySelectorAll('.tab-content');
const questionForm = document.getElementById('question-form');
const autoTagBtn = document.getElementById('auto-tag-btn');
const searchBtn = document.getElementById('search-btn');
const searchKeyword = document.getElementById('search-keyword');
const tagSelector = document.getElementById('tag-selector');
const tagFilter = document.getElementById('tag-filter');
const searchResults = document.getElementById('search-results');
const questionList = document.getElementById('question-list');
const refreshBtn = document.getElementById('refresh-btn');
const prevPageBtn = document.getElementById('prev-page');
const nextPageBtn = document.getElementById('next-page');
const topPrevPageBtn = document.getElementById('top-prev-page');
const topNextPageBtn = document.getElementById('top-next-page');
const pageInfo = document.getElementById('page-info');
const currentCount = document.getElementById('current-count');
const totalCount = document.getElementById('total-count');
const questionModal = document.getElementById('question-modal');
const questionModalClose = questionModal ? questionModal.querySelector('.modal-close') : null;
const loading = document.getElementById('loading');
const message = document.getElementById('message');
const messageText = document.getElementById('message-text');
const messageClose = document.getElementById('message-close');
const modalQuestionContent = document.getElementById('modal-question-content');
const modalQuestionTags = document.getElementById('modal-question-tags');
const modalQuestionAnswer = document.getElementById('modal-question-answer');
const modalQuestionEditor = document.getElementById('modal-question-editor');
const modalAnswerEditor = document.getElementById('modal-answer-editor');
const modalQuestionType = document.getElementById('modal-question-type');
const editQuestionBtn = document.getElementById('edit-question-btn');
const saveQuestionBtn = document.getElementById('save-question-btn');
const cancelEditBtn = document.getElementById('cancel-edit-btn');
const aiVariantBtn = document.getElementById('ai-variant-btn');
const modalEditHint = document.getElementById('modal-edit-hint');

const addQuestionModal = document.getElementById('add-question-modal');
const openAddQuestionModalBtn = document.getElementById('open-add-question-modal');
const addStudentModal = document.getElementById('add-student-modal');
const addStudentForm = document.getElementById('add-student-form');
const submitStudentBtn = document.getElementById('submit-student-btn');
const addStudentBtn = document.getElementById('add-student-btn');
const reloadStudentsBtn = document.getElementById('reload-students-btn');
const studentIdInput = document.getElementById('student-id-input');
const studentNameInput = document.getElementById('student-name-input');
const studentsTableBody = document.getElementById('students-table-body');
const studentsTableWrapper = document.getElementById('students-table-wrapper');
const studentsEmpty = document.getElementById('students-empty');
const studentsCountLabel = document.getElementById('students-count');

const homeworkModal = document.getElementById('homework-modal');
const homeworkParseBtn = document.getElementById('homework-parse-btn');
const homeworkSaveBtn = document.getElementById('homework-save-btn');
const homeworkExportSelect = document.getElementById('homework-export-select');
const homeworkExportOptions = document.getElementById('homework-export-options');
const homeworkFileInput = document.getElementById('homework-file-input');
const homeworkUploadZone = document.getElementById('homework-upload-zone');
const homeworkUploadBtn = document.getElementById('homework-upload-btn');
const homeworkPreview = document.getElementById('homework-preview');
const removeHomeworkBtn = document.getElementById('remove-homework-btn');
const homeworkResultsContainer = document.getElementById('homework-results');
const homeworkResultsList = document.getElementById('homework-results-list');
const homeworkStudentName = document.getElementById('homework-student-name');
const homeworkStudentId = document.getElementById('homework-student-id');

const questionTypeSelect = document.getElementById('question-type-select');

const historyModal = document.getElementById('history-modal');
const historyContent = document.getElementById('history-content');

const reportModal = document.getElementById('report-modal');
const reportDistribution = document.getElementById('report-distribution');
const reportKnowledgeList = document.getElementById('report-knowledge-list');
const reportPlanList = document.getElementById('report-plan-list');
const refreshReportBtn = document.getElementById('refresh-report-btn');

const recommendationModal = document.getElementById('recommendation-modal');
const recommendationReasons = document.getElementById('recommendation-reasons');
const recommendationList = document.getElementById('recommendation-list');

const imageUpload = document.getElementById('image-upload');
const uploadBtn = document.getElementById('upload-btn');
const imagePreview = document.getElementById('image-preview');

const examUpload = document.getElementById('exam-upload');
const examUploadBtn = document.getElementById('exam-upload-btn');
const examPreview = document.getElementById('exam-preview');
const parseExamBtn = document.getElementById('parse-exam-btn');
const parsedQuestionsDiv = document.getElementById('parsed-questions');
const parsedQuestionsList = document.getElementById('parsed-questions-list');
const batchSaveBtn = document.getElementById('batch-save-btn');

const logoutBtn = document.getElementById('logout-btn');
const cartIcon = document.getElementById('cart-icon');
const cartBadge = document.getElementById('cart-badge');
const cartModal = document.getElementById('cart-modal');
const cartModalClose = document.getElementById('cart-modal-close');
const clearCartBtn = document.getElementById('clear-cart-btn');
const exportPaperBtn = document.getElementById('export-paper-btn');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

async function initializeApp() {
    await checkLoginStatus();

    // 根据配置设置CSS变量
    applyConfigToCSS();

    setupEventListeners();

    await loadAvailableTags();

    const activeTab = document.querySelector('.nav-tab.active');
    if (activeTab) {
        const tabName = activeTab.dataset.tab;
        if (tabName === 'manage') {
            await loadQuestions();
        } else if (tabName === 'students') {
            await loadStudents();
        }
    }

    setTimeout(() => {
        renderMath();
    }, 100);

    updateCartBadge();
}

// 根据配置应用CSS变量
function applyConfigToCSS() {
    if (!window.APP_CONFIG) {
        return;
    }

    const root = document.documentElement;
    const lineHeight = 1.6; // 与CSS中的line-height保持一致
    
    // 题目卡片配置
    if (window.APP_CONFIG.content && window.APP_CONFIG.content.questionCard) {
        const config = window.APP_CONFIG.content.questionCard;
        const mobileBreakpoint = window.APP_CONFIG.layout?.mobileBreakpoint || 900;
        
        // 计算桌面端和移动端的最大高度（行数 × 行高）
        const maxLinesDesktop = config.maxLinesDesktop || 16;
        const maxLinesMobile = config.maxLinesMobile || 12;
        const maxHeightDesktop = `calc(${maxLinesDesktop} * ${lineHeight}em)`;
        const maxHeightMobile = `calc(${maxLinesMobile} * ${lineHeight}em)`;
        
        // 设置桌面端和移动端的最大高度值
        root.style.setProperty('--question-card-max-height-desktop', maxHeightDesktop);
        root.style.setProperty('--question-card-max-height-mobile', maxHeightMobile);
        root.style.setProperty('--question-card-gradient-height', (config.gradientHeight || 48) + 'px');
        
        // 更新当前屏幕尺寸下的最大高度
        function updateMaxHeight() {
            const isMobile = window.innerWidth < mobileBreakpoint;
            const maxHeight = isMobile ? maxHeightMobile : maxHeightDesktop;
            root.style.setProperty('--max-height', maxHeight);
        }
        
        // 初始设置
        updateMaxHeight();
        
        // 监听窗口大小变化（使用防抖优化性能）
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(updateMaxHeight, 100);
        });
    }
}

async function checkLoginStatus() {
    try {
        const response = await fetch('/api/auth/current');
        const result = await response.json();

        if (result.success) {
            currentUser = result.user;
            const usernameElement = document.getElementById('current-username');
            if (usernameElement) {
                usernameElement.textContent = currentUser.username;
            }
        } else {
            window.location.href = '/login';
        }
    } catch (error) {
        window.location.href = '/login';
    }
}

function setupEventListeners() {
    navTabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    if (questionForm) {
        questionForm.addEventListener('submit', handleFormSubmit);
    }

    if (autoTagBtn) {
        autoTagBtn.addEventListener('click', handleAutoTag);
    }

    if (searchBtn) {
        searchBtn.addEventListener('click', handleSearch);
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadQuestions);
    }

    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', () => changePage(-1));
    }
    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', () => changePage(1));
    }
    if (topPrevPageBtn) {
        topPrevPageBtn.addEventListener('click', () => changePage(-1));
    }
    if (topNextPageBtn) {
        topNextPageBtn.addEventListener('click', () => changePage(1));
    }

    if (questionModalClose) {
        questionModalClose.addEventListener('click', closeQuestionModal);
    }
    if (questionModal) {
        questionModal.addEventListener('click', (e) => {
            if (e.target === questionModal) closeQuestionModal();
        });
    }

    if (messageClose) {
        messageClose.addEventListener('click', hideMessage);
    }

    if (searchKeyword) {
        searchKeyword.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleSearch();
        });
    }

    if (uploadBtn && imageUpload) {
        uploadBtn.addEventListener('click', () => imageUpload.click());
        imageUpload.addEventListener('change', handleImageUpload);
    }

    if (examUploadBtn && examUpload) {
        examUploadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            examUpload.click();
        });
        examUpload.addEventListener('change', handleExamUpload);
    }
    if (parseExamBtn) {
        parseExamBtn.addEventListener('click', handleParseExam);
    }

    const uploadZone = document.getElementById('upload-zone');
    if (uploadZone) {
        uploadZone.addEventListener('click', (e) => {
            if (e.target === uploadZone || e.target.closest('.upload-icon') || e.target.tagName === 'H3' || e.target.tagName === 'P') {
                examUpload?.click();
            }
        });
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });
        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                examUpload.files = files;
                handleExamUpload({ target: { files } });
            }
        });
    }

    const removeExamBtn = document.getElementById('remove-exam-btn');
    if (removeExamBtn) {
        removeExamBtn.addEventListener('click', removeExam);
    }

    if (batchSaveBtn) {
        batchSaveBtn.addEventListener('click', handleBatchSave);
    }

    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogout);
    }

    if (cartIcon) {
        cartIcon.addEventListener('click', openCartModal);
    }
    if (cartModalClose) {
        cartModalClose.addEventListener('click', closeCartModal);
    }
    if (cartModal) {
        cartModal.addEventListener('click', (e) => {
            if (e.target === cartModal) closeCartModal();
        });
    }

    if (clearCartBtn) {
        clearCartBtn.addEventListener('click', clearCart);
    }
    if (exportPaperBtn) {
        exportPaperBtn.addEventListener('click', exportPaper);
    }

    if (openAddQuestionModalBtn && addQuestionModal) {
        openAddQuestionModalBtn.addEventListener('click', () => openModalElement(addQuestionModal));
        attachModalBackdropHandler(addQuestionModal, () => closeModalElement(addQuestionModal));
    }

    if (addStudentBtn && addStudentModal) {
        addStudentBtn.addEventListener('click', () => {
            resetAddStudentForm();
            openModalElement(addStudentModal);
        });
        attachModalBackdropHandler(addStudentModal, () => closeModalElement(addStudentModal));
    }

    if (submitStudentBtn) {
        submitStudentBtn.addEventListener('click', handleStudentSubmit);
    }
    if (addStudentForm) {
        addStudentForm.addEventListener('submit', (event) => {
            event.preventDefault();
            handleStudentSubmit();
        });
    }

    if (reloadStudentsBtn) {
        reloadStudentsBtn.addEventListener('click', () => loadStudents(true));
    }

    if (studentsTableBody) {
        studentsTableBody.addEventListener('click', handleStudentActionClick);
    }

    if (homeworkModal) {
        attachModalBackdropHandler(homeworkModal, () => closeModalElement(homeworkModal));
    }
    if (homeworkParseBtn) {
        homeworkParseBtn.addEventListener('click', handleHomeworkParse);
    }
    if (homeworkSaveBtn) {
        homeworkSaveBtn.addEventListener('click', handleHomeworkSave);
    }
    if (homeworkUploadBtn) {
        homeworkUploadBtn.addEventListener('click', () => homeworkFileInput?.click());
    }
    if (homeworkUploadZone) {
        homeworkUploadZone.addEventListener('click', (e) => {
            if (e.target === homeworkUploadZone || e.target.closest('.upload-icon') || e.target.tagName === 'H4' || e.target.tagName === 'P') {
                homeworkFileInput?.click();
            }
        });
        homeworkUploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            homeworkUploadZone.classList.add('dragover');
        });
        homeworkUploadZone.addEventListener('dragleave', () => {
            homeworkUploadZone.classList.remove('dragover');
        });
        homeworkUploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            homeworkUploadZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                homeworkFileInput.files = files;
                handleHomeworkFileUpload({ target: { files } });
            }
        });
    }
    if (homeworkFileInput) {
        homeworkFileInput.addEventListener('change', handleHomeworkFileUpload);
    }
    if (removeHomeworkBtn) {
        removeHomeworkBtn.addEventListener('click', removeHomeworkFile);
    }

    initCustomSelects();

    if (historyModal) {
        attachModalBackdropHandler(historyModal, () => closeModalElement(historyModal));
    }

    if (reportModal) {
        attachModalBackdropHandler(reportModal, () => closeModalElement(reportModal));
    }
    if (refreshReportBtn) {
        refreshReportBtn.addEventListener('click', () => loadStudentReport(selectedStudent, { refresh: true }));
    }

    if (recommendationModal) {
        attachModalBackdropHandler(recommendationModal, () => closeModalElement(recommendationModal));
    }

    if (recommendationList) {
        recommendationList.addEventListener('click', handleRecommendationClick);
    }

    document.querySelectorAll('[data-close]').forEach(button => {
        button.addEventListener('click', () => {
            const targetId = button.getAttribute('data-close');
            if (!targetId) return;
            const modal = document.getElementById(targetId);
            closeModalElement(modal);
        });
    });

    if (editQuestionBtn) {
        editQuestionBtn.addEventListener('click', handleEditQuestion);
    }
    if (saveQuestionBtn) {
        saveQuestionBtn.addEventListener('click', handleSaveQuestion);
    }
    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', handleCancelEdit);
    }
    if (aiVariantBtn) {
        aiVariantBtn.addEventListener('click', handleAiVariant);
    }
    if (modalQuestionEditor) {
        modalQuestionEditor.addEventListener('input', () => {
            if (modalState.isEditing) {
                modalState.draft.latex_content = modalQuestionEditor.value;
            }
        });
    }
    if (modalAnswerEditor) {
        modalAnswerEditor.addEventListener('input', () => {
            if (modalState.isEditing) {
                modalState.draft.reference_answer = modalAnswerEditor.value;
            }
        });
    }
}

function switchTab(tabName) {
    navTabs.forEach(tab => tab.classList.remove('active'));
    const targetTab = document.querySelector(`[data-tab="${tabName}"]`);
    if (targetTab) {
        targetTab.classList.add('active');
    }

    tabContents.forEach(content => content.classList.remove('active'));
    const contentPanel = document.getElementById(`${tabName}-tab`);
    if (contentPanel) {
        contentPanel.classList.add('active');
    }

    if (tabName === 'manage') {
        loadQuestions();
    } else if (tabName === 'students') {
        loadStudents();
    } else if (tabName === 'search') {
        if (availableTags.length > 0) {
            renderTagFilter();
        }
        if (searchResults) {
            searchResults.innerHTML = '';
            searchResults.style.display = 'none';
        }
    }
}

function renderMathContent(content) {
    if (!content) return '';

    let processed = content;

    const placeholders = {
        olStart: '___MATHJAX_OL_START___',
        olEnd: '___MATHJAX_OL_END___',
        ulStart: '___MATHJAX_UL_START___',
        ulEnd: '___MATHJAX_UL_END___',
        liItem: '___MATHJAX_LI_ITEM___'
    };

    processed = processed.replace(/\\begin\{enumerate\}/g, placeholders.olStart);
    processed = processed.replace(/\\end\{enumerate\}/g, placeholders.olEnd);
    processed = processed.replace(/\\begin\{itemize\}/g, placeholders.ulStart);
    processed = processed.replace(/\\end\{itemize\}/g, placeholders.ulEnd);
    processed = processed.replace(/\\item\s*/g, placeholders.liItem);

    let escaped = processed
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');

    escaped = escaped.replace(new RegExp(placeholders.olStart, 'g'), '<ol class="math-enumerate">');
    escaped = escaped.replace(new RegExp(placeholders.olEnd, 'g'), '</ol>');
    escaped = escaped.replace(new RegExp(placeholders.ulStart, 'g'), '<ul class="math-itemize">');
    escaped = escaped.replace(new RegExp(placeholders.ulEnd, 'g'), '</ul>');
    escaped = escaped.replace(new RegExp(placeholders.liItem, 'g'), '<li class="math-item">');

    escaped = escaped.replace(/\n/g, '<br>');

    return escaped;
}

function renderMath() {
    if (window.MathJax) {
        MathJax.typesetPromise().catch((err) => {
            console.log('MathJax渲染错误:', err);
        });
    }
}

async function handleLogout() {
    try {
        const response = await fetch('/api/auth/logout', {
            method: 'POST'
        });

        if (response.ok) {
            window.location.href = '/login';
        }
    } catch (error) {
        showMessage('登出失败: ' + error.message, 'error');
    }
}

function formatDate(dateString) {
    if (!dateString) {
        return '';
    }
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) {
        return '';
    }
    return date.toLocaleString('zh-CN');
}

function showLoading(show) {
    if (!loading) return;
    if (show) {
        loading.classList.remove('hidden');
    } else {
        loading.classList.add('hidden');
    }
}

function showMessage(text, type = 'success') {
    if (!message || !messageText) return;
    messageText.textContent = text;
    message.className = `message ${type}`;
    message.classList.remove('hidden');

    // 错误类型的消息使用更长的停留时间
    const autoHide = type === 'error' 
        ? (APP_CONFIG.messages?.errorAutoHideMs ?? 8000)
        : (APP_CONFIG.messages?.autoHideMs ?? 3000);
    if (autoHide > 0) {
        setTimeout(() => {
            hideMessage();
        }, autoHide);
    }
}

function hideMessage() {
    if (!message) return;
    message.classList.add('hidden');
}

function openModalElement(modal) {
    if (!modal) return;
    modal.style.display = 'block';
}

function closeModalElement(modal) {
    if (!modal) return;
    modal.style.display = 'none';

    if (modal === addStudentModal) {
        resetAddStudentForm();
    }

    if (modal === homeworkModal) {
        resetHomeworkState();
    }
}

function attachModalBackdropHandler(modal, onClose) {
    if (!modal) return;
    modal.addEventListener('click', (event) => {
        if (event.target === modal) {
            if (typeof onClose === 'function') {
                onClose();
            } else {
                closeModalElement(modal);
            }
        }
    });
}

function resetAddStudentForm() {
    if (addStudentForm) {
        addStudentForm.reset();
    }
}

function resetHomeworkState() {
    homeworkState = {
        student: null,
        exportId: null,
        paperTitle: '',
        results: [],
        raw: null
    };

    if (homeworkExportSelect) {
        const trigger = homeworkExportSelect.querySelector('.custom-select-trigger');
        const valueSpan = trigger?.querySelector('.custom-select-value');
        if (valueSpan) {
            valueSpan.textContent = '请选择试卷';
        }
        if (homeworkExportOptions) {
            homeworkExportOptions.innerHTML = '';
        }
        if (trigger) {
            trigger.classList.remove('disabled');
        }
    }
    if (homeworkFileInput) {
        homeworkFileInput.value = '';
    }
    if (homeworkUploadZone) {
        homeworkUploadZone.style.display = 'block';
    }
    if (homeworkPreview) {
        homeworkPreview.style.display = 'none';
    }
    if (homeworkResultsContainer) {
        homeworkResultsContainer.classList.add('hidden');
    }
    if (homeworkResultsList) {
        homeworkResultsList.innerHTML = '';
    }
    if (homeworkSaveBtn) {
        homeworkSaveBtn.disabled = true;
    }
}

function initCustomSelects() {
    if (questionTypeSelect) {
        const trigger = questionTypeSelect.querySelector('.custom-select-trigger');
        const options = questionTypeSelect.querySelectorAll('.custom-select-option');
        if (trigger) {
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                const isActive = trigger.classList.contains('active');
                closeAllCustomSelects();
                if (!isActive) {
                    trigger.classList.add('active');
                    const optionsContainer = questionTypeSelect.querySelector('.custom-select-options');
                    if (optionsContainer) {
                        optionsContainer.classList.add('show');
                    }
                }
            });
        }
        options.forEach(option => {
            option.addEventListener('click', (e) => {
                e.stopPropagation();
                const value = option.dataset.value;
                const hiddenInput = document.getElementById('question-type');
                if (hiddenInput) {
                    hiddenInput.value = value;
                }
                const valueSpan = trigger?.querySelector('.custom-select-value');
                if (valueSpan) {
                    valueSpan.textContent = value;
                }
                options.forEach(opt => opt.classList.remove('selected'));
                option.classList.add('selected');
                closeAllCustomSelects();
            });
        });
    }

    if (homeworkExportSelect) {
        const trigger = homeworkExportSelect.querySelector('.custom-select-trigger');
        if (trigger) {
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                const isActive = trigger.classList.contains('active');
                closeAllCustomSelects();
                if (!isActive && !trigger.classList.contains('disabled')) {
                    trigger.classList.add('active');
                    if (homeworkExportOptions) {
                        homeworkExportOptions.classList.add('show');
                    }
                }
            });
        }
    }

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.custom-select')) {
            closeAllCustomSelects();
        }
    });
}

function closeAllCustomSelects() {
    document.querySelectorAll('.custom-select-trigger').forEach(trigger => {
        trigger.classList.remove('active');
    });
    document.querySelectorAll('.custom-select-options').forEach(options => {
        options.classList.remove('show');
    });
}

function updateStudentsEmptyState() {
    if (!studentsTableWrapper) {
        return;
    }
    if (!studentList || studentList.length === 0) {
        studentsTableWrapper.classList.add('empty');
        if (studentsCountLabel) {
            studentsCountLabel.textContent = '0';
        }
    } else {
        studentsTableWrapper.classList.remove('empty');
        if (studentsCountLabel) {
            studentsCountLabel.textContent = String(studentList.length);
        }
    }
}

function formatScore(score) {
    if (typeof score !== 'number' || Number.isNaN(score)) {
        return '--';
    }
    return score.toFixed(2);
}

function getScoreColor(score) {
    if (typeof score !== 'number' || Number.isNaN(score)) {
        return 'var(--color-border)';
    }
    const clamped = Math.max(0, Math.min(1, score));
    const start = [231, 76, 60];
    const end = [31, 132, 89];
    const rgb = start.map((value, index) => Math.round(value + (end[index] - value) * clamped));
    return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

// 将部分函数暴露到全局以供其他脚本使用
window.renderMathContent = renderMathContent;
window.renderMath = renderMath;
window.formatDate = formatDate;
window.handleLogout = handleLogout;
window.showLoading = showLoading;
window.showMessage = showMessage;
window.hideMessage = hideMessage;
window.openModalElement = openModalElement;
window.closeModalElement = closeModalElement;
window.attachModalBackdropHandler = attachModalBackdropHandler;
window.resetAddStudentForm = resetAddStudentForm;
window.resetHomeworkState = resetHomeworkState;
window.initCustomSelects = initCustomSelects;
window.closeAllCustomSelects = closeAllCustomSelects;
window.updateStudentsEmptyState = updateStudentsEmptyState;
window.formatScore = formatScore;
window.getScoreColor = getScoreColor;

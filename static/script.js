// 全局变量
let currentPage = 1;
let totalPages = 1;
let availableTags = [];
let currentQuestions = [];
let uploadedImages = [];
let parsedQuestions = [];
let cart = []; // 购物车
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

const STUDENT_ANALYTICS_WINDOW_DAYS = 30;

// DOM元素
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
const questionTypeSelect = document.getElementById('question-type');
const prevPageBtn = document.getElementById('prev-page');
const nextPageBtn = document.getElementById('next-page');
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
const modalTagsSection = document.getElementById('modal-tags-section');

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

// 图片上传相关
const imageUpload = document.getElementById('image-upload');
const uploadBtn = document.getElementById('upload-btn');
const imagePreview = document.getElementById('image-preview');

// 试卷解析相关
const examUpload = document.getElementById('exam-upload');
const examUploadBtn = document.getElementById('exam-upload-btn');
const examPreview = document.getElementById('exam-preview');
const parseExamBtn = document.getElementById('parse-exam-btn');
const parsedQuestionsDiv = document.getElementById('parsed-questions');
const parsedQuestionsList = document.getElementById('parsed-questions-list');
const batchSaveBtn = document.getElementById('batch-save-btn');

// 状态栏和购物车相关
const logoutBtn = document.getElementById('logout-btn');
const cartIcon = document.getElementById('cart-icon');
const cartBadge = document.getElementById('cart-badge');
const cartModal = document.getElementById('cart-modal');
const cartModalClose = document.getElementById('cart-modal-close');
const clearCartBtn = document.getElementById('clear-cart-btn');
const exportPaperBtn = document.getElementById('export-paper-btn');

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// 初始化应用
async function initializeApp() {
    // 检查登录状态
    await checkLoginStatus();
    
    setupEventListeners();
    
    // 加载标签
    await loadAvailableTags();
    
    // 加载统计信息
    await loadStats();
    
    // 根据当前激活的标签页加载相应内容
    const activeTab = document.querySelector('.nav-tab.active');
    if (activeTab) {
        const tabName = activeTab.dataset.tab;
        if (tabName === 'manage') {
            await loadQuestions();
        } else if (tabName === 'students') {
            await loadStudents();
        }
        // 不再自动加载搜索页面的题目
    }
    
    // 初始化MathJax
    setTimeout(() => {
        renderMath();
    }, 100);
    
    // 更新购物车显示
    updateCartBadge();
}

// 检查登录状态
async function checkLoginStatus() {
    try {
        const response = await fetch('/api/auth/current');
        const result = await response.json();
        
        if (result.success) {
            currentUser = result.user;
            document.getElementById('current-username').textContent = currentUser.username;
        } else {
            window.location.href = '/login';
        }
    } catch (error) {
        window.location.href = '/login';
    }
}

// 加载统计信息
async function loadStats() {
    try {
        const response = await fetch('/api/questions/stats');
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('total-questions').textContent = result.stats.total;
        }
    } catch (error) {
        console.error('加载统计信息失败:', error);
    }
}

// 设置事件监听器
function setupEventListeners() {
    // 导航标签切换
    navTabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // 表单提交
    if (questionForm) {
        questionForm.addEventListener('submit', handleFormSubmit);
    }
    
    // 自动打标按钮
    if (autoTagBtn) {
        autoTagBtn.addEventListener('click', handleAutoTag);
    }
    
    // 搜索按钮
    if (searchBtn) {
        searchBtn.addEventListener('click', handleSearch);
    }
    
    // 刷新按钮
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadQuestions);
    }
    
    // 分页按钮
    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', () => changePage(-1));
    }
    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', () => changePage(1));
    }
    
    // 模态框关闭
    if (questionModalClose) {
        questionModalClose.addEventListener('click', closeQuestionModal);
    }
    if (questionModal) {
        questionModal.addEventListener('click', (e) => {
            if (e.target === questionModal) closeQuestionModal();
        });
    }
    
    // 消息关闭
    messageClose.addEventListener('click', hideMessage);
    
    // 回车键搜索
    searchKeyword.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
    
    // 图片上传
    uploadBtn.addEventListener('click', () => imageUpload.click());
    imageUpload.addEventListener('change', handleImageUpload);
    
    // 试卷上传
    examUploadBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // 阻止事件冒泡，避免触发uploadZone的点击事件
        examUpload.click();
    });
    examUpload.addEventListener('change', handleExamUpload);
    parseExamBtn.addEventListener('click', handleParseExam);
    
    // 拖拽上传
    const uploadZone = document.getElementById('upload-zone');
    uploadZone.addEventListener('click', (e) => {
        // 如果点击的是按钮或其他子元素，不触发文件选择
        if (e.target === uploadZone || e.target.closest('.upload-icon') || e.target.tagName === 'H3' || e.target.tagName === 'P') {
            examUpload.click();
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
            handleExamUpload({ target: { files: files } });
        }
    });
    
    // 移除试卷按钮
    document.getElementById('remove-exam-btn').addEventListener('click', removeExam);
    
    // 批量保存
    batchSaveBtn.addEventListener('click', handleBatchSave);
    
    // 登出按钮
    logoutBtn.addEventListener('click', handleLogout);
    
    // 购物车图标
    cartIcon.addEventListener('click', openCartModal);
    cartModalClose.addEventListener('click', closeCartModal);
    cartModal.addEventListener('click', (e) => {
        if (e.target === cartModal) closeCartModal();
    });
    
    // 购物车操作
    clearCartBtn.addEventListener('click', clearCart);
    exportPaperBtn.addEventListener('click', exportPaper);

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
                handleHomeworkFileUpload({ target: { files: files } });
            }
        });
    }
    if (homeworkFileInput) {
        homeworkFileInput.addEventListener('change', handleHomeworkFileUpload);
    }
    if (removeHomeworkBtn) {
        removeHomeworkBtn.addEventListener('click', removeHomeworkFile);
    }
    // 初始化自定义下拉列表
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

// 登出
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

// 切换标签页
function switchTab(tabName) {
    // 更新导航标签
    navTabs.forEach(tab => tab.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    
    // 更新内容
    tabContents.forEach(content => content.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // 根据标签页执行相应操作
    if (tabName === 'manage') {
        loadQuestions();
    } else if (tabName === 'students') {
        loadStudents();
    } else if (tabName === 'search') {
        // 不再自动加载题目，只在用户触发搜索时显示结果
        if (availableTags.length > 0) {
            renderTagFilter();
        }
        // 隐藏搜索结果区域
        searchResults.innerHTML = '';
        searchResults.style.display = 'none';
    }
}

// 加载可用标签
async function loadAvailableTags() {
    try {
        const response = await fetch('/api/tags');
        const data = await response.json();
        
        if (data.success) {
            availableTags = data.tags;
            renderTagSelector();
            renderTagFilter();
        }
    } catch (error) {
        showMessage('加载标签失败: ' + error.message, 'error');
    }
}

// 渲染标签选择器
function renderTagSelector() {
    tagSelector.innerHTML = '';
    availableTags.forEach(tag => {
        const tagElement = document.createElement('div');
        tagElement.className = 'tag-item';
        tagElement.innerHTML = `
            <input type="checkbox" value="${tag}">
            <span>${tag}</span>
        `;
        tagElement.addEventListener('click', () => toggleTag(tagElement));
        tagSelector.appendChild(tagElement);
    });
}

// 渲染标签过滤器
function renderTagFilter() {
    tagFilter.innerHTML = '';
    availableTags.forEach(tag => {
        const tagElement = document.createElement('div');
        tagElement.className = 'tag-item';
        tagElement.innerHTML = `
            <input type="checkbox" value="${tag}">
            <span>${tag}</span>
        `;
        tagElement.addEventListener('click', () => toggleTag(tagElement));
        tagFilter.appendChild(tagElement);
    });
}

// 切换标签选择
function toggleTag(tagElement) {
    tagElement.classList.toggle('selected');
    const checkbox = tagElement.querySelector('input[type="checkbox"]');
    checkbox.checked = !checkbox.checked;
}

// 获取选中的标签
function getSelectedTags(container) {
    const selectedTags = [];
    const checkboxes = container.querySelectorAll('input[type="checkbox"]:checked');
    checkboxes.forEach(checkbox => {
        selectedTags.push(checkbox.value);
    });
    return selectedTags;
}

// 处理表单提交
async function handleFormSubmit(e) {
    e.preventDefault();
    
    const formData = new FormData(questionForm);
    const selectedTags = getSelectedTags(tagSelector);
    const visibility = document.querySelector('input[name="visibility"]:checked').value;
    
    const questionTypeValue = document.getElementById('question-type')?.value || '解答题';

    const questionData = {
        latex_content: formData.get('latex_content'),
        tags: selectedTags,
        reference_answer: formData.get('reference_answer'),
        source: formData.get('source'),
        image: uploadedImages,
        visibility: visibility,
        question_type: questionTypeValue
    };
    
    if (!questionData.latex_content.trim()) {
        showMessage('请输入题目内容', 'error');
        return;
    }
    
    try {
        showLoading(true);
        
        const response = await fetch('/api/questions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(questionData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showMessage('题目添加成功！', 'success');
            questionForm.reset();
            uploadedImages = [];
            imagePreview.innerHTML = '';
            const questionTypeHidden = document.getElementById('question-type');
            const questionTypeSelectEl = document.getElementById('question-type-select');
            if (questionTypeHidden) {
                questionTypeHidden.value = '解答题';
            }
            if (questionTypeSelectEl) {
                const valueSpan = questionTypeSelectEl.querySelector('.custom-select-value');
                if (valueSpan) {
                    valueSpan.textContent = '解答题';
                }
                questionTypeSelectEl.querySelectorAll('.custom-select-option').forEach(opt => {
                    opt.classList.remove('selected');
                    if (opt.dataset.value === '解答题') {
                        opt.classList.add('selected');
                    }
                });
            }
            // 清除标签选择
            tagSelector.querySelectorAll('.tag-item').forEach(tag => {
                tag.classList.remove('selected');
                tag.querySelector('input[type="checkbox"]').checked = false;
            });
            // 重新加载统计
            await loadStats();
        } else {
            showMessage('添加失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('添加失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 处理自动打标
async function handleAutoTag() {
    const content = document.getElementById('latex-content').value;
    const source = document.getElementById('source').value;
    
    if (!content.trim()) {
        showMessage('请先输入题目内容', 'error');
        return;
    }
    
    try {
        showLoading(true);
        
        const response = await fetch('/api/questions/auto-tag', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                source: source
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // 设置LaTeX格式化的题目内容
            if (result.latex_content) {
                document.getElementById('latex-content').value = result.latex_content;
            }
            
            // 设置标签
            const selectedTags = result.tags;
            tagSelector.querySelectorAll('.tag-item').forEach(tagElement => {
                const checkbox = tagElement.querySelector('input[type="checkbox"]');
                const tagValue = checkbox.value;
                
                if (selectedTags.includes(tagValue)) {
                    tagElement.classList.add('selected');
                    checkbox.checked = true;
                } else {
                    tagElement.classList.remove('selected');
                    checkbox.checked = false;
                }
            });
            
            // 设置参考解答
            document.getElementById('reference-answer').value = result.answer;

            const questionTypeHidden = document.getElementById('question-type');
            const questionTypeSelectEl = document.getElementById('question-type-select');
            if (questionTypeSelectEl && questionTypeHidden) {
                const allowedTypes = ['选择题', '填空题', '解答题'];
                const modelType = (result.question_type || '').trim();
                const selectedType = allowedTypes.includes(modelType) ? modelType : '解答题';
                questionTypeHidden.value = selectedType;
                const valueSpan = questionTypeSelectEl.querySelector('.custom-select-value');
                if (valueSpan) {
                    valueSpan.textContent = selectedType;
                }
                questionTypeSelectEl.querySelectorAll('.custom-select-option').forEach(opt => {
                    opt.classList.remove('selected');
                    if (opt.dataset.value === selectedType) {
                        opt.classList.add('selected');
                    }
                });
            }
            
            showMessage('自动打标和LaTeX格式化完成！', 'success');
        } else {
            showMessage('自动打标失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('自动打标失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 加载所有题目（用于搜索页面默认显示）
async function loadAllQuestions() {
    try {
        showLoading(true);
        
        const response = await fetch('/api/questions/search');
        const result = await response.json();
        
        if (result.success) {
            currentQuestions = result.questions;
            renderSearchResults();
        } else {
            showMessage('加载题目失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('加载题目失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 处理搜索
async function handleSearch() {
    const keyword = searchKeyword.value.trim();
    const selectedTags = getSelectedTags(tagFilter);
    
    // 显示搜索按钮的旋转图标
    const searchIcon = searchBtn.querySelector('i');
    const originalClass = searchIcon.className;
    searchIcon.className = 'fas fa-spinner fa-spin';
    searchBtn.disabled = true;
    
    try {
        let url = '/api/questions/search?';
        const params = new URLSearchParams();
        
        if (keyword) {
            params.append('keyword', keyword);
        }
        
        if (selectedTags.length > 0) {
            selectedTags.forEach(tag => {
                params.append('tags', tag);
            });
        }
        
        url += params.toString();
        
        const response = await fetch(url);
        const result = await response.json();
        
        if (result.success) {
            currentQuestions = result.questions;
            renderSearchResults();
        } else {
            showMessage('搜索失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('搜索失败: ' + error.message, 'error');
    } finally {
        searchIcon.className = originalClass;
        searchBtn.disabled = false;
    }
}

// 渲染搜索结果（与题目预览保持一致的样式）
function renderSearchResults() {
    // 显示搜索结果区域
    searchResults.style.display = 'block';
    
    if (currentQuestions.length === 0) {
        searchResults.innerHTML = '<div class="no-results">没有找到相关题目</div>';
        return;
    }
    
    searchResults.innerHTML = currentQuestions.map(question => `
        <div class="question-item">
            <div class="question-header">
                <div class="question-meta-row">
                    <div class="question-left">
                        <span class="question-id">#${question.id}</span>
                        <span class="question-type-badge">${question.question_type || '解答题'}</span>
                        <div class="question-tags">
                            ${question.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')}
                        </div>
                    </div>
                    <div class="question-right">
                        <small>${question.source || '未知'} | ${formatDate(question.created_at)}</small>
                    </div>
                </div>
            </div>
            <div class="question-content">
                ${renderMathContent(question.latex_content)}
            </div>
            <div class="question-actions">
                <button class="btn btn-primary btn-sm" onclick="viewQuestion(${question.id})">
                    <i class="fas fa-eye"></i> 查看详情
                </button>
                <button class="btn btn-add-cart btn-sm" onclick="addToCart(${question.id})">
                    <i class="fas fa-plus"></i> 加入试卷
                </button>
            </div>
        </div>
    `).join('');
    
    // 重新渲染数学公式
    renderMath();
}

// 加载题目列表
async function loadQuestions() {
    try {
        showLoading(true);
        
        const response = await fetch(`/api/questions/search?page=${currentPage}&limit=10`);
        const result = await response.json();
        
        if (result.success) {
            currentQuestions = result.questions;
            totalPages = Math.ceil(result.total / 10);
            renderQuestionList();
            updatePagination();
        } else {
            showMessage('加载题目失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('加载题目失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 渲染题目列表
function renderQuestionList() {
    if (currentQuestions.length === 0) {
        questionList.innerHTML = '<div class="no-results">暂无题目</div>';
        return;
    }
    
    questionList.innerHTML = currentQuestions.map(question => `
        <div class="question-item">
            <div class="question-header">
                <div class="question-meta-row">
                    <div class="question-left">
                        <span class="question-id">#${question.id}</span>
                        <span class="question-type-badge">${question.question_type || '解答题'}</span>
                        <div class="question-tags">
                            ${question.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')}
                        </div>
                    </div>
                    <div class="question-right">
                        <small>${question.source || '未知'} | ${formatDate(question.created_at)}</small>
                    </div>
                </div>
            </div>
            <div class="question-content">
                ${renderMathContent(question.latex_content)}
            </div>
            <div class="question-actions">
                <button class="btn btn-primary btn-sm" onclick="viewQuestion(${question.id})">
                    <i class="fas fa-eye"></i> 查看详情
                </button>
                <button class="btn btn-add-cart btn-sm" onclick="addToCart(${question.id})">
                    <i class="fas fa-plus"></i> 加入试卷
                </button>
                <button class="btn btn-danger btn-sm" onclick="deleteQuestion(${question.id})">
                    <i class="fas fa-trash"></i> 删除题目
                </button>
            </div>
        </div>
    `).join('');
    
    // 更新计数
    currentCount.textContent = currentQuestions.length;
    totalCount.textContent = currentQuestions.length;
    
    // 重新渲染数学公式
    renderMath();
}

// 查看题目详情
async function viewQuestion(questionId) {
    try {
        showLoading(true);
        const response = await fetch(`/api/questions/${questionId}`);
        const result = await response.json();
        
        if (!result.success) {
            showMessage('获取题目详情失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        openQuestionModal(result.question);
    } catch (error) {
        showMessage('获取题目详情失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}


// 关闭题目详情模态框
function closeQuestionModal() {
    if (!questionModal) {
        return;
    }
    if (modalState.isEditing && modalState.original) {
        exitEditMode(true);
    }
    questionModal.style.display = 'none';
    resetModalState();
}

// 切换页面
function changePage(direction) {
    const newPage = currentPage + direction;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        loadQuestions();
    }
}

// 更新分页信息
function updatePagination() {
    pageInfo.textContent = `第 ${currentPage} 页`;
    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages;
}

function openQuestionModal(question) {
    if (!question) {
        return;
    }

    modalState.questionId = question.id;
    modalState.original = question;
    modalState.aiSuggested = false;
    modalState.isEditing = false;
    modalState.draft = {
        latex_content: question.latex_content || '',
        reference_answer: question.reference_answer || '',
        question_type: question.question_type || '解答题'
    };

    renderModalContent(question);
    updateModalEditingUI();
    questionModal.style.display = 'block';
    renderMath();
}

function renderModalContent(question) {
    if (!question) {
        if (modalQuestionContent) {
            modalQuestionContent.innerHTML = '';
        }
        if (modalQuestionAnswer) {
            modalQuestionAnswer.innerHTML = '';
        }
        if (modalQuestionEditor) {
            modalQuestionEditor.value = '';
        }
        if (modalAnswerEditor) {
            modalAnswerEditor.value = '';
        }
        if (modalQuestionType) {
            modalQuestionType.textContent = '';
        }
        return;
    }

    const latexContent = question.latex_content || '';
    let contentHtml = renderMathContent(latexContent);

    const questionTypeLabel = question.question_type || '解答题';
    if (modalQuestionType) {
        modalQuestionType.textContent = `题型：${questionTypeLabel}`;
    }

    if (question.image && question.image.length > 0) {
        const imageScale = APP_CONFIG.imageDisplay.defaultScale;
        const imagesHtml = question.image.map(img => {
            let imageSrc = img;
            if (imageSrc.startsWith('/uploads/')) {
                imageSrc = imageSrc.replace('/uploads/', '/images/');
            }
            return `<img src="${imageSrc}" alt="题目图片" style="max-width: ${imageScale * 100}%;">`;
        }).join('');
        contentHtml += `<div class="question-images">${imagesHtml}</div>`;
    }

    if (modalQuestionContent) {
        modalQuestionContent.innerHTML = contentHtml || '<p class="modal-annotation">暂无题面内容</p>';
    }

    const answerContent = question.reference_answer || '';
    if (modalQuestionAnswer) {
        if (answerContent) {
            modalQuestionAnswer.innerHTML = renderMathContent(answerContent);
        } else {
            modalQuestionAnswer.innerHTML = '<p class="modal-annotation">暂无参考解答</p>';
        }
    }

    populateModalTags(question.tags || []);

    if (modalQuestionEditor) {
        modalQuestionEditor.value = modalState.draft.latex_content ?? latexContent;
    }
    if (modalAnswerEditor) {
        modalAnswerEditor.value = modalState.draft.reference_answer ?? answerContent;
    }
}

function populateModalTags(tags) {
    if (!modalQuestionTags || !modalTagsSection) {
        return;
    }

    if (!tags || tags.length === 0) {
        modalTagsSection.classList.add('hidden');
        modalQuestionTags.innerHTML = '<span class="modal-annotation">暂无标签</span>';
        return;
    }

    modalTagsSection.classList.remove('hidden');
    modalQuestionTags.innerHTML = tags.map(tag => `<span class="modal-tag-chip"><i class="fas fa-hashtag"></i>${tag}</span>`).join('');
}

function handleEditQuestion() {
    if (!modalState.original || saveEditLoading || aiVariantLoading) {
        return;
    }
    enterEditMode();
}

function enterEditMode(options = {}) {
    if (!modalState.original) {
        return;
    }

    const preserveDraft = options.preserveDraft === true;
    if (!preserveDraft) {
        modalState.draft = {
            latex_content: modalState.original.latex_content || '',
            reference_answer: modalState.original.reference_answer || '',
            question_type: modalState.original.question_type || '解答题'
        };
    }

    modalState.isEditing = true;
    updateModalEditingUI();

    if (modalQuestionEditor) {
        modalQuestionEditor.focus({ preventScroll: false });
        const length = modalQuestionEditor.value.length;
        modalQuestionEditor.setSelectionRange(length, length);
    }
}

function handleCancelEdit() {
    if (!modalState.isEditing) {
        return;
    }
    exitEditMode(true);
    showMessage('已取消修改', 'warning');
}

async function handleSaveQuestion() {
    if (!modalState.isEditing || !modalState.questionId || saveEditLoading) {
        return;
    }

    const updatedLatex = (modalQuestionEditor.value || '').trim();
    const updatedAnswer = modalAnswerEditor.value ? modalAnswerEditor.value.trim() : '';

    if (!updatedLatex) {
        showMessage('题目内容不能为空', 'error');
        modalQuestionEditor.focus();
        return;
    }

    try {
        setSaveButtonLoading(true);
        const response = await fetch(`/api/questions/${modalState.questionId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                latex_content: updatedLatex,
                reference_answer: updatedAnswer,
                question_type: modalState.original?.question_type || '解答题'
            })
        });

        const result = await response.json();
        if (!result.success) {
            showMessage('保存失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        const updatedQuestion = result.question || result.data || {
            ...modalState.original,
            latex_content: updatedLatex,
            reference_answer: updatedAnswer
        };

        exitEditMode(false, updatedQuestion);
        refreshQuestionCollections(updatedQuestion);
        showMessage('题目已更新', 'success');
    } catch (error) {
        showMessage('保存失败: ' + error.message, 'error');
    } finally {
        setSaveButtonLoading(false);
    }
}

function exitEditMode(resetDraft = false, updatedQuestion = null) {
    if (resetDraft && modalState.original) {
        modalState.draft = {
            latex_content: modalState.original.latex_content || '',
            reference_answer: modalState.original.reference_answer || '',
            question_type: modalState.original.question_type || '解答题'
        };
        modalState.aiSuggested = false;
    }

    if (updatedQuestion) {
        modalState.original = updatedQuestion;
        modalState.draft = {
            latex_content: updatedQuestion.latex_content || '',
            reference_answer: updatedQuestion.reference_answer || '',
            question_type: updatedQuestion.question_type || '解答题'
        };
        modalState.aiSuggested = false;
    }

    modalState.isEditing = false;
    if (modalState.original) {
        renderModalContent(modalState.original);
    }
    updateModalEditingUI();
    renderMath();
}

function updateModalEditingUI() {
    const editing = modalState.isEditing;

    if (modalQuestionContent) {
        modalQuestionContent.classList.toggle('hidden', editing);
    }
    if (modalQuestionEditor) {
        modalQuestionEditor.classList.toggle('hidden', !editing);
        if (editing) {
            modalQuestionEditor.value = modalState.draft.latex_content || '';
        }
    }
    if (modalQuestionAnswer) {
        modalQuestionAnswer.classList.toggle('hidden', editing);
    }
    if (modalAnswerEditor) {
        modalAnswerEditor.classList.toggle('hidden', !editing);
        if (editing) {
            modalAnswerEditor.value = modalState.draft.reference_answer || '';
        }
    }
    if (editQuestionBtn) {
        editQuestionBtn.classList.toggle('hidden', !modalState.original || editing);
        editQuestionBtn.disabled = !modalState.original || aiVariantLoading || saveEditLoading;
    }
    if (cancelEditBtn) {
        cancelEditBtn.classList.toggle('hidden', !editing);
        cancelEditBtn.disabled = saveEditLoading;
    }
    if (saveQuestionBtn && !saveEditLoading) {
        saveQuestionBtn.classList.toggle('hidden', !editing);
    }
    if (modalEditHint) {
        modalEditHint.classList.toggle('hidden', !editing);
    }
    if (aiVariantBtn && !aiVariantLoading) {
        aiVariantBtn.disabled = !modalState.original || saveEditLoading;
    }
}

function setSaveButtonLoading(isLoading) {
    saveEditLoading = isLoading;
    if (!saveQuestionBtn) {
        return;
    }
    if (isLoading) {
        saveQuestionBtn.disabled = true;
        saveQuestionBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 保存中...';
        saveQuestionBtn.classList.remove('hidden');
    } else {
        saveQuestionBtn.disabled = false;
        saveQuestionBtn.innerHTML = '<i class="fas fa-save"></i> 保存修改';
        saveQuestionBtn.classList.toggle('hidden', !modalState.isEditing);
    }
    if (typeof updateModalEditingUI === 'function') {
        updateModalEditingUI();
    }
}

async function handleAiVariant() {
    if (!modalState.questionId || aiVariantLoading) {
        return;
    }

    try {
        setAiVariantLoading(true);
        showLoading(true);

        const payload = {
            latex_content: modalState.isEditing ? (modalQuestionEditor.value || '') : (modalState.original?.latex_content || ''),
            reference_answer: modalState.isEditing ? (modalAnswerEditor.value || '') : (modalState.original?.reference_answer || '')
        };

        const response = await fetch(`/api/questions/${modalState.questionId}/ai-variant`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        if (!result.success) {
            showMessage('AI变题失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        const variant = result.variant || result.data || {};
        const newLatex = variant.latex_content || modalState.draft.latex_content || modalState.original?.latex_content || '';
        const newAnswer = variant.reference_answer ?? variant.answer ?? modalState.draft.reference_answer ?? modalState.original?.reference_answer ?? '';

        modalState.draft = {
            latex_content: newLatex,
            reference_answer: newAnswer,
            question_type: (variant.question_type || modalState.original?.question_type || '解答题')
        };
        modalState.aiSuggested = true;
        modalState.isEditing = true;

        const previewQuestion = {
            ...modalState.original,
            latex_content: newLatex,
            reference_answer: newAnswer,
            tags: Array.isArray(variant.tags) ? variant.tags : (modalState.original?.tags || []),
            question_type: modalState.draft.question_type || modalState.original?.question_type || '解答题'
        };

        renderModalContent(previewQuestion);
        updateModalEditingUI();
        if (modalQuestionEditor) {
            modalQuestionEditor.focus({ preventScroll: false });
        }
        renderMath();
        showMessage('已生成新的题目草稿，请确认后保存。', 'success');
    } catch (error) {
        showMessage('AI变题失败: ' + error.message, 'error');
    } finally {
        setAiVariantLoading(false);
        showLoading(false);
    }
}

function setAiVariantLoading(isLoading) {
    aiVariantLoading = isLoading;
    if (!aiVariantBtn) {
        return;
    }
    if (isLoading) {
        aiVariantBtn.disabled = true;
        aiVariantBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在生成...';
    } else {
        aiVariantBtn.disabled = !modalState.original || saveEditLoading;
        aiVariantBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> AI 变题';
    }
    if (typeof updateModalEditingUI === 'function') {
        updateModalEditingUI();
    }
}

function refreshQuestionCollections(updatedQuestion) {
    if (!updatedQuestion) {
        return;
    }

    const updateList = (list, updater) => {
        if (!Array.isArray(list)) {
            return;
        }
        const index = list.findIndex(item => item && item.id === updatedQuestion.id);
        if (index !== -1) {
            list[index] = { ...list[index], ...updatedQuestion };
            if (typeof updater === 'function') {
                updater();
            }
        }
    };

    updateList(currentQuestions, () => {
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            if (activeTab.id === 'manage-tab') {
                renderQuestionList();
            } else if (activeTab.id === 'search-tab') {
                renderSearchResults();
            }
        }
    });

    cart = cart.map(item => {
        if (item && item.id === updatedQuestion.id) {
            return { ...item, ...updatedQuestion };
        }
        return item;
    });
    updateCartBadge();
    if (cartModal.style.display === 'block') {
        renderCart();
    }
}

function resetModalState() {
    modalState.questionId = null;
    modalState.original = null;
    modalState.isEditing = false;
    modalState.aiSuggested = false;
    modalState.draft = {
        latex_content: '',
        reference_answer: '',
        question_type: '解答题'
    };

    if (modalQuestionContent) {
        modalQuestionContent.innerHTML = '';
    }
    if (modalQuestionTags) {
        modalQuestionTags.innerHTML = '';
    }
    if (modalQuestionAnswer) {
        modalQuestionAnswer.innerHTML = '';
    }
    if (modalQuestionEditor) {
        modalQuestionEditor.value = '';
        modalQuestionEditor.classList.add('hidden');
    }
    if (modalAnswerEditor) {
        modalAnswerEditor.value = '';
        modalAnswerEditor.classList.add('hidden');
    }
    if (modalEditHint) {
        modalEditHint.classList.add('hidden');
    }
    if (modalTagsSection) {
        modalTagsSection.classList.remove('hidden');
    }

    setSaveButtonLoading(false);
    setAiVariantLoading(false);
    updateModalEditingUI();
}

// 渲染数学内容
function renderMathContent(content) {
    if (!content) return '';
    
    // 使用占位符方法避免HTML转义问题
    let processed = content;
    
    // 定义占位符
    const placeholders = {
        olStart: '___MATHJAX_OL_START___',
        olEnd: '___MATHJAX_OL_END___',
        ulStart: '___MATHJAX_UL_START___',
        ulEnd: '___MATHJAX_UL_END___',
        liItem: '___MATHJAX_LI_ITEM___'
    };
    
    // 第一步：将LaTeX环境替换为占位符
    processed = processed.replace(/\\begin\{enumerate\}/g, placeholders.olStart);
    processed = processed.replace(/\\end\{enumerate\}/g, placeholders.olEnd);
    processed = processed.replace(/\\begin\{itemize\}/g, placeholders.ulStart);
    processed = processed.replace(/\\end\{itemize\}/g, placeholders.ulEnd);
    processed = processed.replace(/\\item\s*/g, placeholders.liItem);
    
    // 第二步：转义HTML特殊字符
    let escaped = processed
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
    
    // 第三步：将占位符替换为HTML标签
    escaped = escaped.replace(new RegExp(placeholders.olStart, 'g'), '<ol class="math-enumerate">');
    escaped = escaped.replace(new RegExp(placeholders.olEnd, 'g'), '</ol>');
    escaped = escaped.replace(new RegExp(placeholders.ulStart, 'g'), '<ul class="math-itemize">');
    escaped = escaped.replace(new RegExp(placeholders.ulEnd, 'g'), '</ul>');
    escaped = escaped.replace(new RegExp(placeholders.liItem, 'g'), '<li class="math-item">');
    
    // 处理换行
    escaped = escaped.replace(/\n/g, '<br>');
    
    return escaped;
}

// 重新渲染数学公式
function renderMath() {
    if (window.MathJax) {
        MathJax.typesetPromise().catch((err) => {
            console.log('MathJax渲染错误:', err);
        });
    }
}

// 格式化日期
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN');
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
function showMessage(text, type = 'success') {
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

function openModalElement(modal) {
    if (!modal) {
        return;
    }
    modal.style.display = 'block';
}

function closeModalElement(modal) {
    if (!modal) {
        return;
    }
    modal.style.display = 'none';

    if (modal === addStudentModal) {
        resetAddStudentForm();
    }

    if (modal === homeworkModal) {
        resetHomeworkState();
    }
}

function attachModalBackdropHandler(modal, onClose) {
    if (!modal) {
        return;
    }
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

function handleHomeworkFileUpload(e) {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            if (homeworkUploadZone) {
                homeworkUploadZone.style.display = 'none';
            }
            if (homeworkPreview) {
                homeworkPreview.style.display = 'block';
                const previewImage = homeworkPreview.querySelector('.preview-image');
                if (previewImage) {
                    previewImage.innerHTML = `<img src="${e.target.result}" alt="作业预览">`;
                }
            }
        };
        reader.readAsDataURL(file);
    }
}

function removeHomeworkFile() {
    if (homeworkFileInput) {
        homeworkFileInput.value = '';
    }
    if (homeworkUploadZone) {
        homeworkUploadZone.style.display = 'block';
    }
    if (homeworkPreview) {
        homeworkPreview.style.display = 'none';
    }
}

// 初始化自定义下拉列表
function initCustomSelects() {
    // 题目类型下拉列表
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

    // 试卷选择下拉列表
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

    // 点击外部关闭下拉列表
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
    } else {
        studentsTableWrapper.classList.remove('empty');
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

// 处理图片上传
async function handleImageUpload(e) {
    const files = Array.from(e.target.files);
    
    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            showLoading(true);
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (result.success) {
                uploadedImages.push(result.url);
                addImagePreview(result.url, file.name);
            } else {
                showMessage('图片上传失败: ' + result.message, 'error');
            }
        } catch (error) {
            showMessage('图片上传失败: ' + error.message, 'error');
        } finally {
            showLoading(false);
        }
    }
}

// 添加图片预览
function addImagePreview(url, filename) {
    const previewItem = document.createElement('div');
    previewItem.className = 'image-preview-item';
    previewItem.innerHTML = `
        <img src="${url}" alt="${filename}">
        <button type="button" class="remove-btn" onclick="removeImage('${url}')">&times;</button>
    `;
    imagePreview.appendChild(previewItem);
}

// 移除图片
function removeImage(url) {
    uploadedImages = uploadedImages.filter(img => img !== url);
    const previewItems = imagePreview.querySelectorAll('.image-preview-item');
    previewItems.forEach(item => {
        if (item.querySelector('img').src === url) {
            item.remove();
        }
    });
}

// 处理试卷上传
function handleExamUpload(e) {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            document.getElementById('upload-zone').style.display = 'none';
            examPreview.style.display = 'block';
            examPreview.querySelector('.preview-image').innerHTML = `<img src="${e.target.result}" alt="试卷预览">`;
        };
        reader.readAsDataURL(file);
    }
}

// 移除试卷
function removeExam() {
    document.getElementById('upload-zone').style.display = 'block';
    examPreview.style.display = 'none';
    examUpload.value = '';
    parsedQuestionsDiv.style.display = 'none';
}

// 处理试卷解析
async function handleParseExam() {
    const file = examUpload.files[0];
    if (!file) {
        showMessage('请先选择试卷图片', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    // 替换按钮为进度按钮
    const parseBtn = parseExamBtn;
    const originalBtnText = parseBtn.innerHTML;
    parseBtn.disabled = true;
    parseBtn.classList.add('parsing');
    
    let progress = 0;
    const config = APP_CONFIG.parsingProgress;
    const progressInterval = setInterval(() => {
        progress += config.increment;
        if (progress > config.maxProgress) {
            progress = config.maxProgress;
        }
        parseBtn.innerHTML = `<i class="fas fa-cog fa-spin"></i> 正在解析 ${progress}%`;
    }, config.interval);
    
    try {
        console.log('开始解析试卷...');
        
        const response = await fetch('/api/ocr-parse', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        console.log('解析结果:', result);
        
        // 停止进度条
        clearInterval(progressInterval);
        parseBtn.innerHTML = `<i class="fas fa-cogs"></i> 开始解析`;
        parseBtn.disabled = false;
        parseBtn.classList.remove('parsing');
        
        if (result.success) {
            parsedQuestions = result.questions || [];
            console.log('解析出的题目数量:', parsedQuestions.length);
            console.log('题目详情:', parsedQuestions);
            
            // 检查每个题目的图片信息
            parsedQuestions.forEach((question, index) => {
                if (question.image && question.image.length > 0) {
                    console.log(`题目 ${index + 1} 的图片:`, question.image);
                }
            });
            
            if (parsedQuestions.length === 0) {
                showMessage('试卷解析完成，但没有识别出任何题目', 'warning');
                parsedQuestionsDiv.style.display = 'none';
            } else {
                renderParsedQuestions();
                parsedQuestionsDiv.style.display = 'block';
                document.getElementById('parsed-count').textContent = parsedQuestions.length;
                showMessage(`试卷解析成功！共识别出 ${parsedQuestions.length} 道题目`, 'success');
            }
        } else {
            console.error('解析失败:', result.message);
            showMessage('试卷解析失败: ' + result.message, 'error');
        }
    } catch (error) {
        console.error('解析过程中发生错误:', error);
        clearInterval(progressInterval);
        parseBtn.innerHTML = originalBtnText;
        parseBtn.disabled = false;
        parseBtn.classList.remove('parsing');
        showMessage('试卷解析失败: ' + error.message, 'error');
    }
}

// 渲染解析出的题目
function renderParsedQuestions() {
    if (!parsedQuestions || parsedQuestions.length === 0) {
        parsedQuestionsList.innerHTML = '<div class="no-results">没有解析出任何题目</div>';
        return;
    }
    
    parsedQuestionsList.innerHTML = parsedQuestions.map((question, index) => {
        // 确保题目对象有必要的字段
        const questionText = question.question || question.latex_content || '题目内容缺失';
        const questionImages = question.image || [];
        const questionTags = question.tags || [];
        const questionAnswer = question.answer || '';
        
        return `
            <div class="parsed-question-item">
                <h5>
                    <input type="checkbox" checked data-index="${index}" style="margin-right: 10px;">
                    题目 ${index + 1}
                </h5>
                <div class="parsed-question-content">
                    ${renderMathContent(questionText)}
                </div>
                <div class="parsed-meta"><strong>题型：</strong>${question.question_type || '解答题'}</div>
                ${questionImages.length > 0 ? `
                    <div class="question-images">
                        ${questionImages.map(img => {
                            let imageSrc = img;
                            if (imageSrc.startsWith('/uploads/')) {
                                imageSrc = imageSrc.replace('/uploads/', '/images/');
                            }
                            const imageScale = APP_CONFIG.imageDisplay.defaultScale;
                            return `<img src="${imageSrc}" style="max-width: ${imageScale * 100}%; margin: 5px;">`;
                        }).join('')}
                    </div>
                ` : ''}
                ${questionTags.length > 0 ? `
                    <div class="parsed-tags">
                        <strong>标签：</strong>
                        ${questionTags.map(tag => `<span class="parsed-tag">${tag}</span>`).join('')}
                    </div>
                ` : ''}
                ${questionAnswer ? `
                    <div class="parsed-answer">
                        <strong>解答：</strong>
                        <div class="parsed-answer-content">${renderMathContent(questionAnswer)}</div>
                    </div>
                ` : ''}
                <div class="question-actions" style="margin-top: 10px;">
                    <button class="btn btn-add-cart btn-sm" onclick="addParsedToCart(${index})">
                        <i class="fas fa-plus"></i> 加入试卷
                    </button>
                </div>
            </div>
        `;
    }).join('');
    
    renderMath();
}

// 批量保存
async function handleBatchSave() {
    if (parsedQuestions.length === 0) {
        showMessage('没有可保存的题目', 'error');
        return;
    }
    
    // 获取选中的题目索引
    const checkedBoxes = document.querySelectorAll('#parsed-questions-list input[type="checkbox"]:checked');
    const selectedIndices = Array.from(checkedBoxes).map(cb => parseInt(cb.dataset.index));
    
    if (selectedIndices.length === 0) {
        showMessage('请至少选择一个题目', 'error');
        return;
    }
    
    const visibility = document.querySelector('input[name="ocr-visibility"]:checked').value;
    const source = document.getElementById('ocr-source').value.trim() || '试卷解析';
    
    try {
        showLoading(true);
        let successCount = 0;
        
        for (const index of selectedIndices) {
            const question = parsedQuestions[index];
            const response = await fetch('/api/questions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    latex_content: question.question,
                    tags: question.tags || [],
                    reference_answer: question.answer || '',
                    source: source,
                    image: question.image || [],
                    visibility: visibility,
                    question_type: (question.question_type || '解答题')
                })
            });
            
            const result = await response.json();
            if (result.success) {
                successCount++;
            }
        }
        
        showMessage(`成功保存 ${successCount} 道题目！`, 'success');
        parsedQuestions = [];
        parsedQuestionsDiv.style.display = 'none';
        removeExam();
        // 重新加载统计
        await loadStats();
    } catch (error) {
        showMessage('批量保存失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 购物车功能

// 添加题目到购物车
async function addToCart(questionId) {
    try {
        const response = await fetch(`/api/questions/${questionId}`);
        const result = await response.json();
        
        if (result.success) {
            const question = result.question;
            
            // 检查是否已存在
            if (cart.find(item => item.id === questionId)) {
                showMessage('该题目已在试卷中', 'warning');
                return;
            }
            
            cart.push(question);
            updateCartBadge();
            showMessage('已加入试卷', 'success');
        }
    } catch (error) {
        showMessage('添加失败: ' + error.message, 'error');
    }
}

// 添加解析的题目到购物车
function addParsedToCart(index) {
    const question = parsedQuestions[index];
    
    // 给解析的题目添加一个临时ID
    const tempId = 'parsed_' + index + '_' + Date.now();
    const cartItem = {
        id: tempId,
        latex_content: question.question,
        tags: question.tags || [],
        reference_answer: question.answer || '',
        source: '试卷解析',
        isParsed: true,
        question_type: question.question_type || '解答题'
    };
    
    cart.push(cartItem);
    updateCartBadge();
    showMessage('已加入试卷', 'success');
}

// 更新购物车徽章
function updateCartBadge() {
    cartBadge.textContent = cart.length;
}

// 打开购物车模态框
function openCartModal() {
    renderCart();
    cartModal.style.display = 'block';
}

// 关闭购物车模态框
function closeCartModal() {
    cartModal.style.display = 'none';
}

// 渲染购物车
function renderCart() {
    const cartItemsDiv = document.getElementById('cart-items');
    
    if (cart.length === 0) {
        cartItemsDiv.innerHTML = `
            <div class="cart-empty">
                <i class="fas fa-shopping-cart"></i>
                <p>试卷为空，请先添加题目</p>
            </div>
        `;
        return;
    }
    
    cartItemsDiv.innerHTML = cart.map((item, index) => `
        <div class="cart-item" data-index="${index}">
            <div class="cart-item-content">
                <div class="cart-item-title">题目 ${index + 1}</div>
                <div class="cart-item-preview">${renderMathContent(item.latex_content).substring(0, 80)}...</div>
            </div>
            <div class="cart-item-actions">
                ${index > 0 ? `<button class="cart-item-btn btn-move-up" onclick="moveCartItem(${index}, -1)">
                    <i class="fas fa-arrow-up"></i>
                </button>` : ''}
                ${index < cart.length - 1 ? `<button class="cart-item-btn btn-move-down" onclick="moveCartItem(${index}, 1)">
                    <i class="fas fa-arrow-down"></i>
                </button>` : ''}
                <button class="cart-item-btn btn-remove-cart" onclick="removeFromCart(${index})">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// 移动购物车项目
function moveCartItem(index, direction) {
    const newIndex = index + direction;
    if (newIndex >= 0 && newIndex < cart.length) {
        [cart[index], cart[newIndex]] = [cart[newIndex], cart[index]];
        renderCart();
    }
}

// 从购物车移除
function removeFromCart(index) {
    cart.splice(index, 1);
    updateCartBadge();
    renderCart();
    showMessage('已从试卷中移除', 'success');
}

// 清空购物车
function clearCart() {
    if (cart.length === 0) {
        return;
    }
    
    if (confirm('确定要清空试卷吗？')) {
        cart = [];
        updateCartBadge();
        renderCart();
        showMessage('已清空试卷', 'success');
    }
}

// 导出试卷
async function exportPaper() {
    if (cart.length === 0) {
        showMessage('试卷为空，无法导出', 'error');
        return;
    }
    
    const title = document.getElementById('export-title').value || '数学试卷';
    const mode = document.querySelector('input[name="export-mode"]:checked').value;
    const format = document.querySelector('input[name="export-format"]:checked').value;
    
    try {
        showLoading(true);
        
        const response = await fetch('/api/export-paper', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                questions: cart,
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
            
            // 格式化时间：YYYYMMDD_HHMMSS
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            const timeStr = `${year}${month}${day}_${hours}${minutes}${seconds}`;
            
            // 清理文件名：移除非法字符（Windows文件名不能包含：\ / : * ? " < > |）
            const cleanTitle = title.replace(/[\\/:*?"<>|]/g, '_').trim() || '试卷';
            
            a.download = `${cleanTitle}_${timeStr}.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            showMessage('试卷导出成功！', 'success');
            closeCartModal();
        } else {
            const result = await response.json();
            showMessage('导出失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('导出失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function loadStudents(showSpinner = false) {
    try {
        if (showSpinner) {
            showLoading(true);
        }
        const response = await fetch('/api/students');
        const result = await response.json();

        if (!result.success) {
            showMessage('加载学生列表失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        studentList = Array.isArray(result.students) ? result.students : [];
        renderStudents();
    } catch (error) {
        console.error(error);
        showMessage('加载学生列表失败: ' + error.message, 'error');
    } finally {
        if (showSpinner) {
            showLoading(false);
        }
    }
}

function renderStudents() {
    if (!studentsTableBody) {
        return;
    }

    if (!Array.isArray(studentList) || studentList.length === 0) {
        studentsTableBody.innerHTML = '';
        updateStudentsEmptyState();
        return;
    }

    const rowsHtml = studentList.map((student) => {
        const score = typeof student.average_score === 'number' ? student.average_score : NaN;
        const scoreText = formatScore(score);
        const hasScore = scoreText !== '--';
        const scoreStyle = hasScore
            ? `background:${getScoreColor(score)}; color:#fff;`
            : 'background:var(--color-border); color:var(--color-muted);';
        const updatedAt = student.updated_at ? formatDate(student.updated_at) : '';
        const displayName = student.name || '-';

        return `
            <tr data-student-id="${student.student_id}">
                <td>${student.student_id || '-'}</td>
                <td>${displayName}</td>
                <td>${updatedAt}</td>
                <td>
                    <div class="student-action-group">
                        <span class="score-chip" style="${scoreStyle}">${scoreText}</span>
                        <button class="btn btn-secondary" data-action="history">
                            <i class="fas fa-clock-rotate-left"></i> 做题历史
                        </button>
                        <button class="btn btn-secondary" data-action="homework">
                            <i class="fas fa-file-signature"></i> 提交作业
                        </button>
                        <button class="btn btn-secondary" data-action="report">
                            <i class="fas fa-chart-line"></i> 生成报告
                        </button>
                        <button class="btn btn-secondary" data-action="recommendation">
                            <i class="fas fa-wand-magic-sparkles"></i> AI题目推荐
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    studentsTableBody.innerHTML = rowsHtml;
    updateStudentsEmptyState();
    renderMath();
}

async function handleStudentSubmit() {
    const studentId = (studentIdInput?.value || '').trim();
    const studentName = (studentNameInput?.value || '').trim();

    if (!studentId || !studentName) {
        showMessage('请填写学号和姓名', 'error');
        return;
    }

    try {
        showLoading(true);
        const response = await fetch('/api/students', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student_id: studentId,
                name: studentName
            })
        });

        const result = await response.json();
        if (!result.success) {
            showMessage('添加学生失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        showMessage('学生添加成功', 'success');
        closeModalElement(addStudentModal);
        await loadStudents(false);
    } catch (error) {
        showMessage('添加学生失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function handleStudentActionClick(event) {
    const actionButton = event.target.closest('button[data-action]');
    if (!actionButton) {
        return;
    }

    const action = actionButton.dataset.action;
    const row = actionButton.closest('tr[data-student-id]');
    if (!row) {
        return;
    }

    const studentId = row.dataset.studentId;
    const student = studentList.find((item) => item.student_id === studentId);
    if (!student) {
        showMessage('学生信息不存在或已被删除', 'error');
        return;
    }

    selectedStudent = student;

    switch (action) {
        case 'history':
            loadStudentHistory(student);
            break;
        case 'homework':
            openHomeworkModal(student);
            break;
        case 'report':
            loadStudentReport(student, { refresh: false });
            break;
        case 'recommendation':
            loadStudentRecommendations(student);
            break;
        default:
            break;
    }
}

async function openHomeworkModal(student) {
    if (!student || !homeworkModal) {
        return;
    }

    resetHomeworkState();
    selectedStudent = student;
    homeworkState.student = student;

    if (homeworkStudentName) {
        homeworkStudentName.textContent = student.name || '-';
    }
    if (homeworkStudentId) {
        homeworkStudentId.textContent = student.student_id || '-';
    }

    openModalElement(homeworkModal);
    await populateExportOptions();
}

async function populateExportOptions(forceReload = false) {
    if (forceReload) {
        exportHistoryCache = null;
    }

    if (!exportHistoryCache) {
        try {
            const response = await fetch('/api/user/exports');
            const result = await response.json();
            if (result.success) {
                exportHistoryCache = Array.isArray(result.exports) ? result.exports : [];
            } else {
                exportHistoryCache = [];
                showMessage('加载试卷列表失败: ' + (result.message || '未知错误'), 'error');
            }
        } catch (error) {
            exportHistoryCache = [];
            showMessage('加载试卷列表失败: ' + error.message, 'error');
        }
    }

    if (!homeworkExportOptions || !homeworkExportSelect) {
        return;
    }

    homeworkExportOptions.innerHTML = '';
    const trigger = homeworkExportSelect.querySelector('.custom-select-trigger');
    const valueSpan = trigger?.querySelector('.custom-select-value');

    const exports = Array.isArray(exportHistoryCache) ? exportHistoryCache.slice() : [];
    if (exports.length === 0) {
        if (valueSpan) {
            valueSpan.textContent = '暂无导出的试卷';
        }
        if (trigger) {
            trigger.classList.add('disabled');
        }
        return;
    }

    exports.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    if (trigger) {
        trigger.classList.remove('disabled');
    }

    exports.forEach((exportItem) => {
        const option = document.createElement('div');
        option.className = 'custom-select-option';
        option.dataset.value = exportItem.id;
        const title = exportItem.title || '未命名试卷';
        const createdAt = exportItem.created_at ? formatDate(exportItem.created_at) : '';
        option.textContent = `${title}（${createdAt}）`;
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            const value = option.dataset.value;
            homeworkState.exportId = parseInt(value);
            if (valueSpan) {
                valueSpan.textContent = option.textContent;
            }
            homeworkExportOptions.querySelectorAll('.custom-select-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            option.classList.add('selected');
            closeAllCustomSelects();
        });
        homeworkExportOptions.appendChild(option);
    });
}

async function handleHomeworkParse() {
    if (!homeworkState.student) {
        showMessage('请选择学生后再解析作业', 'error');
        return;
    }

    const trigger = homeworkExportSelect?.querySelector('.custom-select-trigger');
    if (!trigger || trigger.classList.contains('disabled')) {
        showMessage('请先准备好关联的试卷', 'error');
        return;
    }

    const exportId = homeworkState.exportId;
    if (!exportId) {
        showMessage('请选择关联的试卷', 'error');
        return;
    }

    const file = homeworkFileInput?.files?.[0];
    if (!file) {
        showMessage('请先上传作业图片', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('export_id', exportId);
    formData.append('student_name', homeworkState.student.name || '');
    formData.append('file', file);

    const originalHtml = homeworkParseBtn.innerHTML;
    const config = APP_CONFIG.parsingProgress;
    let progress = 0;

    homeworkParseBtn.disabled = true;
    homeworkParseBtn.classList.add('parsing');

    const progressInterval = setInterval(() => {
        progress += config.increment;
        if (progress > config.maxProgress) {
            progress = config.maxProgress;
        }
        homeworkParseBtn.innerHTML = `<i class="fas fa-cog fa-spin"></i> 正在解析 ${Math.floor(progress)}%`;
    }, config.interval);

    try {
        const response = await fetch(`/api/students/${homeworkState.student.student_id}/homework/parse`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        if (!result.success) {
            showMessage('作业解析失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        homeworkState.exportId = result.export_id;
        homeworkState.paperTitle = result.paper_title || '';
        homeworkState.results = Array.isArray(result.results) ? result.results : [];
        homeworkState.raw = result;

        renderHomeworkResults(homeworkState.results);
        showMessage('作业解析完成', 'success');
    } catch (error) {
        showMessage('作业解析失败: ' + error.message, 'error');
    } finally {
        clearInterval(progressInterval);
        homeworkParseBtn.disabled = false;
        homeworkParseBtn.classList.remove('parsing');
        homeworkParseBtn.innerHTML = originalHtml;
    }
}

function renderHomeworkResults(results) {
    if (!homeworkResultsContainer || !homeworkResultsList) {
        return;
    }

    if (!Array.isArray(results) || results.length === 0) {
        homeworkResultsContainer.classList.add('hidden');
        homeworkResultsList.innerHTML = '';
        return;
    }

    const itemsHtml = results.map((item, index) => {
        const questionNumber = item.question_number || index + 1;
        const score = typeof item.score === 'number' ? item.score : 0;
        const scoreText = (score * 100).toFixed(0) + '%';
        const feedback = item.feedback || '';
        const questionHtml = renderMathContent(item.original_question || '');
        const answerHtml = renderMathContent(item.student_answer || '');

        return `
            <div class="homework-card">
                <div class="homework-card-header">
                    <span>题目 ${questionNumber}</span>
                    <span class="homework-card-score">得分：${scoreText}</span>
                </div>
                <div class="homework-card-content">
                    <strong>原题：</strong>
                    <div>${questionHtml || '暂无题面内容'}</div>
                </div>
                <div class="homework-card-content">
                    <strong>学生作答：</strong>
                    <div>${answerHtml || '未识别到学生作答'}</div>
                </div>
                <div class="homework-card-content">
                    <strong>点评：</strong>
                    <div>${feedback || '—'}</div>
                </div>
            </div>
        `;
    }).join('');

    homeworkResultsList.innerHTML = itemsHtml;
    homeworkResultsContainer.classList.remove('hidden');
    if (homeworkSaveBtn) {
        homeworkSaveBtn.disabled = false;
    }
    renderMath();
}

async function handleHomeworkSave() {
    if (!homeworkState.student) {
        showMessage('请先选择学生', 'error');
        return;
    }

    if (!homeworkState.results || homeworkState.results.length === 0) {
        showMessage('请先完成作业解析', 'error');
        return;
    }

    if (!homeworkState.exportId) {
        showMessage('缺少试卷信息，请重新解析', 'error');
        return;
    }

    const payload = {
        export_id: homeworkState.exportId,
        paper_title: homeworkState.paperTitle,
        student_name: homeworkState.student.name || '',
        results: homeworkState.results
    };

    try {
        showLoading(true);
        const response = await fetch(`/api/students/${homeworkState.student.student_id}/homework/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        if (!result.success) {
            showMessage('保存作业失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        showMessage('作业结果已保存', 'success');
        closeModalElement(homeworkModal);
        await loadStudents(false);
    } catch (error) {
        showMessage('保存作业失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function loadStudentHistory(student) {
    if (!student || !historyModal) {
        return;
    }

    try {
        showLoading(true);
        const params = new URLSearchParams({
            window_days: String(STUDENT_ANALYTICS_WINDOW_DAYS),
            limit: '200'
        });
        const response = await fetch(`/api/students/${student.student_id}/history?${params.toString()}`);
        const result = await response.json();

        if (!result.success) {
            showMessage('加载做题历史失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        renderStudentHistory(result.history || [], student);
        openModalElement(historyModal);
    } catch (error) {
        showMessage('加载做题历史失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function renderStudentHistory(history, student) {
    if (!historyContent) {
        return;
    }

    if (!Array.isArray(history) || history.length === 0) {
        historyContent.innerHTML = '<div class="history-item">暂无做题记录</div>';
        return;
    }

    historyContent.innerHTML = history.map((item, index) => {
        const questionNumber = item.question_number || (index + 1);
        const score = typeof item.score === 'number' ? item.score : 0;
        const scoreText = (score * 100).toFixed(0) + '%';
        const createdAt = item.created_at ? formatDate(item.created_at) : '';
        const feedback = item.feedback || '';
        const questionHtml = renderMathContent(item.original_question || '');
        const answerHtml = renderMathContent(item.student_answer || '');

        return `
            <div class="history-item">
                <div class="history-item-header">
                    <span>题目 ${questionNumber}</span>
                    <span>得分：${scoreText}</span>
                    <span>${createdAt}</span>
                </div>
                <div class="history-item-content">
                    <strong>原题：</strong>
                    <div>${questionHtml || '暂无题面内容'}</div>
                </div>
                <div class="history-item-content">
                    <strong>学生作答：</strong>
                    <div>${answerHtml || '未识别到学生作答'}</div>
                </div>
                <div class="history-item-content">
                    <strong>点评：</strong>
                    <div>${feedback || '—'}</div>
                </div>
            </div>
        `;
    }).join('');

    renderMath();
}

async function loadStudentReport(student, options = {}) {
    if (!student) {
        showMessage('请先选择学生', 'error');
        return;
    }
    if (!reportModal) {
        return;
    }

    selectedStudent = student;

    const params = new URLSearchParams();
    if (options.refresh) {
        params.append('refresh', 'true');
    }

    try {
        showLoading(true);
        const response = await fetch(`/api/students/${student.student_id}/report?${params.toString()}`);
        const result = await response.json();

        if (!result.success) {
            showMessage('生成学习报告失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        const report = result.report || {};
        const historyPreview = result.history_preview || [];
        renderStudentReport(report, student, historyPreview, Boolean(result.cached), result.generated_at);
        openModalElement(reportModal);
    } catch (error) {
        showMessage('生成学习报告失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function renderStudentReport(report, student, historyPreview, cached, generatedAt) {
    if (reportDistribution) {
        reportDistribution.textContent = report.mistake_distribution || '暂无数据。';
    }

    if (reportKnowledgeList) {
        const knowledgePoints = Array.isArray(report.knowledge_points) ? report.knowledge_points : [];
        if (knowledgePoints.length === 0) {
            reportKnowledgeList.innerHTML = '<li>暂无需要补强的知识点</li>';
        } else {
            reportKnowledgeList.innerHTML = knowledgePoints.map((point) => `<li>${point}</li>`).join('');
        }
    }

    if (reportPlanList) {
        const plan = Array.isArray(report.study_plan) ? report.study_plan : [];
        if (plan.length === 0) {
            reportPlanList.innerHTML = '<li>暂无学习计划建议</li>';
        } else {
            reportPlanList.innerHTML = plan.map((item, idx) => {
                if (item && typeof item === 'object') {
                    const topic = item.topic || `步骤 ${item.step || idx + 1}`;
                    const action = item.action || '';
                    return `<li><strong>${topic}</strong>：${action}</li>`;
                }
                return `<li>${item}</li>`;
            }).join('');
        }
    }

    if (historyPreview && historyPreview.length > 0 && historyContent) {
        // 可选：在报告生成后同步更新历史预览
    }

    renderMath();
}

async function loadStudentRecommendations(student) {
    if (!student) {
        showMessage('请先选择学生', 'error');
        return;
    }
    if (!recommendationModal) {
        return;
    }

    try {
        showLoading(true);
        const response = await fetch(`/api/students/${student.student_id}/recommendations`);
        const result = await response.json();

        if (!result.success) {
            showMessage('生成AI题目推荐失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        renderStudentRecommendations(result.reasons || [], result.questions || []);
        openModalElement(recommendationModal);
    } catch (error) {
        showMessage('生成AI题目推荐失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function renderStudentRecommendations(reasons, questions) {
    if (recommendationReasons) {
        if (!Array.isArray(reasons) || reasons.length === 0) {
            recommendationReasons.innerHTML = '<span class="reason-chip">暂无推荐理由</span>';
        } else {
            recommendationReasons.innerHTML = reasons.map((reason) => `<span class="reason-chip">${reason}</span>`).join('');
        }
    }

    if (!recommendationList) {
        return;
    }

    if (!Array.isArray(questions) || questions.length === 0) {
        recommendationList.innerHTML = '<div class="recommendation-card">暂无推荐题目，请先生成学习报告。</div>';
        return;
    }

    recommendationList.innerHTML = questions.map((question) => {
        const questionId = question.id;
        const questionHtml = renderMathContent(question.latex_content || '');
        const tags = Array.isArray(question.tags) ? question.tags : [];
        const tagHtml = tags.length > 0
            ? `<div class="question-tags">${tags.map((tag) => `<span class="question-tag">${tag}</span>`).join('')}</div>`
            : '';

        const actionButtons = questionId !== undefined && questionId !== null
            ? `
                <button class="btn btn-primary action-view" data-question-id="${questionId}">
                    <i class="fas fa-eye"></i> 查看详情
                </button>
                <button class="btn btn-secondary action-add" data-question-id="${questionId}">
                    <i class="fas fa-plus"></i> 加入试卷
                </button>
            `
            : '<span class="score-chip" style="background: var(--color-border); color: var(--color-muted);">暂无操作</span>';

        return `
            <div class="recommendation-card">
                <div class="question-content">${questionHtml}</div>
                ${tagHtml}
                <div class="card-actions">
                    ${actionButtons}
                </div>
            </div>
        `;
    }).join('');

    renderMath();
}

function handleRecommendationClick(event) {
    const button = event.target.closest('button[data-question-id]');
    if (!button) {
        return;
    }

    const questionId = button.getAttribute('data-question-id');
    if (!questionId) {
        return;
    }

    if (button.classList.contains('action-view')) {
        viewQuestion(questionId);
        return;
    }

    if (button.classList.contains('action-add')) {
        addToCart(questionId);
    }
}

// 删除题目
async function deleteQuestion(questionId) {
    if (!confirm('确定要删除这道题目吗？此操作不可恢复。')) {
        return;
    }
    
    try {
        showLoading(true);
        
        const response = await fetch(`/api/questions/${questionId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showMessage('题目删除成功！', 'success');
            // 重新加载题目列表
            await loadQuestions();
            // 重新加载统计
            await loadStats();
        } else {
            showMessage('删除失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('删除失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 全局函数，供HTML调用
window.viewQuestion = viewQuestion;
window.removeImage = removeImage;
window.addToCart = addToCart;
window.addParsedToCart = addParsedToCart;
window.moveCartItem = moveCartItem;
window.removeFromCart = removeFromCart;
window.deleteQuestion = deleteQuestion;

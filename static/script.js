// 全局变量
let currentPage = 1;
let totalPages = 1;
let availableTags = [];
let currentQuestions = [];
let uploadedImages = [];
let parsedQuestions = [];

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
const prevPageBtn = document.getElementById('prev-page');
const nextPageBtn = document.getElementById('next-page');
const pageInfo = document.getElementById('page-info');
const currentCount = document.getElementById('current-count');
const totalCount = document.getElementById('total-count');
const questionModal = document.getElementById('question-modal');
const modalClose = document.querySelector('.modal-close');
const loading = document.getElementById('loading');
const message = document.getElementById('message');
const messageText = document.getElementById('message-text');
const messageClose = document.getElementById('message-close');

// 新增的DOM元素
const imageUpload = document.getElementById('image-upload');
const uploadBtn = document.getElementById('upload-btn');
const imagePreview = document.getElementById('image-preview');
const examUpload = document.getElementById('exam-upload');
const examUploadBtn = document.getElementById('exam-upload-btn');
const examPreview = document.getElementById('exam-preview');
const parseExamBtn = document.getElementById('parse-exam-btn');
const parsedQuestionsDiv = document.getElementById('parsed-questions');
const parsedQuestionsList = document.getElementById('parsed-questions-list');
const batchTagBtn = document.getElementById('batch-tag-btn');
const batchSaveBtn = document.getElementById('batch-save-btn');

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// 初始化应用
async function initializeApp() {
    setupEventListeners();
    
    // 先加载标签，再加载内容
    await loadAvailableTags();
    
    // 根据当前激活的标签页加载相应内容
    const activeTab = document.querySelector('.nav-tab.active');
    if (activeTab) {
        const tabName = activeTab.dataset.tab;
        if (tabName === 'search') {
            await loadAllQuestions();
        } else if (tabName === 'manage') {
            await loadQuestions();
        }
    }
    
    // 初始化MathJax
    setTimeout(() => {
        renderMath();
    }, 100);
}

// 设置事件监听器
function setupEventListeners() {
    // 导航标签切换
    navTabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // 表单提交
    questionForm.addEventListener('submit', handleFormSubmit);
    
    // 自动打标按钮
    autoTagBtn.addEventListener('click', handleAutoTag);
    
    // 搜索按钮
    searchBtn.addEventListener('click', handleSearch);
    
    // 刷新按钮
    refreshBtn.addEventListener('click', loadQuestions);
    
    // 分页按钮
    prevPageBtn.addEventListener('click', () => changePage(-1));
    nextPageBtn.addEventListener('click', () => changePage(1));
    
    // 模态框关闭
    modalClose.addEventListener('click', closeModal);
    questionModal.addEventListener('click', (e) => {
        if (e.target === questionModal) closeModal();
    });
    
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
    examUploadBtn.addEventListener('click', () => examUpload.click());
    examUpload.addEventListener('change', handleExamUpload);
    parseExamBtn.addEventListener('click', handleParseExam);
    
    // 拖拽上传
    const uploadZone = document.getElementById('upload-zone');
    uploadZone.addEventListener('click', () => examUpload.click());
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
    
    // 批量操作
    batchTagBtn.addEventListener('click', handleBatchTag);
    batchSaveBtn.addEventListener('click', handleBatchSave);
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
    } else if (tabName === 'search') {
        // 搜索页面默认加载所有题目
        loadAllQuestions();
        // 确保标签筛选正确显示
        if (availableTags.length > 0) {
            renderTagFilter();
        }
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
    
    const questionData = {
        latex_content: formData.get('latex_content'),
        tags: selectedTags,
        reference_answer: formData.get('reference_answer'),
        source: formData.get('source'),
        image: uploadedImages
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
            // 清除标签选择
            tagSelector.querySelectorAll('.tag-item').forEach(tag => {
                tag.classList.remove('selected');
                tag.querySelector('input[type="checkbox"]').checked = false;
            });
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
    const latexContent = document.getElementById('latex-content').value;
    const source = document.getElementById('source').value;
    
    if (!latexContent.trim()) {
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
                latex_content: latexContent,
                source: source
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
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
            
            // 显示打标结果预览
            showTaggingPreview(result.tags, result.answer);
            
            showMessage('自动打标完成！', 'success');
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
    
    try {
        showLoading(true);
        
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
        showLoading(false);
    }
}

// 渲染搜索结果
function renderSearchResults() {
    if (currentQuestions.length === 0) {
        searchResults.innerHTML = '<div class="no-results">没有找到相关题目</div>';
        return;
    }
    
    searchResults.innerHTML = currentQuestions.map(question => `
        <div class="question-item">
            <div class="question-header">
                <span class="question-id">#${question.id}</span>
                <div class="question-tags">
                    ${question.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')}
                </div>
            </div>
            <div class="question-content">
                ${renderMathContent(question.latex_content)}
            </div>
            <div class="question-actions">
                <button class="btn btn-primary" onclick="viewQuestion(${question.id})">
                    <i class="fas fa-eye"></i> 查看详情
                </button>
                ${question.reference_answer ? `
                    <button class="btn btn-secondary" onclick="viewAnswer(${question.id})">
                        <i class="fas fa-lightbulb"></i> 查看解答
                    </button>
                ` : ''}
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
                        <button class="btn btn-primary btn-sm" onclick="viewQuestion(${question.id})">
                            <i class="fas fa-eye"></i> 查看
                        </button>
                        <div class="question-tags">
                            ${question.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')}
                        </div>
                    </div>
                    <div class="question-right">
                        <small>${question.source || '未知'} | ${formatDate(question.created_at)}</small>
                    </div>
                </div>
            </div>
            <div class="question-content-preview">
                ${renderMathContent(question.latex_content).replace(/\n/g, ' ').substring(0, 100)}${question.latex_content.length > 100 ? '...' : ''}
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
        
        if (result.success) {
            const question = result.question;
            
            document.getElementById('modal-question-content').innerHTML = `
                <h4>题目内容</h4>
                <div class="question-detail">${renderMathContent(question.latex_content)}</div>
            `;
            
            document.getElementById('modal-question-tags').innerHTML = `
                <h4>标签</h4>
                <div class="question-tags">
                    ${question.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')}
                </div>
            `;
            
            if (question.reference_answer) {
                document.getElementById('modal-question-answer').innerHTML = `
                    <h4>参考解答</h4>
                    <div class="answer-detail">${renderMathContent(question.reference_answer)}</div>
                `;
            } else {
                document.getElementById('modal-question-answer').innerHTML = '';
            }
            
            questionModal.style.display = 'block';
            
            // 重新渲染数学公式
            if (window.MathJax) {
                MathJax.typesetPromise();
            }
        } else {
            showMessage('获取题目详情失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('获取题目详情失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 查看解答
async function viewAnswer(questionId) {
    try {
        showLoading(true);
        
        const response = await fetch(`/api/questions/${questionId}/answer`);
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('modal-question-content').innerHTML = `
                <h4>参考解答</h4>
                <div class="answer-detail">${renderMathContent(result.answer)}</div>
            `;
            
            document.getElementById('modal-question-tags').innerHTML = '';
            document.getElementById('modal-question-answer').innerHTML = '';
            
            questionModal.style.display = 'block';
            
            // 重新渲染数学公式
            if (window.MathJax) {
                MathJax.typesetPromise();
            }
        } else {
            showMessage('获取解答失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('获取解答失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 关闭模态框
function closeModal() {
    questionModal.style.display = 'none';
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

// 渲染数学内容
function renderMathContent(content) {
    if (!content) return '';
    
    // 转义HTML特殊字符，但保留LaTeX数学公式
    let escaped = content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
    
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
    
    try {
        showLoading(true);
        const response = await fetch('/api/ocr-parse', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            parsedQuestions = result.questions;
            renderParsedQuestions();
            parsedQuestionsDiv.style.display = 'block';
            document.getElementById('parsed-count').textContent = parsedQuestions.length;
            showMessage('试卷解析成功！', 'success');
        } else {
            showMessage('试卷解析失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('试卷解析失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 渲染解析出的题目
function renderParsedQuestions() {
    parsedQuestionsList.innerHTML = parsedQuestions.map((question, index) => `
        <div class="parsed-question-item">
            <h5>题目 ${index + 1}</h5>
            <div class="parsed-question-content">
                ${renderMathContent(question.question)}
            </div>
            ${question.image && question.image.length > 0 ? `
                <div class="question-images">
                    ${question.image.map(img => `<img src="${img}" style="max-width: 200px; margin: 5px;">`).join('')}
                </div>
            ` : ''}
            ${question.tags && question.tags.length > 0 ? `
                <div class="parsed-tags">
                    <strong>标签：</strong>
                    ${question.tags.map(tag => `<span class="parsed-tag">${tag}</span>`).join('')}
                </div>
            ` : ''}
            ${question.answer ? `
                <div class="parsed-answer">
                    <strong>解答：</strong>
                    <div class="parsed-answer-content">${renderMathContent(question.answer)}</div>
                </div>
            ` : ''}
        </div>
    `).join('');
    
    renderMath();
}


// 批量保存
async function handleBatchSave() {
    if (parsedQuestions.length === 0) {
        showMessage('没有可保存的题目', 'error');
        return;
    }
    
    try {
        showLoading(true);
        let successCount = 0;
        
        for (const question of parsedQuestions) {
            const response = await fetch('/api/questions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    latex_content: question.question,
                    tags: question.tags || [],
                    reference_answer: question.answer || '',
                    source: '试卷解析',
                    image: question.image || []
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
        removeExam(); // 重置整个上传区域
    } catch (error) {
        showMessage('批量保存失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 删除题目
async function deleteQuestion(questionId) {
    if (!confirm('确定要删除这道题目吗？此操作不可撤销。')) {
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
            loadQuestions(); // 重新加载题目列表
        } else {
            showMessage('删除失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('删除失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 显示打标结果预览
function showTaggingPreview(tags, answer) {
    // 创建预览容器
    let previewContainer = document.getElementById('tagging-preview');
    if (!previewContainer) {
        previewContainer = document.createElement('div');
        previewContainer.id = 'tagging-preview';
        previewContainer.className = 'tagging-preview';
        previewContainer.innerHTML = `
            <h4><i class="fas fa-eye"></i> 打标结果预览</h4>
            <div class="preview-content">
                <div class="preview-tags">
                    <strong>标签：</strong>
                    <div class="preview-tags-list"></div>
                </div>
                <div class="preview-answer">
                    <strong>解答：</strong>
                    <div class="preview-answer-content"></div>
                </div>
            </div>
        `;
        
        // 插入到表单后面
        const form = document.getElementById('question-form');
        form.parentNode.insertBefore(previewContainer, form.nextSibling);
    }
    
    // 更新内容
    const tagsList = previewContainer.querySelector('.preview-tags-list');
    const answerContent = previewContainer.querySelector('.preview-answer-content');
    
    tagsList.innerHTML = tags.map(tag => `<span class="preview-tag">${tag}</span>`).join('');
    answerContent.innerHTML = renderMathContent(answer);
    
    // 重新渲染数学公式
    renderMath();
}

// 隐藏打标结果预览
function hideTaggingPreview() {
    const previewContainer = document.getElementById('tagging-preview');
    if (previewContainer) {
        previewContainer.remove();
    }
}

// 全局函数，供HTML调用
window.viewQuestion = viewQuestion;
window.viewAnswer = viewAnswer;
window.removeImage = removeImage;
window.deleteQuestion = deleteQuestion;

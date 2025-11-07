// 题目与搜索模块逻辑

const QUESTION_PAGE_LIMIT = APP_CONFIG.content?.manageListPageSize || 10;

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

function renderTagSelector() {
    if (!tagSelector) {
        return;
    }
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

function renderTagFilter() {
    if (!tagFilter) {
        return;
    }
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

function toggleTag(tagElement) {
    tagElement.classList.toggle('selected');
    const checkbox = tagElement.querySelector('input[type="checkbox"]');
    checkbox.checked = !checkbox.checked;
}

function getSelectedTags(container) {
    const selectedTags = [];
    if (!container) {
        return selectedTags;
    }
    const checkboxes = container.querySelectorAll('input[type="checkbox"]:checked');
    checkboxes.forEach(checkbox => {
        selectedTags.push(checkbox.value);
    });
    return selectedTags;
}

async function handleFormSubmit(e) {
    e.preventDefault();

    const formData = new FormData(questionForm);
    const selectedTags = getSelectedTags(tagSelector);
    const visibility = document.querySelector('input[name="visibility"]:checked')?.value || 'public';
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

    if (!questionData.latex_content || !questionData.latex_content.trim()) {
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
            if (imagePreview) {
                imagePreview.innerHTML = '';
            }
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
            if (tagSelector) {
                tagSelector.querySelectorAll('.tag-item').forEach(tag => {
                    tag.classList.remove('selected');
                    const checkbox = tag.querySelector('input[type="checkbox"]');
                    if (checkbox) {
                        checkbox.checked = false;
                    }
                });
            }
        } else {
            showMessage('添加失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('添加失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function handleAutoTag() {
    const contentInput = document.getElementById('latex-content');
    const sourceInput = document.getElementById('source');
    const content = contentInput ? contentInput.value : '';
    const source = sourceInput ? sourceInput.value : '';

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
            if (result.latex_content && contentInput) {
                contentInput.value = result.latex_content;
            }

            const selectedTags = result.tags || [];
            if (tagSelector) {
                tagSelector.querySelectorAll('.tag-item').forEach(tagElement => {
                    const checkbox = tagElement.querySelector('input[type="checkbox"]');
                    const tagValue = checkbox?.value;

                    if (tagValue && selectedTags.includes(tagValue)) {
                        tagElement.classList.add('selected');
                        if (checkbox) {
                            checkbox.checked = true;
                        }
                    } else {
                        tagElement.classList.remove('selected');
                        if (checkbox) {
                            checkbox.checked = false;
                        }
                    }
                });
            }

            const referenceAnswerInput = document.getElementById('reference-answer');
            if (referenceAnswerInput) {
                referenceAnswerInput.value = result.answer || '';
            }

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

async function handleSearch() {
    if (!searchBtn || !searchKeyword) {
        return;
    }

    const keyword = searchKeyword.value.trim();
    const selectedTags = getSelectedTags(tagFilter);

    const searchIcon = searchBtn.querySelector('i');
    const originalClass = searchIcon ? searchIcon.className : '';
    if (searchIcon) {
        searchIcon.className = 'fas fa-spinner fa-spin';
    }
    searchBtn.disabled = true;

    try {
        let url = '/api/questions/search?';
        const params = new URLSearchParams();

        if (keyword) {
            params.append('keyword', keyword);
        }

        if (selectedTags.length > 0) {
            selectedTags.forEach(tag => params.append('tags', tag));
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
        if (searchIcon) {
            searchIcon.className = originalClass;
        }
        searchBtn.disabled = false;
    }
}

function formatSource(source) {
    if (!source) {
        return '未知';
    }
    const maxLength = APP_CONFIG.content?.sourceMaxLength || 30;
    if (source.length <= maxLength) {
        return source;
    }
    return '...' + source.slice(-maxLength);
}

function renderSearchResults() {
    if (!searchResults) {
        return;
    }

    searchResults.style.display = 'block';

    if (!currentQuestions || currentQuestions.length === 0) {
        searchResults.innerHTML = '<div class="no-results">没有找到相关题目</div>';
        return;
    }

    searchResults.innerHTML = currentQuestions.map(question => {
        const tagsHtml = Array.isArray(question.tags)
            ? question.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')
            : '';

        return `
            <div class="question-item">
                <div class="question-header">
                    <div class="question-meta-row">
                        <div class="question-left">
                            <span class="question-id">#${question.id}</span>
                            <div class="question-tags">
                                ${tagsHtml}
                            </div>
                        </div>
                        <div class="question-right">
                            <small>${formatSource(question.source)} | ${formatDate(question.created_at)}</small>
                        </div>
                    </div>
                </div>
                <div class="question-content limited-content">
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
        `;
    }).join('');

    renderMath();
}

async function loadQuestions() {
    try {
        showLoading(true);

        // 先获取题目总数
        const statsResponse = await fetch('/api/questions/stats');
        const statsResult = await statsResponse.json();

        if (!statsResult.success) {
            showMessage('获取题目统计失败: ' + statsResult.message, 'error');
            return;
        }

        questionsTotal = statsResult.stats?.total || 0;
        totalPages = Math.ceil(questionsTotal / QUESTION_PAGE_LIMIT) || 1;

        // 确保当前页码在有效范围内
        if (currentPage > totalPages && totalPages > 0) {
            currentPage = totalPages;
        }
        if (currentPage < 1) {
            currentPage = 1;
        }

        // 根据当前页码获取题目数据
        const response = await fetch(`/api/questions/search?page=${currentPage}&limit=${QUESTION_PAGE_LIMIT}`);
        const result = await response.json();

        if (result.success) {
            currentQuestions = result.questions;
            renderQuestionList(questionsTotal);
            updatePagination(questionsTotal);
        } else {
            showMessage('加载题目失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('加载题目失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function renderQuestionList(totalRecords = questionsTotal) {
    if (!questionList) {
        return;
    }

    const totalValue = typeof totalRecords === 'number' && !Number.isNaN(totalRecords)
        ? totalRecords
        : questionsTotal;

    if (!currentQuestions || currentQuestions.length === 0) {
        questionList.innerHTML = '<div class="no-results">暂无题目</div>';
        if (currentCount) currentCount.textContent = '0';
        if (totalCount) totalCount.textContent = String(totalValue || 0);
        return;
    }

    questionList.innerHTML = currentQuestions.map(question => {
        const tagsHtml = Array.isArray(question.tags)
            ? question.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')
            : '';

        return `
            <div class="question-item">
                <div class="question-header">
                    <div class="question-meta-row">
                        <div class="question-left">
                            <span class="question-id">#${question.id}</span>
                            <div class="question-tags">
                                ${tagsHtml}
                            </div>
                        </div>
                        <div class="question-right">
                            <small>${formatSource(question.source)} | ${formatDate(question.created_at)}</small>
                        </div>
                    </div>
                </div>
                <div class="question-content limited-content">
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
        `;
    }).join('');

    if (currentCount) currentCount.textContent = String(currentQuestions.length);
    if (totalCount) totalCount.textContent = String(totalValue || currentQuestions.length);

    renderMath();
}

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

function closeQuestionModal() {
    if (!questionModal) {
        return;
    }
    if (modalState.isEditing && modalState.original) {
        exitEditMode(true);
    }
    // 重置滚动条位置
    const modalBody = questionModal.querySelector('.modal-body');
    if (modalBody) {
        modalBody.scrollTop = 0;
    }
    questionModal.style.display = 'none';
    resetModalState();
}

function changePage(direction) {
    const newPage = currentPage + direction;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        loadQuestions();
    }
}

function updatePagination(totalRecords = questionsTotal) {
    const totalValue = typeof totalRecords === 'number' && !Number.isNaN(totalRecords)
        ? totalRecords
        : questionsTotal;

    // 获取分页按钮元素（从全局作用域或直接获取）
    const prevBtn = typeof prevPageBtn !== 'undefined' ? prevPageBtn : document.getElementById('prev-page');
    const nextBtn = typeof nextPageBtn !== 'undefined' ? nextPageBtn : document.getElementById('next-page');
    const topPrevBtn = typeof topPrevPageBtn !== 'undefined' ? topPrevPageBtn : document.getElementById('top-prev-page');
    const topNextBtn = typeof topNextPageBtn !== 'undefined' ? topNextPageBtn : document.getElementById('top-next-page');
    const pageInfoEl = typeof pageInfo !== 'undefined' ? pageInfo : document.getElementById('page-info');
    const totalCountEl = typeof totalCount !== 'undefined' ? totalCount : document.getElementById('total-count');

    if (pageInfoEl) {
        pageInfoEl.textContent = `第 ${currentPage} 页 / 共 ${totalPages} 页`;
    }
    if (prevBtn) {
        prevBtn.disabled = currentPage <= 1;
    }
    if (nextBtn) {
        nextBtn.disabled = currentPage >= totalPages;
    }
    if (topPrevBtn) {
        topPrevBtn.disabled = currentPage <= 1;
    }
    if (topNextBtn) {
        topNextBtn.disabled = currentPage >= totalPages;
    }
    if (totalCountEl) {
        totalCountEl.textContent = String(totalValue || currentQuestions.length);
    }
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
    if (questionModal) {
        questionModal.style.display = 'block';
        // 重置滚动条位置到顶部
        const modalBody = questionModal.querySelector('.modal-body');
        if (modalBody) {
            modalBody.scrollTop = 0;
        }
    }
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
            return `<img src="${imageSrc}" alt="题目图片" style="max-width: ${imageScale * 100}%">`;
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
    if (!modalQuestionTags || !modalEditHint) {
        return;
    }

    const modalTagsSection = document.getElementById('modal-tags-section');
    if (!tags || tags.length === 0) {
        modalTagsSection?.classList.add('hidden');
        modalQuestionTags.innerHTML = '<span class="modal-annotation">暂无标签</span>';
        return;
    }

    modalTagsSection?.classList.remove('hidden');
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
    updateModalEditingUI();
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
    updateModalEditingUI();
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
    if (cartModal && cartModal.style.display === 'block') {
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
    const modalTagsSection = document.getElementById('modal-tags-section');
    if (modalTagsSection) {
        modalTagsSection.classList.remove('hidden');
    }

    setSaveButtonLoading(false);
    setAiVariantLoading(false);
    updateModalEditingUI();
}

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
            await loadQuestions();
        } else {
            showMessage('删除失败: ' + result.message, 'error');
        }
    } catch (error) {
        showMessage('删除失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

window.loadAvailableTags = loadAvailableTags;
window.handleFormSubmit = handleFormSubmit;
window.handleAutoTag = handleAutoTag;
window.handleSearch = handleSearch;
window.renderSearchResults = renderSearchResults;
window.loadQuestions = loadQuestions;
window.renderQuestionList = renderQuestionList;
window.viewQuestion = viewQuestion;
window.closeQuestionModal = closeQuestionModal;
window.changePage = changePage;
window.updatePagination = updatePagination;
window.openQuestionModal = openQuestionModal;
window.handleEditQuestion = handleEditQuestion;
window.enterEditMode = enterEditMode;
window.handleCancelEdit = handleCancelEdit;
window.handleSaveQuestion = handleSaveQuestion;
window.exitEditMode = exitEditMode;
window.updateModalEditingUI = updateModalEditingUI;
window.setSaveButtonLoading = setSaveButtonLoading;
window.handleAiVariant = handleAiVariant;
window.setAiVariantLoading = setAiVariantLoading;
window.refreshQuestionCollections = refreshQuestionCollections;
window.resetModalState = resetModalState;
window.deleteQuestion = deleteQuestion;

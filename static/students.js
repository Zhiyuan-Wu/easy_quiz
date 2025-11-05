// 学生管理、作业解析与报告模块

const STUDENT_ANALYTICS_WINDOW_DAYS = APP_CONFIG.students?.analyticsWindowDays || 30;

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
                <td data-label="学号">${student.student_id || '-'}</td>
                <td data-label="姓名">${displayName}</td>
                <td data-label="更新时间">${updatedAt}</td>
                <td data-label="操作">
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

    const exports = Array.isArray(exportHistoryCache) ? [...exportHistoryCache] : [];
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
            homeworkState.exportId = parseInt(value, 10);
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

function handleHomeworkFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) {
        return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
        if (homeworkUploadZone) {
            homeworkUploadZone.style.display = 'none';
        }
        if (homeworkPreview) {
            homeworkPreview.style.display = 'block';
            const previewImage = homeworkPreview.querySelector('.preview-image');
            if (previewImage) {
                previewImage.innerHTML = `<img src="${event.target.result}" alt="作业预览">`;
            }
        }
    };
    reader.readAsDataURL(file);
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
        const previewImage = homeworkPreview.querySelector('.preview-image');
        if (previewImage) {
            previewImage.innerHTML = '';
        }
    }
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

    if (!homeworkParseBtn) {
        return;
    }

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
                    <div class="limited-content">${questionHtml || '暂无题面内容'}</div>
                </div>
                <div class="homework-card-content">
                    <strong>学生作答：</strong>
                    <div class="limited-content">${answerHtml || '未识别到学生作答'}</div>
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
                    <div class="limited-content">${questionHtml || '暂无题面内容'}</div>
                </div>
                <div class="history-item-content">
                    <strong>学生作答：</strong>
                    <div class="limited-content">${answerHtml || '未识别到学生作答'}</div>
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
                <div class="question-content limited-content">${questionHtml}</div>
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

window.loadStudents = loadStudents;
window.renderStudents = renderStudents;
window.handleStudentSubmit = handleStudentSubmit;
window.handleStudentActionClick = handleStudentActionClick;
window.openHomeworkModal = openHomeworkModal;
window.populateExportOptions = populateExportOptions;
window.handleHomeworkFileUpload = handleHomeworkFileUpload;
window.removeHomeworkFile = removeHomeworkFile;
window.handleHomeworkParse = handleHomeworkParse;
window.renderHomeworkResults = renderHomeworkResults;
window.handleHomeworkSave = handleHomeworkSave;
window.loadStudentHistory = loadStudentHistory;
window.renderStudentHistory = renderStudentHistory;
window.loadStudentReport = loadStudentReport;
window.renderStudentReport = renderStudentReport;
window.loadStudentRecommendations = loadStudentRecommendations;
window.renderStudentRecommendations = renderStudentRecommendations;
window.handleRecommendationClick = handleRecommendationClick;

// 学生管理、作业解析与报告模块

const STUDENT_ANALYTICS_WINDOW_DAYS = APP_CONFIG.students?.analyticsWindowDays || 30;

const batchState = {
    exportId: null,
    paperTitle: '',
    files: [],
    mapping: {},
    order: [],
    questions: [],
    failures: [],
};

const classReportState = {
    exportId: null,
    paperTitle: '',
    sectionOrder: [],
    sections: {},
};

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
    homeworkState.detectedStudentId = '';
    homeworkState.detectedStudentName = '';
    updateHomeworkDetectedStudentHint();

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

function updateHomeworkDetectedStudentHint() {
    if (!homeworkDetectedStudent) {
        return;
    }
    const detectedId = homeworkState.detectedStudentId;
    const detectedName = homeworkState.detectedStudentName;
    const currentId = homeworkState.student ? homeworkState.student.student_id : '';
    if (detectedId) {
        const same = detectedId === currentId;
        const nameLabel = detectedName ? `（${detectedName}）` : '';
        homeworkDetectedStudent.textContent = same
            ? `模型识别：${detectedId}`
            : `模型识别：${detectedId}${nameLabel}`;
        homeworkDetectedStudent.classList.remove('hidden');
        homeworkDetectedStudent.classList.toggle('warning', !same);
    } else {
        homeworkDetectedStudent.textContent = '';
        homeworkDetectedStudent.classList.add('hidden');
        homeworkDetectedStudent.classList.remove('warning');
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
        homeworkState.detectedStudentId = result.detected_student_id || '';
        homeworkState.detectedStudentName = result.detected_student_name || '';
        updateHomeworkDetectedStudentHint();

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

async function populateBatchExportOptions(forceReload = false) {
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

    if (!batchExportOptions || !batchExportSelect) {
        return;
    }

    batchExportOptions.innerHTML = '';
    const trigger = batchExportSelect.querySelector('.custom-select-trigger');
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
        option.dataset.title = exportItem.title || '未命名试卷';
        const title = exportItem.title || '未命名试卷';
        const createdAt = exportItem.created_at ? formatDate(exportItem.created_at) : '';
        option.textContent = `${title}（${createdAt}）`;
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            const value = option.dataset.value;
            batchState.exportId = parseInt(value, 10);
            batchState.paperTitle = option.dataset.title || '未命名试卷';
            if (valueSpan) {
                valueSpan.textContent = option.textContent;
            }
            batchExportOptions.querySelectorAll('.custom-select-option').forEach((opt) => {
                opt.classList.remove('selected');
            });
            option.classList.add('selected');
            closeAllCustomSelects();
        });
        batchExportOptions.appendChild(option);
    });
}

async function populateClassReportExportOptions(forceReload = false) {
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

    if (!classReportExportOptions || !classReportExportSelect) {
        return;
    }

    classReportExportOptions.innerHTML = '';
    const trigger = classReportExportSelect.querySelector('.custom-select-trigger');
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
        option.dataset.title = exportItem.title || '未命名试卷';
        const title = exportItem.title || '未命名试卷';
        const createdAt = exportItem.created_at ? formatDate(exportItem.created_at) : '';
        option.textContent = `${title}（${createdAt}）`;
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            const value = option.dataset.value;
            classReportState.exportId = parseInt(value, 10);
            classReportState.paperTitle = option.dataset.title || '未命名试卷';
            if (valueSpan) {
                valueSpan.textContent = option.textContent;
            }
            classReportExportOptions.querySelectorAll('.custom-select-option').forEach((opt) => {
                opt.classList.remove('selected');
            });
            option.classList.add('selected');
            closeAllCustomSelects();
        });
        classReportExportOptions.appendChild(option);
    });
}

function resetBatchState() {
    batchState.exportId = null;
    batchState.paperTitle = '';
    batchState.files = [];
    batchState.mapping = {};
    batchState.order = [];
    batchState.questions = [];
    batchState.failures = [];

    if (batchFileInput) {
        batchFileInput.value = '';
    }
    if (batchUploadSummary) {
        batchUploadSummary.classList.add('hidden');
        batchUploadSummary.innerHTML = '';
    }
    if (batchResultsContainer) {
        batchResultsContainer.classList.add('hidden');
    }
    if (batchSaveBtn) {
        batchSaveBtn.disabled = true;
    }
}

function openBatchHomeworkModal() {
    resetBatchState();
    if (batchExportSelect) {
        const trigger = batchExportSelect.querySelector('.custom-select-trigger');
        const valueSpan = trigger?.querySelector('.custom-select-value');
        if (valueSpan) {
            valueSpan.textContent = '请选择试卷';
        }
        if (batchExportOptions) {
            batchExportOptions.innerHTML = '';
        }
    }
    populateBatchExportOptions();
    openModalElement(batchHomeworkModal);
}

function openClassReportModal() {
    classReportState.exportId = null;
    classReportState.paperTitle = '';
    classReportState.sectionOrder = [];
    classReportState.sections = {};

    if (classReportExportSelect) {
        const trigger = classReportExportSelect.querySelector('.custom-select-trigger');
        const valueSpan = trigger?.querySelector('.custom-select-value');
        if (valueSpan) {
            valueSpan.textContent = '请选择试卷';
        }
        if (classReportExportOptions) {
            classReportExportOptions.innerHTML = '';
        }
    }
    if (classReportContent) {
        classReportContent.classList.add('hidden');
    }
    if (classReportSections) {
        classReportSections.innerHTML = '';
    }
    if (classReportDownloadBtn) {
        classReportDownloadBtn.disabled = true;
    }

    populateClassReportExportOptions();
    openModalElement(classReportModal);
}

function handleBatchFileChange(event) {
    const files = Array.from(event?.target?.files || []);
    batchState.files = files;
    renderBatchUploadSummary();
}

function renderBatchUploadSummary() {
    if (!batchUploadSummary) {
        return;
    }

    if (!batchState.files || batchState.files.length === 0) {
        batchUploadSummary.classList.add('hidden');
        batchUploadSummary.innerHTML = '';
        return;
    }

    const fileNames = batchState.files.map((file) => file.name || '未命名文件');
    batchUploadSummary.innerHTML = `
        <div class="batch-upload-summary-content">
            <i class="fas fa-folder-open"></i>
            <span>已选择 ${batchState.files.length} 个文件</span>
        </div>
        <ul class="batch-upload-file-list">
            ${fileNames.map((name) => `<li title="${name}">${name}</li>`).join('')}
        </ul>
    `;
    batchUploadSummary.classList.remove('hidden');
}

function hasValidBatchEntries() {
    const mappingKeys = Object.keys(batchState.mapping || {});
    if (mappingKeys.length === 0) {
        return false;
    }
    return mappingKeys.some((id) => !id.startsWith('unknown_id'));
}

async function handleBatchParse() {
    if (!batchState.exportId) {
        showMessage('请先选择关联的试卷', 'error');
        return;
    }
    if (!batchState.files || batchState.files.length === 0) {
        showMessage('请先上传作业文件', 'error');
        return;
    }

    if (!batchParseBtn) {
        return;
    }

    const originalText = batchParseBtn.innerHTML;
    batchParseBtn.disabled = true;
    batchParseBtn.innerHTML = '<i class="fas fa-cog fa-spin"></i> 正在解析';

    try {
        const formData = new FormData();
        formData.append('export_id', batchState.exportId);
        batchState.files.forEach((file) => formData.append('files', file));

        const response = await fetch('/api/students/homework/batch-parse', {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();
        if (!result.success) {
            showMessage('批量解析失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        batchState.mapping = result.mapping || {};
        batchState.order = Array.isArray(result.order) ? result.order : Object.keys(batchState.mapping);
        batchState.questions = Array.isArray(result.questions) ? result.questions : [];
        batchState.paperTitle = result.paper_title || '';
        batchState.failures = Array.isArray(result.failures) ? result.failures : [];

        if (batchResultsContainer) {
            batchResultsContainer.classList.remove('hidden');
        }
        renderBatchResultsTable();
        showMessage('批量解析完成', 'success');
    } catch (error) {
        showMessage('批量解析失败: ' + error.message, 'error');
    } finally {
        batchParseBtn.disabled = false;
        batchParseBtn.innerHTML = originalText;
    }
}

function createScoreChip(score, placeholder = '--') {
    if (typeof score === 'number' && !Number.isNaN(score)) {
        const text = formatScore(score);
        const color = getScoreColor(score);
        return `<span class="score-chip" style="background:${color};color:#fff;">${text}</span>`;
    }
    return `<span class="score-chip score-chip-neutral">${placeholder}</span>`;
}

function getStudentNameById(studentId) {
    if (!Array.isArray(studentList)) {
        return '';
    }
    const student = studentList.find((item) => item.student_id === studentId);
    return student ? (student.name || '') : '';
}

function renderBatchResultsTable() {
    if (!batchResultsTableWrapper) {
        return;
    }

    const questions = Array.isArray(batchState.questions) ? batchState.questions : [];
    const columns = questions.map((question) => question.question_number || question.number).filter((num) => num !== undefined);
    const order = Array.isArray(batchState.order) ? batchState.order : [];
    const mapping = batchState.mapping || {};

    const rows = [];
    order.forEach((entryId) => {
        const entry = mapping[entryId];
        if (!entry) {
            return;
        }
        const scoreMap = {};
        (entry.results || []).forEach((item) => {
            if (!item || typeof item !== 'object') {
                return;
            }
            const qnum = item.question_number;
            if (qnum !== undefined && qnum !== null) {
                scoreMap[qnum] = item.score;
            }
        });
        rows.push({
            entryId,
            studentId: entry.student_id || entryId,
            studentName: entry.student_name || getStudentNameById(entry.student_id),
            scores: scoreMap,
            totalScore: entry.total_score,
            assignmentSource: entry.assignment_source || 'auto',
            detectedStudentId: entry.detected_student_id || '',
            detectedStudentName: entry.detected_student_name || '',
        });
    });

    const mappedIds = new Set(order);
    if (Array.isArray(studentList)) {
        studentList.forEach((student) => {
            if (!student.student_id || mappedIds.has(student.student_id)) {
                return;
            }
            rows.push({
                entryId: student.student_id,
                studentId: student.student_id,
                studentName: student.name || '',
                scores: {},
                totalScore: null,
                assignmentSource: 'roster',
                detectedStudentId: '',
                detectedStudentName: '',
                isRosterOnly: true,
            });
        });
    }

    const headerCells = [
        '<th>学号</th>',
        '<th>姓名</th>',
        ...columns.map((num) => `<th>题${num}</th>`),
        '<th>总分</th>',
    ];

    const bodyRows = rows.map((row) => {
        const isUnknown = row.entryId.startsWith('unknown_id');
        const rowClass = [
            'batch-result-row',
            row.isRosterOnly ? 'row-roster' : '',
            isUnknown ? 'row-unknown' : '',
        ].filter(Boolean).join(' ');

        const tags = {
            filename: '文件名匹配',
            llm: '模型识别',
            manual: '手动指定',
            unknown: '未匹配',
            roster: '暂无解析',
        };
        const sourceLabel = tags[row.assignmentSource] || '自动识别';

        const studentCell = isUnknown
            ? `
                <div class="student-cell">
                    <select class="batch-student-select" data-entry-id="${row.entryId}">
                        <option value="">未匹配学生</option>
                        ${(studentList || []).map((student) => `<option value="${student.student_id}">${student.student_id} ${student.name || ''}</option>`).join('')}
                    </select>
                    ${row.detectedStudentId
                        ? `<div class="detected-hint">模型识别：${row.detectedStudentId}${row.detectedStudentName ? `（${row.detectedStudentName}）` : ''}</div>`
                        : ''}
                </div>
            `
            : `
                <div class="student-cell">
                    <div class="student-name">${row.studentName || '—'}</div>
                    ${row.detectedStudentId && row.detectedStudentId !== row.studentId
                        ? `<div class="detected-hint">模型识别：${row.detectedStudentId}${row.detectedStudentName ? `（${row.detectedStudentName}）` : ''}</div>`
                        : ''}
                </div>
            `;

        const scoreCells = columns.map((num) => createScoreChip(row.scores[num]));
        const totalCell = createScoreChip(row.totalScore, '--');

        return `
            <tr class="${rowClass}">
                <td>
                    <div class="student-id">${row.studentId || '—'}</div>
                    <div class="assignment-source">${sourceLabel}</div>
                </td>
                <td>${studentCell}</td>
                ${scoreCells.map((cell) => `<td>${cell}</td>`).join('')}
                <td>${totalCell}</td>
            </tr>
        `;
    }).join('');

    const failures = Array.isArray(batchState.failures) ? batchState.failures : [];
    const failureHtml = failures.length
        ? `
            <div class="batch-failures">
                <h5><i class="fas fa-triangle-exclamation"></i> 未解析的文件</h5>
                <ul>${failures.map((item) => `<li>${item.filename || '未知文件'}：${item.message || '解析失败'}</li>`).join('')}</ul>
            </div>
        `
        : '';

    batchResultsTableWrapper.innerHTML = `
        <div class="table-responsive">
            <table class="batch-results-table">
                <thead>
                    <tr>${headerCells.join('')}</tr>
                </thead>
                <tbody>
                    ${bodyRows || `<tr><td colspan="${columns.length + 3}">暂无解析结果</td></tr>`}
                </tbody>
            </table>
        </div>
        ${failureHtml}
    `;

    if (batchSaveBtn) {
        batchSaveBtn.disabled = !hasValidBatchEntries();
    }
}

function handleBatchMappingSelectChange(event) {
    const select = event.target.closest('.batch-student-select');
    if (!select) {
        return;
    }
    const entryId = select.dataset.entryId;
    const newId = select.value;
    if (!entryId || !newId) {
        return;
    }
    if (batchState.mapping[newId]) {
        showMessage('该学生已有解析结果，请选择其他学生', 'error');
        select.value = '';
        return;
    }
    const entry = batchState.mapping[entryId];
    if (!entry) {
        return;
    }
    delete batchState.mapping[entryId];
    entry.student_id = newId;
    entry.student_name = getStudentNameById(newId) || entry.student_name || '';
    entry.assignment_source = 'manual';
    entry.results = (entry.results || []).map((item) => ({
        ...item,
        student_id: newId,
    }));
    batchState.mapping[newId] = entry;
    const idx = batchState.order.indexOf(entryId);
    if (idx !== -1) {
        batchState.order[idx] = newId;
    }
    renderBatchResultsTable();
}

async function handleBatchSave() {
    if (!batchState.exportId) {
        showMessage('请先选择关联的试卷', 'error');
        return;
    }
    const studentsPayload = Object.keys(batchState.mapping || {})
        .filter((id) => !id.startsWith('unknown_id'))
        .map((id) => {
            const entry = batchState.mapping[id];
            return {
                student_id: id,
                student_name: entry.student_name || getStudentNameById(id) || '',
                results: entry.results || [],
            };
        });

    if (studentsPayload.length === 0) {
        showMessage('暂无可保存的解析结果，请先指定学生', 'error');
        return;
    }

    try {
        showLoading(true);
        const response = await fetch('/api/students/homework/batch-save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                export_id: batchState.exportId,
                paper_title: batchState.paperTitle,
                students: studentsPayload,
            }),
        });
        const result = await response.json();
        if (!result.success) {
            showMessage('批量保存失败: ' + (result.message || '未知错误'), 'error');
            return;
        }
        const savedCount = Array.isArray(result.saved) ? result.saved.length : 0;
        showMessage(`已保存 ${savedCount} 位学生的作业结果`, 'success');
        const skippedEntries = Array.isArray(result.skipped) ? result.skipped.length : 0;
        if (skippedEntries > 0) {
            showMessage(`有 ${skippedEntries} 条解析结果未保存，请在表格中确认学生信息`, 'warning');
        }
        closeModalElement(batchHomeworkModal);
        await loadStudents(false);
    } catch (error) {
        showMessage('批量保存失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function handleClassReportGenerate() {
    if (!classReportState.exportId) {
        showMessage('请先选择试卷', 'error');
        return;
    }
    if (!classReportGenerateBtn) {
        return;
    }

    const originalText = classReportGenerateBtn.innerHTML;
    classReportGenerateBtn.disabled = true;
    classReportGenerateBtn.innerHTML = '<i class="fas fa-cog fa-spin"></i> 正在生成';

    try {
        const response = await fetch('/api/students/class-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ export_id: classReportState.exportId }),
        });
        const result = await response.json();
        if (!result.success) {
            showMessage('生成全班报告失败: ' + (result.message || '未知错误'), 'error');
            return;
        }

        classReportState.paperTitle = result.paper_title || '';
        classReportState.sectionOrder = Array.isArray(result.section_order) ? result.section_order : [];
        classReportState.sections = result.sections || {};

        renderClassReportSections(result);
        showMessage('全班报告生成成功', 'success');
    } catch (error) {
        showMessage('生成全班报告失败: ' + error.message, 'error');
    } finally {
        classReportGenerateBtn.disabled = false;
        classReportGenerateBtn.innerHTML = originalText;
    }
}

function renderClassReportSections(data) {
    if (!classReportSections) {
        return;
    }
    const order = Array.isArray(data.section_order) ? data.section_order : [];
    const sections = data.sections || {};

    const html = order.map((sectionId) => {
        const section = sections[sectionId];
        if (!section) {
            return '';
        }
        if (sectionId === 'class_ranking') {
            return renderClassRankingSection(section);
        }
        if (sectionId === 'question_overview') {
            return renderQuestionOverviewSection(section);
        }
        if (sectionId === 'common_mistakes') {
            return renderCommonMistakesSection(section);
        }
        return '';
    }).join('');

    classReportSections.innerHTML = html || '<div class="empty-state">暂无报告内容。</div>';
    if (classReportContent) {
        classReportContent.classList.remove('hidden');
    }
    if (classReportDownloadBtn) {
        classReportDownloadBtn.disabled = false;
    }
    renderMath();
}

function renderClassRankingSection(section) {
    const questions = Array.isArray(section.questions) ? section.questions : [];
    const rows = Array.isArray(section.rows) ? section.rows : [];
    const headers = [
        '<th>学号</th>',
        '<th>姓名</th>',
        ...questions.map((question) => `<th>题${question.question_number || question.number}</th>`),
        '<th>总分</th>',
        '<th>排名</th>',
    ];

    const body = rows.map((row) => {
        const scores = row.scores || {};
        const rowType = row.row_type || '';
        const rowClass = [
            rowType === 'average' ? 'report-row-average' : '',
            rowType === 'roster_only' ? 'report-row-roster' : '',
        ].filter(Boolean).join(' ');
        const questionCells = questions.map((question) => {
            const qnum = question.question_number || question.number;
            return `<td>${createScoreChip(scores[qnum])}</td>`;
        }).join('');
        const rank = row.rank === undefined || row.rank === '-' || row.rank === null
            ? '-'
            : `<span class="rank-badge">#${row.rank}</span>`;
        return `
            <tr class="${rowClass}">
                <td>${row.student_id || '—'}</td>
                <td>${row.student_name || '—'}</td>
                ${questionCells}
                <td>${createScoreChip(row.total_score)}</td>
                <td>${rank}</td>
            </tr>
        `;
    }).join('');

    return `
        <section class="class-report-section">
            <h4><i class="fas fa-trophy"></i> ${section.title || '全班排名'}</h4>
            <div class="table-responsive">
                <table class="class-report-table">
                    <thead>
                        <tr>${headers.join('')}</tr>
                    </thead>
                    <tbody>${body}</tbody>
                </table>
            </div>
        </section>
    `;
}

function renderQuestionOverviewSection(section) {
    const rows = Array.isArray(section.rows) ? section.rows : [];
    const body = rows.map((row) => {
        const tags = Array.isArray(row.tags) ? row.tags : [];
        const tagHtml = tags.length
            ? `<div class="tag-list">${tags.map((tag) => `<span class="tag">${tag}</span>`).join('')}</div>`
            : '<span class="tag tag-ghost">无标签</span>';
        return `
            <tr>
                <td>题${row.question_number}</td>
                <td>${tagHtml}</td>
                <td>${createScoreChip(row.average_score)}</td>
                <td>${createScoreChip(row.full_score_rate)}</td>
            </tr>
        `;
    }).join('');

    return `
        <section class="class-report-section">
            <h4><i class="fas fa-list-ul"></i> ${section.title || '题目总览'}</h4>
            <div class="table-responsive">
                <table class="class-report-table">
                    <thead>
                        <tr>
                            <th>题目</th>
                            <th>标签</th>
                            <th>平均得分</th>
                            <th>满分率</th>
                        </tr>
                    </thead>
                    <tbody>${body}</tbody>
                </table>
            </div>
        </section>
    `;
}

function renderCommonMistakesSection(section) {
    const cards = Array.isArray(section.cards) ? section.cards : [];
    if (cards.length === 0) {
        return `
            <section class="class-report-section">
                <h4><i class="fas fa-triangle-exclamation"></i> ${section.title || '高频错题'}</h4>
                <div class="empty-state">暂无高频错题。</div>
            </section>
        `;
    }
    const cardHtml = cards.map((card) => {
        const tags = Array.isArray(card.tags) ? card.tags : [];
        const tagHtml = tags.length
            ? `<div class="tag-list">${tags.map((tag) => `<span class="tag">${tag}</span>`).join('')}</div>`
            : '<span class="tag tag-ghost">无标签</span>';
        const questionHtml = renderMathContent(card.latex_content || '');
        return `
            <div class="mistake-card">
                <div class="mistake-card-header">
                    <span class="card-title">题目 ${card.question_number}</span>
                    ${tagHtml}
                </div>
                <div class="mistake-card-meta">
                    <span>平均得分：${createScoreChip(card.average_score)}</span>
                    <span>满分率：${createScoreChip(card.full_score_rate)}</span>
                </div>
                <div class="mistake-card-content limited-content">
                    ${questionHtml || '暂无题面内容'}
                </div>
            </div>
        `;
    }).join('');

    return `
        <section class="class-report-section">
            <h4><i class="fas fa-triangle-exclamation"></i> ${section.title || '高频错题'}</h4>
            <div class="mistake-card-grid">
                ${cardHtml}
            </div>
        </section>
    `;
}

async function handleClassReportDownload() {
    if (!classReportState.exportId) {
        showMessage('请先选择试卷', 'error');
        return;
    }
    try {
        showLoading(true);
        const response = await fetch('/api/students/class-report/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ export_id: classReportState.exportId }),
        });
        const result = await response.json();
        if (!result.success) {
            showMessage('下载报告失败: ' + (result.message || '未知错误'), 'error');
            return;
        }
        const filename = `${result.paper_title || classReportState.paperTitle || '全班报告'}.pdf`;
        downloadPdfBase64(result.pdf_base64, filename);
    } catch (error) {
        showMessage('下载报告失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function downloadPdfBase64(base64, filename) {
    if (!base64) {
        return;
    }
    const binary = atob(base64);
    const length = binary.length;
    const bytes = new Uint8Array(length);
    for (let i = 0; i < length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    const blob = new Blob([bytes], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'report.pdf';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
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
window.openBatchHomeworkModal = openBatchHomeworkModal;
window.populateBatchExportOptions = populateBatchExportOptions;
window.handleBatchFileChange = handleBatchFileChange;
window.handleBatchParse = handleBatchParse;
window.handleBatchSave = handleBatchSave;
window.handleBatchMappingSelectChange = handleBatchMappingSelectChange;
window.openClassReportModal = openClassReportModal;
window.populateClassReportExportOptions = populateClassReportExportOptions;
window.handleClassReportGenerate = handleClassReportGenerate;
window.handleClassReportDownload = handleClassReportDownload;

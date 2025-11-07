// 试卷扫描与解析模块

async function handleImageUpload(e) {
    const files = Array.from(e.target.files || []);

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

function addImagePreview(url, filename) {
    if (!imagePreview) {
        return;
    }
    const previewItem = document.createElement('div');
    previewItem.className = 'image-preview-item';
    previewItem.innerHTML = `
        <img src="${url}" alt="${filename}">
        <button type="button" class="remove-btn" onclick="removeImage('${url}')">&times;</button>
    `;
    imagePreview.appendChild(previewItem);
}

function removeImage(url) {
    uploadedImages = uploadedImages.filter(img => img !== url);
    if (!imagePreview) {
        return;
    }
    const previewItems = imagePreview.querySelectorAll('.image-preview-item');
    previewItems.forEach(item => {
        const imgEl = item.querySelector('img');
        if (imgEl && imgEl.getAttribute('src') === url) {
            item.remove();
        }
    });
}

async function handleExamUpload(e) {
    const file = e.target.files?.[0];
    if (!file || !examPreview) {
        return;
    }

    const uploadZone = document.getElementById('upload-zone');
    if (uploadZone) {
        uploadZone.style.display = 'none';
    }

    examPreview.style.display = 'block';

    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');

    const previewContainer = examPreview.querySelector('.preview-image');
    const previewFilename = examPreview.querySelector('.preview-filename');
    const previewMetaType = examPreview.querySelector('.preview-filetype');

    if (previewFilename) {
        previewFilename.textContent = file.name;
    }
    if (previewMetaType) {
        const ext = (file.name.split('.').pop() || '').toUpperCase();
        previewMetaType.textContent = isPdf
            ? 'PDF 文档'
            : file.type
                ? file.type
                : ext
                    ? `.${ext}`
                    : '未知类型';
    }

    if (!previewContainer) {
        return;
    }
    previewContainer.innerHTML = '';

    if (isPdf) {
        previewContainer.innerHTML = `
            <div class="preview-loading">
                <i class="fas fa-spinner fa-spin"></i>
                <span>正在生成 PDF 预览...</span>
            </div>
        `;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/pdf-preview', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.success && result.preview) {
                const previewSrc = result.preview.startsWith('data:')
                    ? result.preview
                    : `data:image/png;base64,${result.preview}`;
                previewContainer.innerHTML = `<img src="${previewSrc}" alt="PDF预览第一页">`;
            } else {
                const message = result.message || '无法生成PDF预览';
                previewContainer.innerHTML = `
                    <div class="preview-error">
                        <i class="fas fa-triangle-exclamation"></i>
                        <span>${message}</span>
                    </div>
                `;
                showMessage(`PDF预览失败: ${message}`, 'error');
            }
        } catch (error) {
            previewContainer.innerHTML = `
                <div class="preview-error">
                    <i class="fas fa-triangle-exclamation"></i>
                    <span>PDF预览失败: ${error.message}</span>
                </div>
            `;
            showMessage('PDF预览失败: ' + error.message, 'error');
        }
    } else {
        const reader = new FileReader();
        reader.onload = (event) => {
            previewContainer.innerHTML = `<img src="${event.target.result}" alt="试卷预览">`;
        };
        reader.readAsDataURL(file);
    }
}

function removeExam() {
    const uploadZone = document.getElementById('upload-zone');
    if (uploadZone) {
        uploadZone.style.display = 'block';
    }
    if (examPreview) {
        examPreview.style.display = 'none';
        const previewContainer = examPreview.querySelector('.preview-image');
        if (previewContainer) {
            previewContainer.innerHTML = '';
        }
        const previewFilename = examPreview.querySelector('.preview-filename');
        if (previewFilename) {
            previewFilename.textContent = '';
        }
        const previewMetaType = examPreview.querySelector('.preview-filetype');
        if (previewMetaType) {
            previewMetaType.textContent = '';
        }
    }
    if (examUpload) {
        examUpload.value = '';
    }
    if (parsedQuestionsDiv) {
        parsedQuestionsDiv.style.display = 'none';
    }
    parsedQuestions = [];
}

async function handleParseExam() {
    if (!examUpload || !parseExamBtn) {
        return;
    }

    const file = examUpload.files?.[0];
    if (!file) {
        showMessage('请先选择试卷文件', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const originalBtnText = parseExamBtn.innerHTML;
    parseExamBtn.disabled = true;
    parseExamBtn.classList.add('parsing');

    let progress = 0;
    const config = APP_CONFIG.parsingProgress;
    const progressInterval = setInterval(() => {
        progress += config.increment;
        if (progress > config.maxProgress) {
            progress = config.maxProgress;
        }
        parseExamBtn.innerHTML = `<i class="fas fa-cog fa-spin"></i> 正在解析 ${Math.floor(progress)}%`;
    }, config.interval);

    try {
        const response = await fetch('/api/ocr-parse', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        clearInterval(progressInterval);
        parseExamBtn.innerHTML = '<i class="fas fa-cogs"></i> 开始解析';
        parseExamBtn.disabled = false;
        parseExamBtn.classList.remove('parsing');

        if (result.success) {
            parsedQuestions = result.questions || [];

            if (!parsedQuestions || parsedQuestions.length === 0) {
                showMessage('试卷解析完成，但没有识别出任何题目', 'warning');
                if (parsedQuestionsDiv) {
                    parsedQuestionsDiv.style.display = 'none';
                }
            } else {
                renderParsedQuestions();
                if (parsedQuestionsDiv) {
                    parsedQuestionsDiv.style.display = 'block';
                }
                const parsedCount = document.getElementById('parsed-count');
                if (parsedCount) {
                    parsedCount.textContent = parsedQuestions.length;
                }
                showMessage(`试卷解析成功！共识别出 ${parsedQuestions.length} 道题目`, 'success');
            }
        } else {
            showMessage('试卷解析失败: ' + result.message, 'error');
        }
    } catch (error) {
        clearInterval(progressInterval);
        parseExamBtn.innerHTML = originalBtnText;
        parseExamBtn.disabled = false;
        parseExamBtn.classList.remove('parsing');
        showMessage('试卷解析失败: ' + error.message, 'error');
    }
}

function renderParsedQuestions() {
    if (!parsedQuestionsList) {
        return;
    }

    if (!parsedQuestions || parsedQuestions.length === 0) {
        parsedQuestionsList.innerHTML = '<div class="no-results">没有解析出任何题目</div>';
        return;
    }

    parsedQuestionsList.innerHTML = parsedQuestions.map((question, index) => {
        const questionText = question.question || question.latex_content || '题目内容缺失';
        const questionImages = question.image || [];
        const questionTags = question.tags || [];
        const questionAnswer = question.answer || '';

        const imagesHtml = questionImages.length > 0
            ? `<div class="question-images">${questionImages.map(img => {
                let imageSrc = img;
                if (imageSrc.startsWith('/uploads/')) {
                    imageSrc = imageSrc.replace('/uploads/', '/images/');
                }
                const imageScale = APP_CONFIG.imageDisplay.defaultScale;
                return `<img src="${imageSrc}" style="max-width: ${imageScale * 100}%; margin: 5px;">`;
            }).join('')}</div>`
            : '';

        const tagsHtml = questionTags.length > 0
            ? `<div class="parsed-tags"><strong>标签：</strong>${questionTags.map(tag => `<span class="parsed-tag">${tag}</span>`).join('')}</div>`
            : '';

        const answerHtml = questionAnswer
            ? `<div class="parsed-answer"><strong>解答：</strong><div class="parsed-answer-content">${renderMathContent(questionAnswer)}</div></div>`
            : '';

        return `
            <div class="parsed-question-item">
                <h5>
                    <input type="checkbox" checked data-index="${index}" style="margin-right: 10px;">
                    题目 ${index + 1}
                </h5>
                <div class="parsed-question-content limited-content">
                    ${renderMathContent(questionText)}
                </div>
                <div class="parsed-meta"><strong>题型：</strong>${question.question_type || '解答题'}</div>
                ${imagesHtml}
                ${tagsHtml}
                ${answerHtml}
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

async function handleBatchSave() {
    if (!parsedQuestions || parsedQuestions.length === 0) {
        showMessage('没有可保存的题目', 'error');
        return;
    }

    const checkedBoxes = document.querySelectorAll('#parsed-questions-list input[type="checkbox"]:checked');
    const selectedIndices = Array.from(checkedBoxes).map(cb => parseInt(cb.dataset.index, 10)).filter(idx => !Number.isNaN(idx));

    if (selectedIndices.length === 0) {
        showMessage('请至少选择一个题目', 'error');
        return;
    }

    const visibility = document.querySelector('input[name="ocr-visibility"]:checked')?.value || 'public';
    const sourceInput = document.getElementById('ocr-source');
    const source = sourceInput ? (sourceInput.value.trim() || '试卷解析') : '试卷解析';

    try {
        showLoading(true);
        let successCount = 0;

        for (const index of selectedIndices) {
            const question = parsedQuestions[index];
            if (!question) {
                continue;
            }
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
                successCount += 1;
            }
        }

        showMessage(`成功保存 ${successCount} 道题目！`, 'success');
        parsedQuestions = [];
        if (parsedQuestionsDiv) {
            parsedQuestionsDiv.style.display = 'none';
        }
        removeExam();
    } catch (error) {
        showMessage('批量保存失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function addParsedToCart(index) {
    const question = parsedQuestions[index];
    if (!question) {
        return;
    }

    const tempId = `parsed_${index}_${Date.now()}`;
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

window.handleImageUpload = handleImageUpload;
window.addImagePreview = addImagePreview;
window.removeImage = removeImage;
window.handleExamUpload = handleExamUpload;
window.removeExam = removeExam;
window.handleParseExam = handleParseExam;
window.renderParsedQuestions = renderParsedQuestions;
window.handleBatchSave = handleBatchSave;
window.addParsedToCart = addParsedToCart;

// 购物车与试卷导出模块

const CART_PREVIEW_MAX_CHARS = APP_CONFIG.content?.cartPreviewMaxChars || 120;

async function addToCart(questionId) {
    try {
        const response = await fetch(`/api/questions/${questionId}`);
        const result = await response.json();

        if (result.success) {
            const question = result.question;

            if (cart.find(item => item.id === questionId)) {
                showMessage('该题目已在试卷中', 'warning');
                return;
            }

            cart.push(question);
            updateCartBadge();
            showMessage('已加入试卷', 'success');
        } else {
            showMessage('添加失败: ' + (result.message || '未知错误'), 'error');
        }
    } catch (error) {
        showMessage('添加失败: ' + error.message, 'error');
    }
}

function updateCartBadge() {
    if (cartBadge) {
        cartBadge.textContent = cart.length;
    }
}

function openCartModal() {
    renderCart();
    if (cartModal) {
        cartModal.style.display = 'block';
    }
}

function closeCartModal() {
    if (cartModal) {
        cartModal.style.display = 'none';
    }
}

function truncatePlainText(html, maxChars) {
    if (!html || maxChars <= 0) {
        return '';
    }
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    const text = tempDiv.textContent || tempDiv.innerText || '';
    if (text.length <= maxChars) {
        return text;
    }
    return text.slice(0, maxChars).trim() + '…';
}

function renderCart() {
    const cartItemsDiv = document.getElementById('cart-items');
    if (!cartItemsDiv) {
        return;
    }

    if (cart.length === 0) {
        cartItemsDiv.innerHTML = `
            <div class="cart-empty">
                <i class="fas fa-shopping-cart"></i>
                <p>试卷为空，请先添加题目</p>
            </div>
        `;
        return;
    }

    cartItemsDiv.innerHTML = cart.map((item, index) => {
        const previewText = truncatePlainText(renderMathContent(item.latex_content), CART_PREVIEW_MAX_CHARS);
        const tagsHtml = Array.isArray(item.tags) && item.tags.length > 0
            ? item.tags.map(tag => `<span class="question-tag">${tag}</span>`).join('')
            : '';

        return `
            <div class="cart-item" data-index="${index}">
                <div class="cart-item-actions">
                    ${index > 0 ? `<button class="cart-item-btn btn-move-up" onclick="moveCartItem(${index}, -1)">
                        <i class="fas fa-arrow-up"></i>
                    </button>` : ''}
                    ${index < cart.length - 1 ? `<button class="cart-item-btn btn-move-down" onclick="moveCartItem(${index}, 1)">
                        <i class="fas fa-arrow-down"></i>
                    </button>` : ''}
                </div>
                <div class="cart-item-content">
                    <div class="cart-item-title">
                        题目 ${index + 1}
                        ${tagsHtml ? `<div class="question-tags">${tagsHtml}</div>` : ''}
                    </div>
                    <div class="cart-item-preview" title="${previewText}">${previewText}</div>
                </div>
                <div class="cart-item-remove">
                    <button class="cart-item-btn btn-remove-cart" onclick="removeFromCart(${index})">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function moveCartItem(index, direction) {
    const newIndex = index + direction;
    if (newIndex >= 0 && newIndex < cart.length) {
        [cart[index], cart[newIndex]] = [cart[newIndex], cart[index]];
        renderCart();
    }
}

function removeFromCart(index) {
    cart.splice(index, 1);
    updateCartBadge();
    renderCart();
    showMessage('已从试卷中移除', 'success');
}

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

async function exportPaper() {
    if (cart.length === 0) {
        showMessage('试卷为空，无法导出', 'error');
        return;
    }

    const titleInput = document.getElementById('export-title');
    const title = titleInput ? (titleInput.value || '数学试卷') : '数学试卷';
    const mode = document.querySelector('input[name="export-mode"]:checked')?.value || 'questions';
    const format = document.querySelector('input[name="export-format"]:checked')?.value || 'pdf';

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

            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            const timeStr = `${year}${month}${day}_${hours}${minutes}${seconds}`;

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
            showMessage('导出失败: ' + (result.message || '未知错误'), 'error');
        }
    } catch (error) {
        showMessage('导出失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

window.addToCart = addToCart;
window.updateCartBadge = updateCartBadge;
window.openCartModal = openCartModal;
window.closeCartModal = closeCartModal;
window.renderCart = renderCart;
window.moveCartItem = moveCartItem;
window.removeFromCart = removeFromCart;
window.clearCart = clearCart;
window.exportPaper = exportPaper;

// 全局帮助弹窗逻辑
(function () {
    const HELP_FALLBACK = {
        title: '使用帮助',
        description: '暂未配置详细帮助信息，请稍后再试。'
    };

    function escapeHtml(text = '') {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderList(items = []) {
        if (!Array.isArray(items) || items.length === 0) {
            return '';
        }
        return `<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
    }

    function buildHelpHtml(entry) {
        const parts = [];
        if (entry.description) {
            parts.push(`<p>${escapeHtml(entry.description)}</p>`);
        }
        if (entry.steps && entry.steps.length > 0) {
            parts.push('<strong>操作步骤</strong>');
            parts.push(renderList(entry.steps));
        }
        if (entry.tips && entry.tips.length > 0) {
            parts.push('<strong>小提示</strong>');
            parts.push(renderList(entry.tips));
        }
        return parts.join('');
    }

    function getHelpEntry(key) {
        if (!key) {
            return HELP_FALLBACK;
        }
        const source = window.HELP_CONTENT || {};
        return source[key] || HELP_FALLBACK;
    }

    function getModalElements() {
        const modal = document.getElementById('help-modal');
        if (!modal) {
            return {};
        }
        return {
            modal,
            title: modal.querySelector('#help-modal-title'),
            body: modal.querySelector('#help-modal-body')
        };
    }

    function openHelpModal(key) {
        const { modal, title, body } = getModalElements();
        if (!modal || !body) {
            console.warn('未找到帮助弹窗容器');
            return;
        }
        const entry = getHelpEntry(key);
        if (title) {
            title.textContent = entry.title || '使用帮助';
        }
        body.innerHTML = buildHelpHtml(entry);
        modal.style.display = 'block';
    }

    function closeHelpModal() {
        const { modal } = getModalElements();
        if (modal) {
            modal.style.display = 'none';
        }
    }

    function onTriggerClick(event) {
        const trigger = event.target.closest('[data-help-key]');
        if (!trigger) {
            return;
        }
        event.preventDefault();
        const key = trigger.getAttribute('data-help-key');
        openHelpModal(key);
    }

    document.addEventListener('DOMContentLoaded', () => {
        const { modal } = getModalElements();
        if (!modal) {
            return;
        }

        document.body.addEventListener('click', onTriggerClick);

        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeHelpModal();
            }
        });

        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', closeHelpModal);
        }

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeHelpModal();
            }
        });
    });

    window.openHelpModal = openHelpModal;
    window.closeHelpModal = closeHelpModal;
})();

/**
 * Честный ЗНАК — Модуль отслеживания сроков годности пива
 * Интеграция с API Честный ЗНАК для мониторинга остатков
 */

const CZ = (function() {
    // Состояние модуля
    let state = {
        isConnected: false,
        isLoading: false,
        data: null,
        error: null
    };

    // DOM элементы
    const elements = {};

    /**
     * Инициализация модуля
     */
    function init() {
        console.log('[CZ] Инициализация модуля Честный ЗНАК');

        // Кэшируем DOM элементы
        cacheElements();

        // Навешиваем обработчики событий
        attachEventListeners();

        // Проверяем подключение при загрузке
        checkConnection();
    }

    /**
     * Кэширование DOM элементов
     */
    function cacheElements() {
        elements.container = document.getElementById('expiry-container');
        elements.loading = document.getElementById('expiry-loading');
        elements.noData = document.getElementById('expiry-no-data');
        elements.error = document.getElementById('expiry-error');
        elements.errorMessage = document.getElementById('expiry-error-message');
        elements.tableBody = document.getElementById('expiry-table-body');

        // Summary элементы
        elements.summaryExpired = document.getElementById('summary-expired');
        elements.summaryExpiringSoon = document.getElementById('summary-expiring-soon');
        elements.summaryTotal = document.getElementById('summary-total');
        elements.summaryGtin = document.getElementById('summary-gtin');

        // Controls
        elements.innInput = document.getElementById('expiry-inn-input');
        elements.daysInput = document.getElementById('expiry-days-input');
        elements.refreshBtn = document.getElementById('btn-refresh-expiry');
    }

    /**
     * Обработчики событий
     */
    function attachEventListeners() {
        if (elements.refreshBtn) {
            elements.refreshBtn.addEventListener('click', handleRefresh);
        }

        // Enter key для INN input
        if (elements.innInput) {
            elements.innInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    handleRefresh();
                }
            });
        }
    }

    /**
     * Проверка подключения к API
     */
    async function checkConnection() {
        try {
            const response = await fetch('/api/chestny-znak/status');
            const data = await response.json();

            state.isConnected = data.connected;
            console.log('[CZ] Статус подключения:', state.isConnected);

            if (!state.isConnected) {
                // Показываем кнопку подключения или уведомление
                console.log('[CZ] Требуется подключение к API');
            }
        } catch (error) {
            console.error('[CZ] Ошибка проверки подключения:', error);
            state.isConnected = false;
        }
    }

    /**
     * Обработчик кнопки обновления
     */
    function handleRefresh() {
        const inn = elements.innInput?.value?.trim();
        const days = parseInt(elements.daysInput?.value) || 30;

        if (!inn || !/^\d{10,12}$/.test(inn)) {
            showMessage('error', 'Введите корректный ИНН (10-12 цифр)');
            return;
        }

        loadExpiringCodes(inn, days);
    }

    /**
     * Загрузка данных об истекающих кодах
     */
    async function loadExpiringCodes(participantInn, daysThreshold) {
        if (state.isLoading) {
            console.log('[CZ] Уже идет загрузка...');
            return;
        }

        state.isLoading = true;
        state.error = null;
        state.data = null;

        showLoading();

        try {
            console.log(`[CZ] Запрос данных: INN=${participantInn}, days=${daysThreshold}`);

            const response = await fetch('/api/chestny-znak/expiring', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    participantInn: participantInn,
                    daysThreshold: daysThreshold
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.success) {
                state.data = result;
                renderData(result);
            } else {
                throw new Error(result.message || 'Не удалось получить данные');
            }

        } catch (error) {
            console.error('[CZ] Ошибка загрузки:', error);
            state.error = error.message;
            showError(error.message);
        } finally {
            state.isLoading = false;
        }
    }

    /**
     * Рендеринг данных
     */
    function renderData(result) {
        const { summary, codes } = result;

        // Обновляем summary
        if (elements.summaryExpired) {
            elements.summaryExpired.textContent = summary.expired;
        }
        if (elements.summaryExpiringSoon) {
            elements.summaryExpiringSoon.textContent = summary.expiringSoon;
        }
        if (elements.summaryTotal) {
            elements.summaryTotal.textContent = summary.total;
        }

        // Подсчет уникальных GTIN
        const uniqueGtins = new Set(codes.map(c => c.gtin)).size;
        if (elements.summaryGtin) {
            elements.summaryGtin.textContent = uniqueGtins;
        }

        // Рендеринг таблицы
        renderTable(codes);

        // Показываем контейнер
        if (elements.container) {
            elements.container.classList.remove('hidden');
        }
    }

    /**
     * Рендеринг таблицы кодов
     */
    function renderTable(codes) {
        if (!elements.tableBody) return;

        if (!codes || codes.length === 0) {
            elements.tableBody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 40px; color: #999;">
                        Нет кодов с истекающим сроком годности
                    </td>
                </tr>
            `;
            return;
        }

        const html = codes.map(code => {
            const isExpired = code.isExpired;
            const daysLeft = code.daysUntilExpiry;

            // Определяем стиль статуса
            let statusClass = 'status-badge ';
            let statusText = '';

            if (isExpired) {
                statusClass += 'status-badge--expired';
                statusText = 'Просрочено';
            } else if (daysLeft <= 7) {
                statusClass += 'status-badge--critical';
                statusText = `7 дней`;
            } else if (daysLeft <= 14) {
                statusClass += 'status-badge--warning';
                statusText = `${daysLeft} дн.`;
            } else {
                statusClass += 'status-badge--normal';
                statusText = `${daysLeft} дн.`;
            }

            // Форматирование дат
            const expDate = formatDate(code.expirationDate);
            const prodDate = formatDate(code.productionDate);

            // Сокращение кода для отображения
            const cisShort = shortenCode(code.cis);

            return `
                <tr class="expiry-table-row ${isExpired ? 'row--expired' : ''}">
                    <td>
                        <span class="${statusClass}">${statusText}</span>
                    </td>
                    <td>
                        <code class="code-display" title="${code.cis}">${cisShort}</code>
                    </td>
                    <td>
                        <span class="gtin-display">${code.gtin || '—'}</span>
                    </td>
                    <td>${prodDate}</td>
                    <td class="expiry-date ${isExpired ? 'date--expired' : ''}">${expDate}</td>
                    <td class="days-left ${getDaysClass(daysLeft, isExpired)}">
                        ${formatDaysLeft(daysLeft, isExpired)}
                    </td>
                    <td>${formatInn(code.producerInn)}</td>
                    <td>${formatInn(code.ownerInn)}</td>
                </tr>
            `;
        }).join('');

        elements.tableBody.innerHTML = html;
    }

    /**
     * Форматирование даты из ISO строки
     */
    function formatDate(isoString) {
        if (!isoString) return '—';

        try {
            const date = new Date(isoString);
            return date.toLocaleDateString('ru-RU', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit'
            });
        } catch (e) {
            return isoString.substring(0, 10);
        }
    }

    /**
     * Сокращение длинного кода
     */
    function shortenCode(code) {
        if (!code) return '—';
        if (code.length <= 20) return code;

        return `${code.substring(0, 10)}...${code.substring(code.length - 8)}`;
    }

    /**
     * Класс для дней до истечения
     */
    function getDaysClass(days, isExpired) {
        if (isExpired) return 'days--expired';
        if (days <= 7) return 'days--critical';
        if (days <= 14) return 'days--warning';
        return 'days--normal';
    }

    /**
     * Форматирование отображения дней
     */
    function formatDaysLeft(days, isExpired) {
        if (isExpired) {
            return `Просрочено (${Math.abs(days)} дн. назад)`;
        }

        const dayWord = getDayWord(days);

        if (days === 0) {
            return 'Истекает сегодня';
        }

        return `${days} ${dayWord}`;
    }

    /**
     * Склонение слова "день"
     */
    function getDayWord(days) {
        const lastDigit = days % 10;
        const lastTwoDigits = days % 100;

        if (lastTwoDigits >= 11 && lastTwoDigits <= 19) {
            return 'дней';
        }

        if (lastDigit === 1) {
            return 'день';
        }

        if (lastDigit >= 2 && lastDigit <= 4) {
            return 'дня';
        }

        return 'дней';
    }

    /**
     * Форматирование ИНН
     */
    function formatInn(inn) {
        if (!inn) return '—';
        return inn;
    }

    /**
     * Показ loading состояния
     */
    function showLoading() {
        hideAll();
        if (elements.loading) {
            elements.loading.classList.remove('hidden');
        }
    }

    /**
     * Показ ошибки
     */
    function showError(message) {
        hideAll();
        if (elements.error) {
            elements.error.classList.remove('hidden');
        }
        if (elements.errorMessage) {
            elements.errorMessage.textContent = message || 'Неизвестная ошибка';
        }
    }

    /**
     * Показ no-data состояния
     */
    function showNoData() {
        hideAll();
        if (elements.noData) {
            elements.noData.classList.remove('hidden');
        }
    }

    /**
     * Скрыть все состояния
     */
    function hideAll() {
        [elements.container, elements.loading, elements.noData, elements.error].forEach(el => {
            if (el) el.classList.add('hidden');
        });
    }

    /**
     * Показ сообщения пользователю
     */
    function showMessage(type, text) {
        // Используем существующую систему сообщений из dashboard
        const messagesContainer = document.getElementById('messages-container');
        if (!messagesContainer) return;

        const messageEl = document.createElement('div');
        messageEl.className = `message message--${type}`;
        messageEl.textContent = text;

        messagesContainer.appendChild(messageEl);

        setTimeout(() => {
            messageEl.remove();
        }, 5000);
    }

    // Публичный API
    return {
        init: init,
        refresh: handleRefresh,
        checkConnection: checkConnection
    };
})();

// Авто-инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Проверяем, есть ли элементы модуля на странице
    if (document.getElementById('expiry-container') || document.getElementById('expiry-loading')) {
        CZ.init();
    }
});

// Экспорт для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CZ;
}

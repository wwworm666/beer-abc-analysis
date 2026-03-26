/**
 * PWA Widget для отображения выручки по барам
 * Главный экран: 5 карточек с процентами выполнения
 * Детальный экран: 4 карточки с метриками бара
 */

// Утилиты
function formatMoney(value) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(value);
}

function getStatusClass(percent) {
    if (percent >= 100) return 'success';
    if (percent >= 80) return 'warning';
    return 'danger';
}

function formatDateRange() {
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const options = { day: 'numeric', month: 'long' };
    return `${monthStart.toLocaleDateString('ru-RU', options)} — ${now.toLocaleDateString('ru-RU', options)}`;
}

/**
 * Основной контроллер виджета
 */
class WidgetController {
    constructor() {
        this.currentView = 'main';
        this.barsData = [];
        this.selectedBar = null;
        this.deferredPrompt = null;
        this.elements = {};
    }

    /**
     * Кэширование DOM элементов
     */
    cacheElements() {
        this.elements = {
            loading: document.getElementById('loading'),
            error: document.getElementById('error'),
            mainView: document.getElementById('main-view'),
            detailView: document.getElementById('detail-view'),
            cardsGrid: document.getElementById('cards-grid'),
            detailCards: document.getElementById('detail-cards'),
            detailTitle: document.getElementById('detail-title'),
            dateRange: document.getElementById('date-range'),
            installPrompt: document.getElementById('install-prompt'),
            refreshBtn: document.getElementById('refresh-btn'),
            backBtn: document.getElementById('back-btn'),
            retryBtn: document.getElementById('retry-btn'),
            installBtn: document.getElementById('install-btn'),
            dismissInstall: document.getElementById('dismiss-install')
        };
    }

    /**
     * Инициализация виджета
     */
    init() {
        this.cacheElements();
        this.setupNavigation();
        this.setupInstallPrompt();

        // Регистрируем SW асинхронно (не блокирует UI)
        this.registerServiceWorker();

        // Загружаем данные сразу (не блокируем await)
        this.loadRevenueData();
    }

    /**
     * Регистрация Service Worker (фоновая, не блокирует)
     */
    registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/static/service-worker.js', {
                scope: '/'
            }).then(reg => {
                console.log('[Widget] SW registered:', reg.scope);
            }).catch(err => {
                console.error('[Widget] SW registration failed:', err);
            });
        }
    }

    /**
     * Настройка навигации
     */
    setupNavigation() {
        // Кнопка обновления
        this.elements.refreshBtn?.addEventListener('click', () => {
            this.loadRevenueData();
        });

        // Кнопка назад
        this.elements.backBtn?.addEventListener('click', () => {
            this.showMainView();
        });

        // Повторная попытка загрузки
        this.elements.retryBtn?.addEventListener('click', () => {
            this.loadRevenueData();
        });
    }

    /**
     * Настройка install prompt
     */
    setupInstallPrompt() {
        // Слушаем событие beforeinstallprompt
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            this.showInstallPrompt();
        });

        // Кнопка установки
        this.elements.installBtn?.addEventListener('click', async () => {
            if (this.deferredPrompt) {
                this.deferredPrompt.prompt();
                const { outcome } = await this.deferredPrompt.userChoice;
                console.log('[Widget] Install prompt outcome:', outcome);
                this.deferredPrompt = null;
                this.hideInstallPrompt();
            }
        });

        // Кнопка закрытия
        this.elements.dismissInstall?.addEventListener('click', () => {
            this.hideInstallPrompt();
        });

        // Проверка, запущено ли как PWA
        if (window.matchMedia('(display-mode: standalone)').matches) {
            console.log('[Widget] Running as standalone PWA');
        }
    }

    showInstallPrompt() {
        this.elements.installPrompt?.classList.remove('hidden');
    }

    hideInstallPrompt() {
        this.elements.installPrompt?.classList.add('hidden');
    }

    /**
     * Загрузка данных для главного экрана
     */
    async loadRevenueData() {
        this.showLoading();

        try {
            const response = await fetch('/api/widget/revenue');

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.barsData = data;

            this.renderMainView();
            this.showMainView();
            this.updateDateRange();

        } catch (error) {
            console.error('[Widget] Error loading revenue data:', error);
            this.showError();
        }
    }

    /**
     * Загрузка детальных данных по бару
     */
    async loadBarDetail(barKey) {
        this.showLoading();

        try {
            // Определяем период (с 1-го числа по сегодня)
            const now = new Date();
            const year = now.getFullYear();
            const month = now.getMonth();
            const day = now.getDate();

            const dateFrom = `${year}-${String(month + 1).padStart(2, '0')}-01`;
            const dateTo = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

            const response = await fetch('/api/revenue-metrics', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    bar: barKey,
                    date_from: dateFrom,
                    date_to: dateTo
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.selectedBar = data;

            this.renderDetailView();
            this.showDetailView();

        } catch (error) {
            console.error('[Widget] Error loading bar detail:', error);
            this.showError();
        }
    }

    /**
     * Рендер главного экрана
     */
    renderMainView() {
        const container = this.elements.cardsGrid;
        if (!container) return;

        container.innerHTML = '';

        this.barsData.forEach(bar => {
            const card = this.createMainCard(bar);
            container.appendChild(card);
        });
    }

    /**
     * Создание карточки для главного экрана
     */
    createMainCard(bar) {
        const card = document.createElement('div');
        card.className = 'widget-card';
        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');

        const statusClass = getStatusClass(bar.completion);

        card.innerHTML = `
            <div class="widget-card-header">
                <span class="widget-card-name">${bar.name}</span>
                <div class="widget-card-status ${statusClass}"></div>
            </div>
            <div class="widget-card-value">
                <span class="widget-card-percent">${bar.completion.toFixed(1)}%</span>
            </div>
            <div class="widget-card-progress">
                <div class="widget-card-progress-bar ${statusClass}" style="width: ${Math.min(bar.completion, 100)}%"></div>
            </div>
        `;

        // Обработчики событий
        card.addEventListener('click', () => {
            this.loadBarDetail(bar.bar);
        });

        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.loadBarDetail(bar.bar);
            }
        });

        return card;
    }

    /**
     * Рендер детального экрана
     */
    renderDetailView() {
        const container = this.elements.detailCards;
        if (!container || !this.selectedBar) return;

        container.innerHTML = '';

        const metrics = [
            { name: 'Выручка', value: formatMoney(this.selectedBar.current), neutral: true },
            { name: 'План', value: formatMoney(this.selectedBar.plan), neutral: true },
            { name: 'Ожидаемая', value: formatMoney(this.selectedBar.expected), neutral: true },
            { name: 'Средняя в день', value: formatMoney(this.selectedBar.average), neutral: true }
        ];

        metrics.forEach(metric => {
            const card = this.createDetailCard(metric);
            container.appendChild(card);
        });
    }

    /**
     * Создание карточки для детального экрана
     */
    createDetailCard(metric) {
        const card = document.createElement('div');
        card.className = 'widget-detail-card';

        card.innerHTML = `
            <span class="widget-detail-card-name">${metric.name}</span>
            <span class="widget-detail-card-value">${metric.value}</span>
        `;

        return card;
    }

    /**
     * Обновление диапазона дат
     */
    updateDateRange() {
        if (this.elements.dateRange) {
            this.elements.dateRange.textContent = formatDateRange();
        }
    }

    /**
     * Переключение на главный экран
     */
    showMainView() {
        this.elements.mainView?.classList.remove('hidden');
        this.elements.detailView?.classList.add('hidden');
        this.elements.error?.classList.add('hidden');
        this.elements.loading?.classList.add('hidden');
        this.currentView = 'main';
    }

    /**
     * Переключение на детальный экран
     */
    showDetailView() {
        this.elements.mainView?.classList.add('hidden');
        this.elements.detailView?.classList.remove('hidden');
        this.elements.error?.classList.add('hidden');
        this.elements.loading?.classList.add('hidden');
        this.currentView = 'detail';
    }

    /**
     * Показать loading state
     */
    showLoading() {
        this.elements.loading?.classList.remove('hidden');
        this.elements.error?.classList.add('hidden');
    }

    /**
     * Показать error state
     */
    showError() {
        this.elements.loading?.classList.add('hidden');
        this.elements.mainView?.classList.add('hidden');
        this.elements.detailView?.classList.add('hidden');
        this.elements.error?.classList.remove('hidden');
    }
}

// Инициализация при загрузке DOM
document.addEventListener('DOMContentLoaded', () => {
    const controller = new WidgetController();
    controller.init();
});

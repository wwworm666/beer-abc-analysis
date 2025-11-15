/**
 * MICROINTERACTIONS - Claude Design System
 * Плавные анимации и взаимодействия
 */

// ============================================
// COUNTUP ANIMATION ДЛЯ ЦИФР
// ============================================
function animateValue(element, start, end, duration = 800) {
    const startTime = performance.now();
    const isDecimal = end % 1 !== 0;

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Easing function (ease-out)
        const easeOut = 1 - Math.pow(1 - progress, 3);

        const current = start + (end - start) * easeOut;

        if (isDecimal) {
            element.textContent = current.toFixed(2);
        } else {
            element.textContent = Math.floor(current).toLocaleString('ru-RU');
        }

        if (progress < 1) {
            requestAnimationFrame(update);
        } else {
            // Финальное значение
            if (isDecimal) {
                element.textContent = end.toFixed(2);
            } else {
                element.textContent = end.toLocaleString('ru-RU');
            }
        }
    }

    requestAnimationFrame(update);
}

// Автоматическая инициализация CountUp при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    const metricValues = document.querySelectorAll('.metric-value, .metric-value-md, .metric-value-sm');

    metricValues.forEach(element => {
        const text = element.textContent.trim();
        // Убираем пробелы и знаки валюты для парсинга
        const cleanText = text.replace(/[^\d.,-]/g, '').replace(',', '.');
        const value = parseFloat(cleanText);

        if (!isNaN(value) && value > 0) {
            element.textContent = '0';
            // Задержка для stagger эффекта
            const delay = Math.random() * 100;
            setTimeout(() => {
                animateValue(element, 0, value);
            }, delay);
        }
    });
});

// ============================================
// ПЛАВНОЕ ПОЯВЛЕНИЕ ЭЛЕМЕНТОВ
// ============================================
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, index) => {
        if (entry.isIntersecting) {
            // Stagger delay для последовательного появления
            setTimeout(() => {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }, index * 50);

            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

document.addEventListener('DOMContentLoaded', function() {
    // Применяем к карточкам
    const cards = document.querySelectorAll('.card, .metric-card');
    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 400ms ease-out, transform 400ms ease-out';
        observer.observe(card);
    });
});

// ============================================
// АНИМАЦИЯ ГРАФИКОВ (CHART.JS)
// ============================================
function animateChart(chart) {
    if (!chart) return;

    // Настройка анимации для Chart.js
    chart.options.animation = {
        duration: 800,
        easing: 'easeOutQuart',
        delay: (context) => {
            let delay = 0;
            if (context.type === 'data' && context.mode === 'default') {
                delay = context.dataIndex * 50; // Stagger эффект
            }
            return delay;
        }
    };
}

// ============================================
// ОБНОВЛЕНИЕ ЗНАЧЕНИЙ С АНИМАЦИЕЙ
// ============================================
function updateMetricValue(element, newValue) {
    const oldValue = parseFloat(element.textContent.replace(/[^\d.,-]/g, '').replace(',', '.'));

    // Scale анимация
    element.style.transform = 'scale(1.05)';
    element.style.transition = 'transform 200ms ease-out';

    setTimeout(() => {
        animateValue(element, oldValue, newValue);
        element.style.transform = 'scale(1)';
    }, 100);
}

// ============================================
// TOAST NOTIFICATIONS
// ============================================
function showToast(message, type = 'success', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.textContent = message;
    toast.style.position = 'fixed';
    toast.style.top = '20px';
    toast.style.right = '20px';
    toast.style.zIndex = '9999';
    toast.style.minWidth = '300px';
    toast.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';

    document.body.appendChild(toast);

    // Auto dismiss
    setTimeout(() => {
        toast.style.animation = 'fadeOut 300ms ease-out';
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, duration);
}

// Fade out animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeOut {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;
document.head.appendChild(style);

// ============================================
// LOADING STATE
// ============================================
function showLoading(container) {
    const loader = document.createElement('div');
    loader.className = 'loading-spinner';
    loader.style.margin = '40px auto';

    if (typeof container === 'string') {
        container = document.querySelector(container);
    }

    if (container) {
        container.innerHTML = '';
        container.appendChild(loader);
    }
}

function hideLoading(container) {
    if (typeof container === 'string') {
        container = document.querySelector(container);
    }

    if (container) {
        const loader = container.querySelector('.loading-spinner');
        if (loader) {
            loader.remove();
        }
    }
}

// ============================================
// SKELETON SCREEN
// ============================================
function createSkeleton(type = 'card') {
    const skeleton = document.createElement('div');
    skeleton.className = 'skeleton';

    if (type === 'card') {
        skeleton.style.height = '200px';
        skeleton.style.borderRadius = '12px';
    } else if (type === 'text') {
        skeleton.style.height = '20px';
        skeleton.style.borderRadius = '4px';
    }

    return skeleton;
}

// ============================================
// HOVER TOOLTIPS
// ============================================
function initTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');

    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', function(e) {
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = this.getAttribute('data-tooltip');
            tooltip.style.cssText = `
                position: absolute;
                background: var(--text-primary);
                color: var(--bg-card);
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 13px;
                white-space: nowrap;
                z-index: 1000;
                pointer-events: none;
                opacity: 0;
                transition: opacity 150ms ease-in;
            `;

            document.body.appendChild(tooltip);

            const rect = this.getBoundingClientRect();
            tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
            tooltip.style.top = rect.bottom + 8 + 'px';

            setTimeout(() => tooltip.style.opacity = '1', 10);

            this.addEventListener('mouseleave', function() {
                tooltip.style.opacity = '0';
                setTimeout(() => tooltip.remove(), 150);
            }, { once: true });
        });
    });
}

document.addEventListener('DOMContentLoaded', initTooltips);

// ============================================
// BUTTON SUCCESS STATE
// ============================================
function buttonSuccess(button, message = '✓') {
    const originalText = button.textContent;
    const originalBg = button.style.background;

    button.textContent = message;
    button.style.background = 'var(--success)';
    button.disabled = true;

    setTimeout(() => {
        button.textContent = originalText;
        button.style.background = originalBg;
        button.disabled = false;
    }, 2000);
}

// ============================================
// SMOOTH SCROLL
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
});

// ============================================
// EXPORT FUNCTIONS
// ============================================
window.BeerPlatform = {
    animateValue,
    updateMetricValue,
    showToast,
    showLoading,
    hideLoading,
    createSkeleton,
    buttonSuccess,
    animateChart
};

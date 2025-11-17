/**
 * Утилиты - вспомогательные функции
 * Форматирование, даты, математика
 */

/**
 * Форматировать число как деньги (1234567 → 1 234 567 ₽)
 */
export function formatMoney(value) {
    if (value == null) return '0 ₽';
    return new Intl.NumberFormat('ru-RU', {
        style: 'decimal',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(value) + ' ₽';
}

/**
 * Форматировать число (1234 → 1 234)
 */
export function formatNumber(value) {
    if (value == null) return '0';
    return new Intl.NumberFormat('ru-RU', {
        style: 'decimal',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(value);
}

/**
 * Форматировать процент (12.5 → 12.5%)
 */
export function formatPercent(value) {
    if (value == null) return '0%';
    return value.toFixed(1) + '%';
}

/**
 * Форматировать значение согласно типу
 */
export function formatValue(value, format) {
    switch (format) {
        case 'money':
            return formatMoney(value);
        case 'number':
            return formatNumber(value);
        case 'percent':
            return formatPercent(value);
        default:
            return value;
    }
}

/**
 * Рассчитать процент выполнения плана
 */
export function calculatePercent(actual, plan) {
    if (!plan || plan === 0) return 0;
    return (actual / plan) * 100;
}

/**
 * Рассчитать разницу (факт - план)
 */
export function calculateDiff(actual, plan) {
    if (plan == null || actual == null) return 0;
    return actual - plan;
}

/**
 * Определить статус выполнения (success/warning/danger)
 */
export function getStatus(percent) {
    if (percent >= 100) return 'success';
    if (percent >= 90) return 'warning';
    return 'danger';
}

/**
 * Преобразовать дату из YYYY-MM-DD в DD.MM.YYYY
 */
export function formatDate(dateString) {
    if (!dateString) return '';
    const [year, month, day] = dateString.split('-');
    return `${day}.${month}.${year}`;
}

/**
 * Преобразовать дату из DD.MM.YYYY в YYYY-MM-DD
 */
export function parseDate(dateString) {
    if (!dateString) return '';
    const [day, month, year] = dateString.split('.');
    return `${year}-${month}-${day}`;
}

/**
 * Получить дату N дней назад
 */
export function getDaysAgo(days) {
    const date = new Date();
    date.setDate(date.getDate() - days);
    return date.toISOString().split('T')[0];
}

/**
 * Получить текущую дату в формате YYYY-MM-DD
 */
export function getToday() {
    return new Date().toISOString().split('T')[0];
}

/**
 * Проверить является ли дата сегодня
 */
export function isToday(dateString) {
    return dateString === getToday();
}

/**
 * Debounce функция (отложенный вызов)
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Throttle функция (ограничение частоты вызова)
 */
export function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Скопировать текст в буфер обмена
 */
export async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (error) {
        console.error('Ошибка копирования в буфер:', error);
        return false;
    }
}

/**
 * Скачать данные как файл
 */
export function downloadFile(content, filename, contentType = 'text/plain') {
    const blob = new Blob([content], { type: contentType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * Показать/скрыть элемент
 */
export function toggleElement(element, show) {
    if (show) {
        element.style.display = '';
        element.classList.remove('hidden');
    } else {
        element.style.display = 'none';
        element.classList.add('hidden');
    }
}

/**
 * Добавить класс loading к элементу
 */
export function setLoading(element, loading) {
    if (loading) {
        element.classList.add('loading');
        element.setAttribute('disabled', 'disabled');
    } else {
        element.classList.remove('loading');
        element.removeAttribute('disabled');
    }
}

/**
 * Валидация суммы долей (должна быть ~100%)
 */
export function validateShares(draftShare, packagedShare, kitchenShare) {
    const sum = draftShare + packagedShare + kitchenShare;
    return Math.abs(sum - 100) <= 1; // Допуск ±1%
}

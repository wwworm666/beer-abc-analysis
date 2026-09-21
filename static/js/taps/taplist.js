/**
 * Скачивание выгрузок таплиста со страниц кранов.
 *
 * Переход по ссылке (window.location) для этих кнопок не годится: выгрузка V2
 * ходит за живым прайсом в iiko и при сбое отвечает 503 с JSON — браузер увёл
 * бы сотрудника со страницы кранов на страницу с текстом ошибки. Поэтому
 * запрос идёт через fetch: кнопка блокируется на время ожидания (прайс — это
 * шесть обращений к iiko, ответ не мгновенный), ошибка показывается на месте,
 * а файл со старыми ценами не скачивается никогда.
 *
 * Подпись кнопки не трогаем: в разметке внутри неё бывают вложенные элементы.
 * Состояние показываем классом loading.
 */
async function downloadTaplistFile(button, url, filename) {
    if (button) {
        button.disabled = true;
        button.classList.add('loading');
    }
    try {
        const response = await fetch(url, { cache: 'no-store' });
        if (!response.ok) {
            let message = 'Не удалось получить таплист';
            try {
                const error = await response.json();
                message = error.error || message;
            } catch (parseError) {
                // Ответ не JSON (например, страница ошибки прокси) — показываем
                // общий текст, а не разметку, которая ничего не объяснит.
            }
            throw new Error(message);
        }
        const href = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = href;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(href), 1000);
    } catch (error) {
        alert(error.message || 'Не удалось получить таплист');
    } finally {
        if (button) {
            button.disabled = false;
            button.classList.remove('loading');
        }
    }
}

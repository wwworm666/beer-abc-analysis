/**
 * Модуль комментариев к периодам
 * Добавление и отображение комментариев
 */

import { state } from '../core/state.js';
import { api } from '../core/api.js';

class CommentsManager {
    constructor() {
        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        console.log('[Comments] Инициализация модуля комментариев...');

        this.setupEventListeners();

        // Подписываемся на изменения
        state.subscribe((event) => {
            if (event === 'periodChanged' || event === 'venueChanged') {
                this.loadComment();
            }
        });

        this.initialized = true;
        console.log('[Comments] ✅ Модуль комментариев инициализирован');
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Сохранение комментария
        document.getElementById('btn-save-comment')?.addEventListener('click', () => {
            this.handleSaveComment();
        });

        // Генерация AI анализа обрабатывается через comment_section.html inline скрипт
        // document.getElementById('btn-generate-ai-comment')?.addEventListener('click', () => {
        //     this.handleGenerateAIAnalysis();
        // });
    }

    /**
     * Загрузить комментарий для текущего периода
     */
    async loadComment() {
        const venueKey = state.currentVenue;
        const periodKey = state.currentPeriod?.key;  // ИСПРАВЛЕНО: было state.currentPeriod (объект)

        if (!venueKey || !periodKey) {
            this.clearComment();
            return;
        }

        try {
            console.log(`[Comments] Загрузка комментария: ${venueKey} / ${periodKey}`);

            const data = await api.getComment(venueKey, periodKey);

            if (data && data.comment) {
                this.displayComment(data.comment);
            } else {
                this.clearComment();
            }

        } catch (error) {
            console.error('[Comments] Ошибка загрузки комментария:', error);
            this.clearComment();
        }
    }

    /**
     * Отобразить комментарий
     */
    displayComment(comment) {
        const commentText = document.getElementById('comment-text');
        const commentDisplay = document.getElementById('comment-display');
        const commentForm = document.getElementById('comment-edit-form');
        const textarea = document.getElementById('period-comment');

        if (commentText && commentDisplay) {
            commentText.textContent = comment;
            commentDisplay.classList.remove('hidden');
            commentForm?.classList.add('hidden');

            // Также заполняем textarea на случай редактирования
            if (textarea) {
                textarea.value = comment;
            }
        }
    }

    /**
     * Очистить комментарий
     */
    clearComment() {
        const commentText = document.getElementById('comment-text');
        const commentDisplay = document.getElementById('comment-display');
        const commentForm = document.getElementById('comment-edit-form');
        const textarea = document.getElementById('period-comment');

        if (commentText) {
            commentText.textContent = '';
        }

        commentDisplay?.classList.add('hidden');
        commentForm?.classList.add('hidden');

        if (textarea) {
            textarea.value = '';
        }
    }

    /**
     * Обработать сохранение комментария
     */
    async handleSaveComment() {
        const venueKey = state.currentVenue;
        const periodKey = state.currentPeriod;

        if (!venueKey || !periodKey) {
            state.addMessage('warning', 'Выберите заведение и период', 3000);
            return;
        }

        const textarea = document.getElementById('period-comment');
        const comment = textarea?.value.trim() || '';

        if (!comment) {
            state.addMessage('warning', 'Введите комментарий', 3000);
            return;
        }

        try {
            console.log(`[Comments] Сохранение комментария: ${comment.length} символов`);

            const result = await api.saveComment(venueKey, periodKey, comment);

            if (result.success) {
                state.addMessage('success', 'Комментарий сохранен', 3000);
                this.displayComment(comment);
            } else {
                state.addMessage('error', 'Ошибка сохранения комментария', 5000);
            }

        } catch (error) {
            console.error('[Comments] Ошибка сохранения комментария:', error);
            state.addMessage('error', 'Не удалось сохранить комментарий', 5000);
        }
    }

    /**
     * Обновить комментарий
     */
    refresh() {
        this.loadComment();
    }

    /**
     * Сгенерировать AI анализ для периода
     */
    async handleGenerateAIAnalysis() {
        const venueKey = state.currentVenue;
        const periodKey = state.currentPeriod?.key;

        if (!venueKey || !periodKey) {
            state.addMessage('warning', 'Выберите заведение и период', 3000);
            return;
        }

        const btn = document.getElementById('btn-generate-ai-comment');
        const commentForm = document.getElementById('comment-edit-form');
        const commentDisplay = document.getElementById('comment-display');
        const textarea = document.getElementById('period-comment');

        // Показываем форму редактирования
        commentDisplay?.classList.add('hidden');
        commentForm?.classList.remove('hidden');

        // Деактивируем кнопку и показываем прогресс
        const originalText = btn?.textContent || '🤖 AI анализ';
        if (btn) {
            btn.disabled = true;
            btn.textContent = '⏳ Анализирую...';
        }

        try {
            console.log(`[AI] Запрос анализа для ${venueKey} / ${periodKey}`);

            const response = await fetch(`/api/analyze-period/${venueKey}/${periodKey}`);

            if (!response.ok) {
                throw new Error(`Ошибка сервера: ${response.status}`);
            }

            const data = await response.json();

            if (data.analysis) {
                console.log('[AI] Анализ получен, заполняю textarea');
                if (textarea) {
                    textarea.value = data.analysis;
                }
                state.addMessage('success', 'AI анализ сгенерирован', 3000);
            } else if (data.error) {
                throw new Error(data.error);
            }

        } catch (error) {
            console.error('[AI ERROR]', error);
            state.addMessage('error', `Ошибка генерации анализа: ${error.message}`, 5000);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    }
}

// Экспортируем единственный экземпляр
export const commentsManager = new CommentsManager();

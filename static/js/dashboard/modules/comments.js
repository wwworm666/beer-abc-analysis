/**
 * Модуль комментариев к периодам
 * Добавление и отображение комментариев
 */

import { state } from '../core/state.js';
import { getComment, saveComment } from '../core/api.js';

class CommentsManager {
    constructor() {
        this.commentSection = document.getElementById('comment-section');
        this.commentTextarea = document.getElementById('period-comment');
        this.btnSaveComment = document.getElementById('btn-save-comment');
        this.commentDisplay = document.getElementById('comment-display');

        this.initialized = false;
    }

    /**
     * Инициализация модуля
     */
    init() {
        if (this.initialized) return;

        this.setupEventListeners();
        this.initialized = true;
    }

    /**
     * Настроить обработчики событий
     */
    setupEventListeners() {
        // Сохранение комментария
        this.btnSaveComment?.addEventListener('click', () => {
            this.handleSaveComment();
        });

        // Подписка на изменения состояния
        state.subscribe((event, data) => {
            if (event === 'venueChanged' || event === 'periodChanged') {
                this.loadComment();
            }
        });
    }

    /**
     * Загрузить комментарий для текущего периода
     */
    async loadComment() {
        if (!state.currentVenue || !state.currentPeriod) {
            return;
        }

        try {
            const data = await getComment(state.currentVenue, state.currentPeriod.key);

            if (data && data.comment) {
                this.displayComment(data.comment);
                if (this.commentTextarea) {
                    this.commentTextarea.value = data.comment;
                }
            } else {
                this.clearComment();
            }

        } catch (error) {
            console.error('Ошибка загрузки комментария:', error);
        }
    }

    /**
     * Отобразить комментарий
     */
    displayComment(comment) {
        if (this.commentDisplay) {
            this.commentDisplay.textContent = comment;
            this.commentDisplay.classList.remove('hidden');
        }
    }

    /**
     * Очистить комментарий
     */
    clearComment() {
        if (this.commentTextarea) {
            this.commentTextarea.value = '';
        }
        if (this.commentDisplay) {
            this.commentDisplay.textContent = '';
            this.commentDisplay.classList.add('hidden');
        }
    }

    /**
     * Обработать сохранение комментария
     */
    async handleSaveComment() {
        if (!state.currentVenue || !state.currentPeriod) {
            state.addMessage('warning', 'Выберите заведение и период', 3000);
            return;
        }

        const comment = this.commentTextarea?.value.trim();

        if (!comment) {
            state.addMessage('warning', 'Введите комментарий', 3000);
            return;
        }

        try {
            const result = await saveComment(
                state.currentVenue,
                state.currentPeriod.key,
                comment
            );

            if (result.success) {
                state.addMessage('success', 'Комментарий сохранен', 3000);
                this.displayComment(comment);
            } else {
                state.addMessage('error', 'Ошибка сохранения комментария', 5000);
            }

        } catch (error) {
            console.error('Ошибка сохранения комментария:', error);
            state.addMessage('error', 'Не удалось сохранить комментарий', 5000);
        }
    }

    /**
     * Обновить комментарий
     */
    refresh() {
        this.loadComment();
    }
}

// Экспортируем единственный экземпляр
export const commentsManager = new CommentsManager();

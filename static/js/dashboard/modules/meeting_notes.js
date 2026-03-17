/**
 * Meeting Notes — заметки к собранию.
 * Привязаны к бару + периоду, автосохранение с debounce.
 * История предыдущих заметок по бару.
 */

import { state } from '../core/state.js';

class MeetingNotes {
    constructor() {
        this.textarea = null;
        this.container = null;
        this.statusEl = null;
        this.historyEl = null;
        this.historyToggle = null;
        this.historyToggleText = null;
        this.saveTimeout = null;
        this.currentKey = null;
        this.historyOpen = false;
        this.saving = false;
    }

    init() {
        this.textarea = document.getElementById('meeting-notes-text');
        this.container = document.getElementById('meeting-notes');
        this.statusEl = document.getElementById('notes-status');
        this.historyEl = document.getElementById('notes-history');
        this.historyToggle = document.getElementById('notes-history-toggle');
        this.historyToggleText = document.getElementById('notes-history-toggle-text');
        if (!this.textarea || !this.container) return;

        // Autosave on input (debounce 1s)
        this.textarea.addEventListener('input', () => {
            this.setStatus('saving');
            clearTimeout(this.saveTimeout);
            this.saveTimeout = setTimeout(() => this.save(), 1000);
        });

        // History toggle
        if (this.historyToggle) {
            this.historyToggle.addEventListener('click', () => this.toggleHistory());
        }

        // Subscribe to state changes (venue/period)
        state.subscribe((event) => {
            if (event === 'venueChanged' || event === 'periodChanged') {
                this.load();
                this.closeHistory();
            }
        });
    }

    getKey() {
        const venue = state.currentVenue;
        const period = state.currentPeriod;
        if (!venue || !period || !period.start || !period.end) return null;
        return { venue, date_from: period.start, date_to: period.end };
    }

    async load() {
        const key = this.getKey();
        if (!key) {
            this.container.classList.add('hidden');
            return;
        }

        const keyStr = `${key.venue}::${key.date_from}::${key.date_to}`;
        if (keyStr === this.currentKey) return;
        this.currentKey = keyStr;

        this.container.classList.remove('hidden');
        this.textarea.value = '';
        this.setStatus('');

        try {
            const params = new URLSearchParams(key);
            const resp = await fetch(`/api/meeting-notes?${params}`);
            const data = await resp.json();
            if (keyStr === this.currentKey) {
                this.textarea.value = data.text || '';
            }
        } catch (e) {
            console.error('Ошибка загрузки заметок:', e);
        }
    }

    async save() {
        const key = this.getKey();
        if (!key) return;

        this.saving = true;
        try {
            await fetch('/api/meeting-notes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...key, text: this.textarea.value })
            });
            this.setStatus('saved');
        } catch (e) {
            console.error('Ошибка сохранения заметок:', e);
            this.setStatus('error');
        }
        this.saving = false;
    }

    // --- History ---

    toggleHistory() {
        this.historyOpen ? this.closeHistory() : this.openHistory();
    }

    closeHistory() {
        this.historyOpen = false;
        if (this.historyEl) this.historyEl.classList.add('hidden');
        if (this.historyToggle) this.historyToggle.classList.remove('open');
        if (this.historyToggleText) this.historyToggleText.textContent = 'Показать предыдущие';
    }

    async openHistory() {
        const venue = state.currentVenue;
        if (!venue || !this.historyEl) return;

        this.historyOpen = true;
        this.historyToggle.classList.add('open');
        this.historyToggleText.textContent = 'Скрыть';
        this.historyEl.classList.remove('hidden');
        this.historyEl.innerHTML = '<div class="notes-history-loading">Загрузка...</div>';

        try {
            const resp = await fetch(`/api/meeting-notes/history?venue=${encodeURIComponent(venue)}&limit=10`);
            const notes = await resp.json();

            // Exclude the current period's note
            const key = this.getKey();
            const filtered = notes.filter(n =>
                !(n.date_from === key?.date_from && n.date_to === key?.date_to)
            );

            if (!filtered.length) {
                this.historyEl.innerHTML = '<div class="notes-history-empty">Нет предыдущих заметок</div>';
                return;
            }

            this.historyEl.innerHTML = filtered.map(note => {
                const period = this.formatPeriod(note.date_from, note.date_to);
                const preview = (note.text || '').slice(0, 120);
                const hasMore = (note.text || '').length > 120;
                return `
                    <div class="notes-history-item" data-full="${this.escapeAttr(note.text)}">
                        <div class="notes-history-item-header">
                            <span class="notes-history-period">${period}</span>
                        </div>
                        <div class="notes-history-item-text">${this.escapeHtml(preview)}${hasMore ? '...' : ''}</div>
                        ${hasMore ? '<div class="notes-history-item-full hidden">' + this.escapeHtml(note.text) + '</div>' : ''}
                    </div>
                `;
            }).join('');

            // Click to expand/collapse
            this.historyEl.querySelectorAll('.notes-history-item').forEach(item => {
                const full = item.querySelector('.notes-history-item-full');
                const preview = item.querySelector('.notes-history-item-text');
                if (!full) return;
                item.style.cursor = 'pointer';
                item.addEventListener('click', () => {
                    const isExpanded = !full.classList.contains('hidden');
                    full.classList.toggle('hidden');
                    preview.classList.toggle('hidden');
                    item.classList.toggle('expanded');
                });
            });
        } catch (e) {
            console.error('Ошибка загрузки истории:', e);
            this.historyEl.innerHTML = '<div class="notes-history-empty">Ошибка загрузки</div>';
        }
    }

    formatPeriod(from, to) {
        const f = this.formatDate(from);
        const t = this.formatDate(to);
        return `${f} — ${t}`;
    }

    formatDate(dateStr) {
        if (!dateStr) return '';
        const [y, m, d] = dateStr.split('-');
        return `${d}.${m}`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML.replace(/\n/g, '<br>');
    }

    escapeAttr(text) {
        return (text || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    // --- Status ---

    setStatus(status) {
        if (!this.statusEl) return;
        if (status === 'saving') {
            this.statusEl.textContent = 'Сохранение...';
            this.statusEl.className = 'meeting-notes-status saving';
        } else if (status === 'saved') {
            this.statusEl.textContent = 'Сохранено';
            this.statusEl.className = 'meeting-notes-status saved';
            setTimeout(() => {
                if (this.statusEl.textContent === 'Сохранено') {
                    this.statusEl.textContent = '';
                    this.statusEl.className = 'meeting-notes-status';
                }
            }, 3000);
        } else if (status === 'error') {
            this.statusEl.textContent = 'Ошибка сохранения';
            this.statusEl.className = 'meeting-notes-status error';
        } else {
            this.statusEl.textContent = '';
            this.statusEl.className = 'meeting-notes-status';
        }
    }
}

export const meetingNotes = new MeetingNotes();

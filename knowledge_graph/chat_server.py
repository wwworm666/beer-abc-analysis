"""
Standalone GraphRAG Chat Server.
Run: python -m knowledge_graph.chat_server
"""

from flask import Flask, render_template_string, send_from_directory
import os
import pathlib

from knowledge_graph.api.routes import chat_bp

# Calculate static folder path
STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / 'static'

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path='/static')
app.register_blueprint(chat_bp)

# Minimalist Search UI - белый фон, одна строка поиска
CHAT_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Поиск</title>
    <style>
        @font-face {
            font-family: 'IBM Plex Mono';
            src: url('/static/fonts/IBMPlexMono-Regular.ttf') format('truetype');
            font-weight: 400;
        }
        @font-face {
            font-family: 'IBM Plex Mono';
            src: url('/static/fonts/IBMPlexMono-Medium.ttf') format('truetype');
            font-weight: 500;
        }
        @font-face {
            font-family: 'IBM Plex Mono';
            src: url('/static/fonts/IBMPlexMono-Bold.ttf') format('truetype');
            font-weight: 700;
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'IBM Plex Mono', monospace;
            background: #fff;
            min-height: 100vh;
            color: #333;
        }
        .search-page {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
            transition: justify-content 0.3s;
        }
        .search-page.has-result {
            justify-content: flex-start;
            padding-top: 60px;
        }
        .logo {
            margin-bottom: 40px;
        }
        .logo img {
            width: 80px;
            height: 80px;
        }
        .search-box {
            width: 100%;
            max-width: 600px;
            position: relative;
        }
        #search-input {
            width: 100%;
            padding: 16px 50px 16px 20px;
            font-size: 1rem;
            border: 1px solid #ddd;
            border-radius: 24px;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        #search-input:focus {
            border-color: #333;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        #search-input::placeholder {
            color: #999;
        }
        .search-btn {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            width: 36px;
            height: 36px;
            border: none;
            background: #333;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }
        .search-btn:hover {
            background: #555;
        }
        .search-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .search-btn svg {
            width: 16px;
            height: 16px;
            fill: #fff;
        }
        .hints {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 20px;
            justify-content: center;
        }
        .hint {
            padding: 8px 16px;
            font-size: 0.85rem;
            color: #666;
            background: #f5f5f5;
            border: none;
            border-radius: 16px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .hint:hover {
            background: #eee;
        }
        .result-container {
            width: 100%;
            max-width: 700px;
            margin-top: 40px;
            display: none;
        }
        .result-container.visible {
            display: block;
        }
        .loading {
            text-align: center;
            padding: 40px;
            color: #999;
            display: none;
        }
        .loading.active {
            display: block;
        }
        .spinner {
            width: 24px;
            height: 24px;
            border: 2px solid #eee;
            border-top-color: #333;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .answer {
            padding: 24px;
            background: #fafafa;
            border-radius: 12px;
            line-height: 1.7;
            font-size: 1rem;
        }
        .answer p {
            margin-bottom: 12px;
        }
        .answer p:last-child {
            margin-bottom: 0;
        }
        .cypher-block {
            margin-top: 16px;
            padding: 12px 16px;
            background: #2d2d2d;
            border-radius: 8px;
            overflow-x: auto;
        }
        .cypher-block code {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.8rem;
            color: #7dd3fc;
            white-space: pre-wrap;
        }
        .error {
            color: #e53935;
        }
        .query-label {
            font-size: 0.75rem;
            color: #999;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
    </style>
</head>
<body>
    <div class="search-page" id="search-page">
        <div class="logo"><img src="/static/logo.jpg" alt="Культура"></div>

        <div class="search-box">
            <input type="text" id="search-input"
                   onkeypress="handleKeyPress(event)" autofocus>
            <button class="search-btn" id="search-btn" onclick="search()">
                <svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </button>
        </div>

        <div class="hints" id="hints">
            <button class="hint" onclick="askHint(this)">Топ-5 пива по выручке</button>
            <button class="hint" onclick="askHint(this)">Какой бар продает больше?</button>
            <button class="hint" onclick="askHint(this)">Лучший официант</button>
        </div>

        <div class="result-container" id="result-container">
            <div class="loading" id="loading">
                <div class="spinner"></div>
            </div>
            <div class="answer" id="answer"></div>
        </div>
    </div>

    <script>
        const searchPage = document.getElementById('search-page');
        const searchInput = document.getElementById('search-input');
        const searchBtn = document.getElementById('search-btn');
        const hints = document.getElementById('hints');
        const resultContainer = document.getElementById('result-container');
        const loading = document.getElementById('loading');
        const answerDiv = document.getElementById('answer');

        async function search() {
            const question = searchInput.value.trim();
            if (!question) return;

            // Переключаем в режим результата
            searchPage.classList.add('has-result');
            hints.style.display = 'none';
            resultContainer.classList.add('visible');
            loading.classList.add('active');
            answerDiv.style.display = 'none';
            searchBtn.disabled = true;

            try {
                const response = await fetch('/api/chat/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question })
                });

                const data = await response.json();

                if (data.success) {
                    let html = data.answer.replace(/\\n/g, '<br>');

                    if (data.cypher) {
                        html += `
                            <div class="cypher-block">
                                <div class="query-label">Cypher запрос</div>
                                <code>${data.cypher}</code>
                            </div>
                        `;
                    }

                    answerDiv.innerHTML = html;
                } else {
                    answerDiv.innerHTML = `<span class="error">${data.error}</span>`;
                }
            } catch (error) {
                answerDiv.innerHTML = `<span class="error">Ошибка: ${error.message}</span>`;
            }

            loading.classList.remove('active');
            answerDiv.style.display = 'block';
            searchBtn.disabled = false;
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                search();
            }
        }

        function askHint(btn) {
            searchInput.value = btn.textContent;
            search();
        }
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """Chat UI page."""
    return render_template_string(CHAT_HTML)


if __name__ == '__main__':
    print("=" * 50)
    print("GraphRAG Chat Server")
    print("=" * 50)
    print("Open: http://localhost:5001")
    print("API:  http://localhost:5001/api/chat/ask")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5001, debug=True)

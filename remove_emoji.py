"""Убрать все emoji из Python файлов"""
import re
import os

# Файлы для обработки
files = [
    'data_processor.py',
    'abc_analysis.py',
    'xyz_analysis.py',
    'category_analysis.py',
]

# Маппинг emoji на текст
emoji_replacements = {
    '🔑': '[AUTH]',
    '✅': '[OK]',
    '❌': '[ERROR]',
    '📊': '[STATS]',
    '🔄': '[PROCESS]',
    '👋': '[INFO]',
    '🍺': '[BEER]',
    '🎉': '[SUCCESS]',
    '⚠️': '[WARN]',
    '💡': '[TIP]',
    '📄': '[FILE]',
    '📈': '[CHART]',
    '🧪': '[TEST]',
    '🏪': '[BAR]',
    '💰': '[MONEY]',
    '🧐': '[CHECK]',
}

def remove_emoji_from_file(filepath):
    """Убрать emoji из файла"""
    if not os.path.exists(filepath):
        print(f"[SKIP] File not found: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Заменяем known emoji
    for emoji, replacement in emoji_replacements.items():
        content = content.replace(emoji, replacement)

    # Убираем все оставшиеся emoji через regex
    # Emoji обычно в диапазоне U+1F300–U+1F9FF
    content = re.sub(r'[\U0001F300-\U0001F9FF]+', '[EMOJI]', content)

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] Processed: {filepath}")
    else:
        print(f"[SKIP] No changes: {filepath}")

if __name__ == '__main__':
    print("Removing emoji from Python files...\n")
    for file in files:
        remove_emoji_from_file(file)
    print("\n[DONE] All files processed!")

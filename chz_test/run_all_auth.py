# -*- coding: utf-8 -*-
"""
Master-скрипт: запускает ВСЕ варианты аутентификации по очереди.

Варианты:
  1. csptest -sfsign -sign (базовый, уже пробовали — но на всякий случай)
  2. csptest -sfsign -sign -detached -cades_strict
  3. csptest -sfsign -sign -detached -cades_strict -add
  4. csptest -sfsign -sign -detached -cades_strict -add -addsigtime
  5. CryptCP.exe -sign -detached -thumb
  6. PowerShell SignedCms (.NET CMS)

Первый успешно получивший токен — прерывает цикл.

Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА
"""

import subprocess, os, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = [
    ("Вариант 1: csptest + cades_strict + add (ГЛАВНАЯ НАДЕЖДА)",
     "csptest_cades_auth.py"),

    ("Вариант 2: CryptCP.exe",
     "cryptcp_sign_auth.py"),

    ("Вариант 3: PowerShell / certutil",
     "powershell_sign_auth.py"),
]


def main():
    print("=" * 70)
    print("  ЧЗ API — Все варианты аутентификации")
    print("=" * 70)
    print(f"\nВсего скриптов: {len(SCRIPTS)}")
    print(f"Запускать их нужно ОТ ИМЕНИ АДМИНИСТРАТОРА!")
    print(f"Все скрипты остановятся при первом успешном получении токена.\n")

    for i, (label, filename) in enumerate(SCRIPTS, 1):
        filepath = os.path.join(SCRIPT_DIR, filename)
        if not os.path.exists(filepath):
            print(f"\n⚠️ Скрипт не найден: {filepath}")
            continue

        print(f"\n{'#' * 70}")
        print(f"  [{i}/{len(SCRIPTS)}] {label}")
        print(f"  Файл: {filename}")
        print(f"{'#' * 70}")

        input(f"\n→ Нажми Enter для запуска...")

        result = subprocess.run(
            f'python "{filepath}"',
            shell=True,
            encoding='cp866',
            timeout=600  # 10 минут максимум на скрипт
        )

        # Проверить появился ли токен
        debug_dir = os.path.join(SCRIPT_DIR, "debug")
        token_file = os.path.join(debug_dir, "token.json")
        if os.path.exists(token_file):
            print(f"\n🎉 ТОКЕН ПОЛУЧЕН!")
            import json
            with open(token_file) as f:
                token_data = json.load(f)
            print(f"  {json.dumps(token_data, indent=2, ensure_ascii=False)}")
            return

        print(f"\n  ❌ Вариант {i} не дал токен.")

    print(f"\n{'=' * 70}")
    print(f"  ❌ ВСЕ варианты аутентификации не прошли")
    print(f"{'=' * 70}")
    print(f"\nРекомендации:")
    print(f"  1. Запустить diagnose_signature.py — изучить структуру PKCS#7")
    print(f"  2. Отправить error_*.json файлы в support@crpt.ru")
    print(f"  3. Попробовать песочницу: markirovka.sandbox.crptech.ru")
    input("\nНажми Enter для выхода...")


if __name__ == "__main__":
    main()

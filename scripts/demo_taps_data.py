#!/usr/bin/env python3
"""
Скрипт для заполнения системы управления кранами демо-данными
Создает реалистичные данные о состоянии кранов для всех 4 баров
"""

from core.taps_manager import TapsManager
from datetime import datetime, timedelta
import random

def generate_demo_data():
    """Генерирует демо-данные для системы"""

    # Список популярных сортов пива
    beers = [
        "Гиннесс", "Heineken", "Stella Artois", "Corona",
        "Budweiser", "Киликия", "Балтика", "Невское",
        "Оболонь", "Закуска", "Перамога", "Hoegaarden",
        "Krombacher", "Carlsberg", "Tuborg", "Miller"
    ]

    # Инициализируем менеджер
    manager = TapsManager()

    # Словарь с конфигурацией действий для каждого бара
    bars_config = [
        {'bar_id': 'bar1', 'name': 'Большой пр. В.О', 'actions': 8},
        {'bar_id': 'bar2', 'name': 'Лиговский', 'actions': 6},
        {'bar_id': 'bar3', 'name': 'Кременчугская', 'actions': 7},
        {'bar_id': 'bar4', 'name': 'Варшавская', 'actions': 12},
    ]

    print("\n" + "="*60)
    print("ГЕНЕРИРОВАНИЕ ДЕМО-ДАННЫХ ДЛЯ СИСТЕМЫ УПРАВЛЕНИЯ КРАНАМИ")
    print("="*60 + "\n")

    # Для каждого бара создаем события
    for bar_config in bars_config:
        bar_id = bar_config['bar_id']
        bar_name = bar_config['name']
        action_count = bar_config['actions']

        print(f"📍 {bar_name} ({bar_id})")
        print(f"   Количество действий: {action_count}")

        # Генерируем случайные действия
        for _ in range(action_count):
            tap_number = random.randint(1, manager.bars[bar_id].tap_count)
            beer = random.choice(beers)
            keg_id = f"KEG-{random.randint(1000, 9999)}"

            # Выбираем случайное действие
            action = random.choice(['start', 'replace'])

            if action == 'start':
                result = manager.start_tap(bar_id, tap_number, beer, keg_id)
                status = "✅" if result['success'] else "❌"
                print(f"   {status} START - Кран #{tap_number}: {beer}")

            elif action == 'replace':
                # Для replace нужно чтобы кран был активен
                result = manager.replace_tap(bar_id, tap_number, beer, keg_id)
                status = "✅" if result['success'] else "❌"
                print(f"   {status} REPLACE - Кран #{tap_number}: {beer}")

        print()

    # Выполняем несколько stop операций
    print("🛑 Завершение работы некоторых кранов...")
    for bar_id in ['bar1', 'bar2', 'bar3', 'bar4']:
        # Случайно выбираем краны для остановки
        stop_count = random.randint(1, 3)
        for _ in range(stop_count):
            tap_number = random.randint(1, manager.bars[bar_id].tap_count)
            result = manager.stop_tap(bar_id, tap_number)
            bar_name = manager.bars[bar_id].name
            status = "✅" if result['success'] else "❌"
            if result['success']:
                print(f"   {status} STOP - {bar_name}, Кран #{tap_number}")

    print("\n" + "="*60)
    print("СТАТИСТИКА")
    print("="*60 + "\n")

    # Выводим статистику
    stats = manager.get_statistics()

    print(f"📊 Общая статистика:")
    print(f"   Всего баров: {stats['total_bars']}")
    print(f"   Всего кранов: {stats['total_taps']}")
    print(f"   Активных кранов: {stats['active_taps']}")
    print(f"   Пустых кранов: {stats['empty_taps']}")
    print(f"   Процент активности: {stats['active_percentage']}%")
    print(f"   Всего событий: {stats['total_events']}")

    print("\n📈 По барам:\n")

    # Статистика по каждому бару
    for bar_id in ['bar1', 'bar2', 'bar3', 'bar4']:
        bar_stats = manager.get_statistics(bar_id)
        bar_name = bar_stats['bar_name']

        print(f"   {bar_name}:")
        print(f"      Активных: {bar_stats['active_taps']}/{bar_stats['total_taps']} "
              f"({bar_stats['active_percentage']}%)")
        print(f"      Пустых: {bar_stats['empty_taps']}")
        print(f"      Событий: {bar_stats['total_events']}")
        print()

    # Выводим последние события
    print("="*60)
    print("ПОСЛЕДНИЕ 10 СОБЫТИЙ")
    print("="*60 + "\n")

    events = manager.get_all_events(limit=10)
    for i, event in enumerate(events, 1):
        action_emoji = {
            'start': '▶',
            'stop': '⏹',
            'replace': '🔄'
        }.get(event['action'], '•')

        print(f"{i:2}. {action_emoji} {event['action'].upper():7} "
              f"| {event['bar_name']:20} Кран #{event['tap_number']:2} "
              f"| {event['beer_name']:20}")

    print("\n" + "="*60)
    print("✅ ДЕМО-ДАННЫЕ УСПЕШНО СОЗДАНЫ!")
    print("="*60)
    print("\nТеперь откройте http://localhost:5000/taps в браузере")
    print("и увидите все генерированные данные на интерфейсе.\n")

if __name__ == '__main__':
    generate_demo_data()

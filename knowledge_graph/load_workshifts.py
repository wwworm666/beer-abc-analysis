"""
Load employee work shifts (явки) into Neo4j Knowledge Graph.

Creates WorkShift nodes with properties:
- shift_id: UUID явки
- date: дата смены (YYYY-MM-DD)
- start_time: время начала (HH:MM)
- end_time: время окончания (HH:MM)
- duration_minutes: продолжительность в минутах

Creates relationships:
- (Waiter)-[:WORKED_SHIFT]->(WorkShift)
- (WorkShift)-[:AT_BAR]->(Bar)
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.iiko_api import IikoAPI
from knowledge_graph.db import Neo4jConnection


def load_workshifts(date_from: str, date_to: str):
    """
    Загрузить явки из iiko API в Neo4j.

    Args:
        date_from: Дата начала (YYYY-MM-DD)
        date_to: Дата окончания (YYYY-MM-DD)
    """
    print("=" * 50)
    print("ЗАГРУЗКА ЯВОК В KNOWLEDGE GRAPH")
    print("=" * 50)

    # 1. Получаем данные из iiko API
    api = IikoAPI()

    if not api.authenticate():
        print("[ERROR] Не удалось авторизоваться в iiko")
        return

    try:
        # Получаем явки
        attendances = api.get_attendance(date_from, date_to)

        if not attendances:
            print("[INFO] Нет явок за указанный период")
            return

        # Получаем сотрудников для маппинга ID -> Name
        employees = api.get_employees()
        employee_map = {emp['id']: emp['name'] for emp in employees}

    finally:
        api.logout()

    # 2. Фильтруем только завершённые смены
    completed_shifts = [
        att for att in attendances
        if att.get('end_time') is not None and att.get('duration_minutes') is not None
    ]

    print(f"\n[INFO] Всего явок: {len(attendances)}")
    print(f"[INFO] Завершённых смен: {len(completed_shifts)}")

    if not completed_shifts:
        print("[INFO] Нет завершённых смен для загрузки")
        return

    # 3. Загружаем в Neo4j
    print("\n[NEO4J] Подключаюсь к базе данных...")

    with Neo4jConnection() as db:
        # Создаём индекс для WorkShift если ещё нет
        db.execute("""
            CREATE INDEX workshift_id IF NOT EXISTS
            FOR (w:WorkShift) ON (w.shift_id)
        """)

        # Подготавливаем данные для batch insert
        shifts_data = []
        for att in completed_shifts:
            employee_name = employee_map.get(att['employee_id'], 'Unknown')

            shifts_data.append({
                'shift_id': att['id'],
                'date': att['date'],
                'start_time': att['start_time'],
                'end_time': att['end_time'],
                'duration_minutes': att['duration_minutes'],
                'employee_id': att['employee_id'],
                'employee_name': employee_name,
                'department_name': att.get('department_name', '')
            })

        # Создаём WorkShift узлы и связи
        query = """
        UNWIND $batch AS shift

        // Создаём или находим WorkShift
        MERGE (ws:WorkShift {shift_id: shift.shift_id})
        SET ws.date = shift.date,
            ws.start_time = shift.start_time,
            ws.end_time = shift.end_time,
            ws.duration_minutes = shift.duration_minutes

        // Связываем с Waiter (создаём если нет)
        MERGE (w:Waiter {name: shift.employee_name})
        MERGE (w)-[:WORKED_SHIFT]->(ws)

        // Связываем с Bar если есть название подразделения
        WITH ws, shift
        WHERE shift.department_name IS NOT NULL AND shift.department_name <> ''
        MERGE (b:Bar {name: shift.department_name})
        MERGE (ws)-[:AT_BAR]->(b)

        RETURN count(ws) as count
        """

        result = db.execute_batch(query, shifts_data, batch_size=500)

        print(f"\n[OK] Загружено {result} смен в граф")

        # Показываем статистику
        stats = db.execute("""
            MATCH (ws:WorkShift)
            RETURN count(ws) as total_shifts,
                   count(DISTINCT ws.date) as unique_dates
        """)

        if stats:
            print(f"[STATS] Всего смен в графе: {stats[0]['total_shifts']}")
            print(f"[STATS] Уникальных дат: {stats[0]['unique_dates']}")


def show_sample_shifts():
    """Показать примеры загруженных смен."""
    print("\n" + "=" * 50)
    print("ПРИМЕРЫ ЗАГРУЖЕННЫХ СМЕН")
    print("=" * 50)

    with Neo4jConnection() as db:
        results = db.execute("""
            MATCH (w:Waiter)-[:WORKED_SHIFT]->(ws:WorkShift)
            OPTIONAL MATCH (ws)-[:AT_BAR]->(b:Bar)
            RETURN w.name as waiter,
                   ws.date as date,
                   ws.start_time as start,
                   ws.end_time as end,
                   ws.duration_minutes as minutes,
                   b.name as bar
            ORDER BY ws.date DESC, ws.start_time DESC
            LIMIT 10
        """)

        if results:
            print(f"\n{'Сотрудник':<20} {'Дата':<12} {'Начало':<8} {'Конец':<8} {'Минут':<8} {'Бар'}")
            print("-" * 80)
            for r in results:
                print(f"{r['waiter']:<20} {r['date']:<12} {r['start']:<8} {r['end']:<8} {r['minutes']:<8} {r.get('bar', '-')}")
        else:
            print("[INFO] Нет загруженных смен")


if __name__ == "__main__":
    # По умолчанию загружаем за последний месяц
    today = datetime.now()
    date_to = today.strftime('%Y-%m-%d')
    date_from = (today - timedelta(days=30)).strftime('%Y-%m-%d')

    # Можно передать даты через аргументы
    if len(sys.argv) >= 3:
        date_from = sys.argv[1]
        date_to = sys.argv[2]

    load_workshifts(date_from, date_to)
    show_sample_shifts()

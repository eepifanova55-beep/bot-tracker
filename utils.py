"""
Вспомогательные функции для форматирования и расчета данных.
"""
from datetime import datetime, timedelta
from typing import List, Dict


def create_progress_bar(percentage: float, length: int = 10) -> str:
    filled_length = int(length * percentage / 100)
    bar = '▰' * filled_length + '▱' * (length - filled_length)
    return bar


def get_week_calendar(history: List[str], days: int = 7) -> str:
    today = datetime.now()
    calendar = []

    for i in range(days - 1, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        weekday = date.strftime("%a")

        if date_str in history:
            symbol = "✅"
        else:
            if i == 0:
                symbol = "🔄"
            else:
                symbol = "❌"
        calendar.append(f"{weekday}{symbol}")
    return " ".join(calendar)


def format_habit_stats(habit: Dict, days: int = 7) -> str:
    today = datetime.now()
    history_set = set(habit.get("history", []))
    completed_days = 0

    for i in range(days):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if date in history_set:
            completed_days += 1

    percentage = (completed_days / days * 100) if days > 0 else 0
    progress_bar = create_progress_bar(percentage)

    created_date = datetime.strptime(habit["created"], "%Y-%m-%d")
    days_since_creation = (today - created_date).days + 1
    calendar = get_week_calendar(habit["history"])

    return f"""
📊 Статистика: {completed_days}/{days} дней ({percentage:.1f}%)
{progress_bar} {percentage:.0f}%

📅 Создана: {habit['created']} ({days_since_creation} дней назад)
🔥 Серия: {habit.get('streak', 0)} дней
🏆 Макс. серия: {habit.get('max_streak', 0)} дней
📈 Всего дней: {habit.get('total_days', 0)}

📆 Неделя: {calendar}
"""


def parse_reminder_time(time_str: str):
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours, minutes
    except:
        return 9, 0


def format_habits_list(habits: List[Dict]) -> str:
    if not habits:
        return "📭 У вас пока нет привычек. Добавьте первую с помощью /add_habit"

    lines = []
    for habit in habits:
        today = datetime.now().strftime("%Y-%m-%d")
        if today in habit.get("history", []):
            status = "✅"
        else:
            status = "🔄"

        streak = habit.get("streak", 0)
        lines.append(f"{habit['id']}. {status} <b>{habit['name']}</b>")
        lines.append(f"   🔥 Серия: {streak} дней | 📅 Создана: {habit['created']}")
        lines.append("")
    return "\n".join(lines)


def calculate_completion_rate(history: List[str], days: int = 30) -> float:
    if days <= 0:
        return 0.0

    today = datetime.now()
    history_set = set(history)
    completed = 0

    for i in range(days):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if date in history_set:
            completed += 1

    return (completed / days * 100) if days > 0 else 0.0


def create_weekly_report(habits: List[Dict]) -> str:
    if not habits:
        return "📭 Нет данных для отчета"

    total_habits = len(habits)
    completed_today = 0
    total_streak = 0
    total_completion_rate = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for habit in habits:
        if today in habit.get("history", []):
            completed_today += 1
        total_streak += habit.get("streak", 0)
        total_completion_rate += calculate_completion_rate(habit.get("history", []), 7)

    avg_streak = total_streak / total_habits if total_habits > 0 else 0
    avg_completion_rate = total_completion_rate / total_habits if total_habits > 0 else 0
    best_habit = max(habits, key=lambda h: h.get("streak", 0), default=None)

    report = f"""
📈 <b>НЕДЕЛЬНЫЙ ОТЧЕТ</b>

📊 Общая статистика:
┣ Привычек всего: {total_habits}
┣ Выполнено сегодня: {completed_today}/{total_habits}
┣ Средняя серия: {avg_streak:.1f} дней
┗ Средний процент выполнения: {avg_completion_rate:.1f}%

🏆 Лучшая привычка: {best_habit['name'] if best_habit else 'Нет данных'}
   🔥 Серия: {best_habit.get('streak', 0) if best_habit else 0} дней

📅 Календарь выполнения:
"""

    for habit in habits[:5]:
        calendar = get_week_calendar(habit.get("history", []))
        report += f"\n{habit['id']}. {habit['name']}: {calendar}"
    return report
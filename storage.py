"""
Модуль для работы с хранением данных привычек в JSON файле.
"""
import json
import asyncio
import aiofiles
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class HabitStorage:
    """Класс для асинхронного хранения и управления привычками в JSON файле"""

    def __init__(self, filename: str = "habits.json"):
        self.filename = filename
        self._cache: Dict[int, Dict] = {}
        self._lock = asyncio.Lock()

    async def _ensure_file_exists(self):
        async with self._lock:
            if not os.path.exists(self.filename):
                async with aiofiles.open(self.filename, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps({}, ensure_ascii=False, indent=2))

    async def _read_file(self) -> Dict:
        async with self._lock:
            try:
                async with aiofiles.open(self.filename, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content) if content.strip() else {}
            except (FileNotFoundError, json.JSONDecodeError):
                return {}

    async def _write_file(self, data: Dict):
        async with self._lock:
            async with aiofiles.open(self.filename, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    async def get_user_data(self, user_id: int) -> Dict:
        if user_id in self._cache:
            return self._cache[user_id]

        data = await self._read_file()
        user_data = data.get(str(user_id), {
            "habits": [],
            "timezone": "UTC",
            "settings": {"reminder": True, "reminder_time": "09:00"}
        })

        self._cache[user_id] = user_data
        return user_data

    async def save_user_data(self, user_id: int, data: Dict):
        self._cache[user_id] = data
        all_data = await self._read_file()
        all_data[str(user_id)] = data
        await self._write_file(all_data)

    async def add_habit(self, user_id: int, habit_name: str) -> Dict:
        """Добавить новую привычку"""
        # Убедимся, что файл существует
        await self._ensure_file_exists()

        user_data = await self.get_user_data(user_id)
        habits = user_data.get("habits", [])

        # Генерируем ID для новой привычки
        new_id = 1
        if habits:
            # Находим максимальный существующий ID
            max_id = max(habit["id"] for habit in habits)
            new_id = max_id + 1

        new_habit = {
            "id": new_id,
            "name": habit_name,
            "created": datetime.now().strftime("%Y-%m-%d"),
            "history": [],
            "streak": 0,
            "max_streak": 0,
            "total_days": 0
        }

        habits.append(new_habit)
        user_data["habits"] = habits
        await self.save_user_data(user_id, user_data)
        return new_habit

    async def check_habit(self, user_id: int, habit_id: int) -> bool:
        """Отметить выполнение привычки сегодня"""
        user_data = await self.get_user_data(user_id)
        habits = user_data.get("habits", [])
        today = datetime.now().strftime("%Y-%m-%d")

        for habit in habits:
            if habit["id"] == habit_id:
                if today in habit["history"]:
                    return False

                habit["history"].append(today)
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                if yesterday in habit["history"]:
                    habit["streak"] += 1
                else:
                    habit["streak"] = 1

                habit["max_streak"] = max(habit["max_streak"], habit["streak"])
                habit["total_days"] = len(set(habit["history"]))

                await self.save_user_data(user_id, user_data)
                return True
        return False

    async def uncheck_habit(self, user_id: int, habit_id: int) -> bool:
        """Снять отметку выполнения привычки"""
        user_data = await self.get_user_data(user_id)
        habits = user_data.get("habits", [])
        today = datetime.now().strftime("%Y-%m-%d")

        for habit in habits:
            if habit["id"] == habit_id:
                if today in habit["history"]:
                    habit["history"].remove(today)
                    habit["streak"] = self._calculate_current_streak(habit["history"])
                    habit["total_days"] = len(set(habit["history"]))
                    await self.save_user_data(user_id, user_data)
                    return True
        return False

    def _calculate_current_streak(self, history: List[str]) -> int:
        """Рассчитать текущую серию выполнений"""
        if not history:
            return 0

        dates = sorted(history, reverse=True)
        streak = 0
        current_date = datetime.now()

        for date_str in dates:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            if (current_date - date).days == streak:
                streak += 1
            else:
                break
        return streak

    async def get_habit_stats(self, user_id: int, habit_id: int, days: int = 7) -> Dict:
        """Получить статистику привычки"""
        user_data = await self.get_user_data(user_id)
        habits = user_data.get("habits", [])

        for habit in habits:
            if habit["id"] == habit_id:
                today = datetime.now()
                history_set = set(habit["history"])
                completed_days = 0

                for i in range(days):
                    date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                    if date in history_set:
                        completed_days += 1

                return {
                    "habit": habit,
                    "completed": completed_days,
                    "total": days,
                    "percentage": (completed_days / days * 100) if days > 0 else 0
                }
        return {}

    async def reset_user_habits(self, user_id: int):
        """Сбросить все привычки пользователя"""
        user_data = await self.get_user_data(user_id)
        user_data["habits"] = []
        await self.save_user_data(user_id, user_data)

    async def get_all_users(self) -> Dict:
        """Получить данные всех пользователей"""
        return await self._read_file()

    async def update_user_timezone(self, user_id: int, timezone: str):
        """Обновить часовой пояс пользователя"""
        user_data = await self.get_user_data(user_id)
        user_data["timezone"] = timezone
        await self.save_user_data(user_id, user_data)

    async def update_user_settings(self, user_id: int, settings: Dict):
        """Обновить настройки пользователя"""
        user_data = await self.get_user_data(user_id)
        user_data["settings"] = settings
        await self.save_user_data(user_id, user_data)

# Создаем глобальный экземпляр хранилища
storage = HabitStorage()
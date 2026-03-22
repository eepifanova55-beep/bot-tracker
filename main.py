"""
Основной модуль бота для отслеживания привычек.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from storage import storage
from utils import (
    create_progress_bar,
    get_week_calendar,
    format_habits_list,
    create_weekly_report
)

from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class HabitTrackerBot:
    """Основной класс бота для отслеживания привычек"""

    def __init__(self):
        self.token = os.getenv("BOT_TOKEN")
        if not self.token:
            raise ValueError("BOT_TOKEN не найден в .env файле")

        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Создаем отдельные обработчики для каждой команды
        handlers = [
            CommandHandler("start", self.start_command),
            CommandHandler("add_habit", self.add_habit_command),
            CommandHandler("list_habits", self.list_habits_command),
            CommandHandler("check", self.check_command),
            CommandHandler("uncheck", self.uncheck_command),
            CommandHandler("stats", self.stats_command),
            CommandHandler("report", self.report_command),
            CommandHandler("reset", self.reset_command),
            CommandHandler("settings", self.settings_command),
            CommandHandler("help", self.help_command),
        ]

        # Добавляем все командные обработчики
        for handler in handlers:
            self.application.add_handler(handler)

        # Обработчики callback-кнопок (должны быть после команд)
        self.application.add_handler(CallbackQueryHandler(self.button_callback, pattern="^habit_"))
        self.application.add_handler(CallbackQueryHandler(self.settings_callback, pattern="^settings_"))
        self.application.add_handler(CallbackQueryHandler(self.confirm_reset_callback, pattern="^reset_"))
        self.application.add_handler(CallbackQueryHandler(self.timezone_callback, pattern="^timezone_"))

        # Обработчик быстрых действий (должен быть отдельно)
        self.application.add_handler(CallbackQueryHandler(self.quick_action_callback))

        # Обработчик текстовых сообщений (только НЕ команды)
        # Используем фильтр, который исключает команды
        self.application.add_handler(MessageHandler(
            filters.TEXT & (~filters.COMMAND),
            self.text_message_handler
        ))

        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        logger.info(f"Команда /start получена от пользователя {update.effective_user.id}")

        user = update.effective_user
        welcome_text = f"""
👋 Привет, {user.first_name}!

🎯 Я бот для отслеживания привычек. Помогу тебе стать лучше каждый день!

📋 <b>Основные команды:</b>
/add_habit [название] - добавить новую привычку
/list_habits - список всех привычек
/check [номер] - отметить выполнение привычки
/uncheck [номер] - снять отметку
/stats [дней] - статистика за N дней
/report - недельный отчет
/reset - сбросить все привычки
/settings - настройки бота

💡 <b>Советы:</b>
• Начни с 1-2 простых привычек
• Отмечай выполнение каждый день
• Следи за своей серией 🔥

Добавь свою первую привычку командой /add_habit
        """

        keyboard = [
            [
                InlineKeyboardButton("➕ Добавить привычку", callback_data="quick_add"),
                InlineKeyboardButton("📋 Мои привычки", callback_data="quick_list")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)
        logger.info(f"Приветственное сообщение отправлено пользователю {user.id}")

    async def add_habit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /add_habit"""
        logger.info(f"Обработчик add_habit_command вызван с аргументами: {context.args}")

        if not context.args:
            await update.message.reply_text(
                "Используйте: /add_habit [название привычки]\nПример: /add_habit Зарядка по утрам"
            )
            return

        habit_name = " ".join(context.args)
        user_id = update.effective_user.id

        logger.info(f"Добавление привычки '{habit_name}' для пользователя {user_id}")

        try:
            new_habit = await storage.add_habit(user_id, habit_name)
            logger.info(f"Привычка добавлена успешно: {new_habit}")

            keyboard = [
                [
                    InlineKeyboardButton("✅ Отметить сегодня", callback_data=f"habit_check_{new_habit['id']}"),
                    InlineKeyboardButton("❌ Отменить", callback_data="habit_cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response = f"""
✅ Привычка добавлена!

📝 <b>{new_habit['name']}</b>
🆔 ID: {new_habit['id']}
📅 Создана: {new_habit['created']}
            """

            await update.message.reply_text(response, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Ошибка при добавлении привычки: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка при добавлении привычки: {str(e)}")

    async def list_habits_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /list_habits"""
        user_id = update.effective_user.id
        user_data = await storage.get_user_data(user_id)
        habits = user_data.get("habits", [])

        if not habits:
            await update.message.reply_text("📭 У вас пока нет привычек. Добавьте первую с помощью /add_habit")
            return

        response = format_habits_list(habits)
        keyboard = []

        for habit in habits:
            today = datetime.now().strftime("%Y-%m-%d")
            if today in habit.get("history", []):
                button_text = f"✅ {habit['name']}"
                callback_data = f"habit_uncheck_{habit['id']}"
            else:
                button_text = f"🔄 {habit['name']}"
                callback_data = f"habit_check_{habit['id']}"

            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        keyboard.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats_all"),
            InlineKeyboardButton("📈 Отчет", callback_data="report_weekly")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(response, parse_mode='HTML', reply_markup=reply_markup)

    async def check_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /check"""
        if not context.args:
            await update.message.reply_text("Используйте: /check [номер привычки]\nПример: /check 1")
            return

        try:
            habit_id = int(context.args[0])
            user_id = update.effective_user.id
            success = await storage.check_habit(user_id, habit_id)

            if success:
                user_data = await storage.get_user_data(user_id)
                habits = user_data.get("habits", [])
                habit = next((h for h in habits if h["id"] == habit_id), None)

                if habit:
                    response = f"""
✅ Отлично! Привычка отмечена!

📝 <b>{habit['name']}</b>
🔥 Текущая серия: {habit.get('streak', 0)} дней
🏆 Максимальная серия: {habit.get('max_streak', 0)} дней
📅 Всего дней: {habit.get('total_days', 0)}
                    """
                    await update.message.reply_text(response, parse_mode='HTML')
                else:
                    await update.message.reply_text("❌ Привычка не найдена")
            else:
                await update.message.reply_text("⚠️ Эта привычка уже отмечена сегодня")
        except ValueError:
            await update.message.reply_text("❌ Неверный номер привычки")

    async def uncheck_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /uncheck"""
        if not context.args:
            await update.message.reply_text("Используйте: /uncheck [номер привычки]\nПример: /uncheck 1")
            return

        try:
            habit_id = int(context.args[0])
            user_id = update.effective_user.id
            success = await storage.uncheck_habit(user_id, habit_id)

            if success:
                await update.message.reply_text("❌ Отметка снята")
            else:
                await update.message.reply_text("⚠️ Эта привычка не была отмечена сегодня")
        except ValueError:
            await update.message.reply_text("❌ Неверный номер привычки")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats"""
        user_id = update.effective_user.id
        user_data = await storage.get_user_data(user_id)
        habits = user_data.get("habits", [])
        days = 7

        if context.args:
            try:
                days = int(context.args[0])
                if days <= 0:
                    days = 7
            except ValueError:
                pass

        if not habits:
            await update.message.reply_text("📭 У вас пока нет привычек")
            return

        response = f"📊 <b>Статистика за {days} дней:</b>\n\n"
        total_completed = 0
        total_possible = len(habits) * days

        for habit in habits:
            today = datetime.now()
            history_set = set(habit.get("history", []))
            completed_days = 0

            for i in range(days):
                date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                if date in history_set:
                    completed_days += 1

            total_completed += completed_days
            percentage = (completed_days / days * 100) if days > 0 else 0
            progress_bar = create_progress_bar(percentage, length=5)

            response += f"{habit['id']}. {habit['name']}\n"
            response += f"   {progress_bar} {completed_days}/{days} дней ({percentage:.1f}%)\n\n"

        total_percentage = (total_completed / total_possible * 100) if total_possible > 0 else 0
        response += f"📈 <b>Общий прогресс:</b> {total_completed}/{total_possible} ({total_percentage:.1f}%)"
        await update.message.reply_text(response, parse_mode='HTML')

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /report"""
        user_id = update.effective_user.id
        user_data = await storage.get_user_data(user_id)
        habits = user_data.get("habits", [])

        if not habits:
            await update.message.reply_text("📭 У вас пока нет привычек")
            return

        report = create_weekly_report(habits)
        await update.message.reply_text(report, parse_mode='HTML')

    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /reset"""
        user_id = update.effective_user.id

        keyboard = [
            [
                InlineKeyboardButton("✅ Да, сбросить все", callback_data="reset_confirm"),
                InlineKeyboardButton("❌ Нет, отменить", callback_data="reset_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚠️ <b>ВНИМАНИЕ!</b>\n\nВы уверены, что хотите сбросить все свои привычки?\nЭто действие невозможно отменить!",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /settings"""
        user_id = update.effective_user.id
        user_data = await storage.get_user_data(user_id)

        timezone = user_data.get("timezone", "UTC")
        settings = user_data.get("settings", {"reminder": True, "reminder_time": "09:00"})

        response = f"""
⚙️ <b>Настройки бота</b>

🌍 Часовой пояс: {timezone}
🔔 Напоминания: {"✅ Включены" if settings.get("reminder", True) else "❌ Выключены"}
⏰ Время напоминания: {settings.get("reminder_time", "09:00")}
        """

        keyboard = [
            [
                InlineKeyboardButton("🔔 Напоминания", callback_data="settings_toggle_reminder"),
                InlineKeyboardButton("⏰ Время", callback_data="settings_change_time")
            ],
            [
                InlineKeyboardButton("🌍 Часовой пояс", callback_data="settings_change_timezone"),
                InlineKeyboardButton("📊 Статистика", callback_data="settings_stats")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(response, parse_mode='HTML', reply_markup=reply_markup)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📋 <b>СПРАВКА ПО КОМАНДАМ</b>

🎯 <b>Основные команды:</b>
/start - Начать работу с ботом
/add_habit [название] - Добавить новую привычку
/list_habits - Показать все привычки
/check [номер] - Отметить выполнение привычки
/uncheck [номер] - Снять отметку выполнения
/stats [дней] - Статистика за N дней (по умолчанию 7)
/report - Недельный отчет по всем привычкам
/reset - Сбросить все привычки
/settings - Настройки бота

📊 <b>Символы и обозначения:</b>
✅ - Привычка выполнена сегодня
🔄 - Привычка не выполнена сегодня
❌ - Привычка не выполнена вчера
▰ - Выполненный день в прогресс-баре
▱ - Пропущенный день в прогресс-баре
🔥 - Текущая серия дней подряд
        """
        await update.message.reply_text(help_text, parse_mode='HTML')

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки привычек"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id

        if data.startswith("habit_check_"):
            habit_id = int(data.split("_")[2])
            success = await storage.check_habit(user_id, habit_id)

            if success:
                user_data = await storage.get_user_data(user_id)
                habits = user_data.get("habits", [])
                habit = next((h for h in habits if h["id"] == habit_id), None)

                if habit:
                    keyboard = [
                        [InlineKeyboardButton("❌ Снять отметку", callback_data=f"habit_uncheck_{habit_id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    response = f"""
✅ <b>{habit['name']}</b> отмечена!

🔥 Серия: {habit.get('streak', 0)} дней
📅 Всего дней: {habit.get('total_days', 0)}
                    """
                    await query.edit_message_text(text=response, parse_mode='HTML', reply_markup=reply_markup)

        elif data.startswith("habit_uncheck_"):
            habit_id = int(data.split("_")[2])
            success = await storage.uncheck_habit(user_id, habit_id)

            if success:
                keyboard = [
                    [InlineKeyboardButton("✅ Отметить сегодня", callback_data=f"habit_check_{habit_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(text="❌ Отметка снята", parse_mode='HTML', reply_markup=reply_markup)

    async def settings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок настроек"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id

        if data == "settings_toggle_reminder":
            user_data = await storage.get_user_data(user_id)
            settings = user_data.get("settings", {"reminder": True, "reminder_time": "09:00"})
            settings["reminder"] = not settings.get("reminder", True)
            await storage.update_user_settings(user_id, settings)

            status = "включены" if settings["reminder"] else "выключены"
            await query.edit_message_text(text=f"🔔 Напоминания {status}", parse_mode='HTML')

        elif data == "settings_change_time":
            await query.edit_message_text(
                text="Введите время напоминания в формате HH:MM (например, 09:00):",
                parse_mode='HTML'
            )

    async def timezone_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик выбора часового пояса"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id

        if data.startswith("timezone_"):
            timezone = data.split("_", 1)[1]
            await storage.update_user_timezone(user_id, timezone)
            await query.edit_message_text(text=f"✅ Часовой пояс установлен: {timezone}", parse_mode='HTML')

    async def quick_action_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик быстрых действий"""
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "quick_add":
            await query.edit_message_text(text="Введите название новой привычки:", parse_mode='HTML')

        elif data == "quick_list":
            # Имитируем команду /list_habits
            user_id = query.from_user.id
            user_data = await storage.get_user_data(user_id)
            habits = user_data.get("habits", [])

            if not habits:
                await query.edit_message_text("📭 У вас пока нет привычек. Добавьте первую с помощью /add_habit")
                return

            response = format_habits_list(habits)
            keyboard = []

            for habit in habits:
                today = datetime.now().strftime("%Y-%m-%d")
                if today in habit.get("history", []):
                    button_text = f"✅ {habit['name']}"
                    callback_data = f"habit_uncheck_{habit['id']}"
                else:
                    button_text = f"🔄 {habit['name']}"
                    callback_data = f"habit_check_{habit['id']}"

                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

            keyboard.append([
                InlineKeyboardButton("📊 Статистика", callback_data="stats_all"),
                InlineKeyboardButton("📈 Отчет", callback_data="report_weekly")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, parse_mode='HTML', reply_markup=reply_markup)

        elif data == "stats_all":
            user_id = query.from_user.id
            user_data = await storage.get_user_data(user_id)
            habits = user_data.get("habits", [])
            days = 7

            if not habits:
                await query.edit_message_text("📭 У вас пока нет привычек")
                return

            response = f"📊 <b>Статистика за {days} дней:</b>\n\n"
            total_completed = 0
            total_possible = len(habits) * days

            for habit in habits:
                today = datetime.now()
                history_set = set(habit.get("history", []))
                completed_days = 0

                for i in range(days):
                    date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                    if date in history_set:
                        completed_days += 1

                total_completed += completed_days
                percentage = (completed_days / days * 100) if days > 0 else 0
                progress_bar = create_progress_bar(percentage, length=5)

                response += f"{habit['id']}. {habit['name']}\n"
                response += f"   {progress_bar} {completed_days}/{days} дней ({percentage:.1f}%)\n\n"

            total_percentage = (total_completed / total_possible * 100) if total_possible > 0 else 0
            response += f"📈 <b>Общий прогресс:</b> {total_completed}/{total_possible} ({total_percentage:.1f}%)"
            await query.edit_message_text(response, parse_mode='HTML')

        elif data == "report_weekly":
            user_id = query.from_user.id
            user_data = await storage.get_user_data(user_id)
            habits = user_data.get("habits", [])

            if not habits:
                await query.edit_message_text("📭 У вас пока нет привычек")
                return

            report = create_weekly_report(habits)
            await query.edit_message_text(report, parse_mode='HTML')

    async def confirm_reset_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик подтверждения сброса"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id

        if data == "reset_confirm":
            await storage.reset_user_habits(user_id)
            await query.edit_message_text(text="✅ Все привычки сброшены! Начните с чистого листа.", parse_mode='HTML')
        elif data == "reset_cancel":
            await query.edit_message_text(text="❌ Сброс отменен.", parse_mode='HTML')

    async def text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений (не команд)"""
        logger.info(f"Текстовое сообщение от {update.effective_user.id}: {update.message.text}")

        user_id = update.effective_user.id
        text = update.message.text.strip()

        # Обработка времени напоминания (формат HH:MM)
        if ":" in text and len(text) == 5:
            try:
                hours, minutes = map(int, text.split(":"))
                if 0 <= hours < 24 and 0 <= minutes < 60:
                    user_data = await storage.get_user_data(user_id)
                    settings = user_data.get("settings", {"reminder": True, "reminder_time": "09:00"})
                    settings["reminder_time"] = text
                    await storage.update_user_settings(user_id, settings)
                    await update.message.reply_text(f"✅ Время напоминания установлено: {text}", parse_mode='HTML')
                    return
            except ValueError:
                pass

        # Обработка названия новой привычки (длина больше 2 символов)
        elif len(text) > 2:
            # Проверяем, не пытается ли пользователь выполнить команду без "/"
            if text.lower() in ["список", "привычки", "мои привычки", "list"]:
                await self.list_habits_command(update, context)
                return

            try:
                new_habit = await storage.add_habit(user_id, text)
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Отметить сегодня", callback_data=f"habit_check_{new_habit['id']}"),
                        InlineKeyboardButton("📋 Все привычки", callback_data="quick_list")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                response = f"""
✅ Привычка добавлена!

📝 <b>{new_habit['name']}</b>
🆔 ID: {new_habit['id']}
                """
                await update.message.reply_text(response, parse_mode='HTML', reply_markup=reply_markup)
                return
            except Exception as e:
                logger.error(f"Ошибка при добавлении привычки из текста: {e}")
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
                return

        # Если ничего не подошло
        await update.message.reply_text(
            "Не понимаю ваше сообщение. Используйте команды или кнопки.\n"
            "Например: /help - список команд",
            parse_mode='HTML'
        )

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка при обработке запроса: {context.error}", exc_info=context.error)
        try:
            await update.effective_message.reply_text("❌ Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                                                      parse_mode='HTML')
        except:
            pass

    def run(self):
        """Запуск бота"""
        logger.info("Запуск бота...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Точка входа в приложение"""
    try:
        bot = HabitTrackerBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}", exc_info=True)


if __name__ == "__main__":
    main()
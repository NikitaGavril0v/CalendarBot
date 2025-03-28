import os
import pytz
from datetime import datetime, timedelta
from telegram.ext import Application, JobQueue
from config import logger, TIMEZONE
from database import init_database
from handlers import get_handlers
from handlers import send_event_notifications

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "Начать работу с ботом"),
        ("help", "Помощь и список команд"),
        ("events", "Просмотр событий"),
        ("addevent", "Создать событие (админ)"),
        ("admins", "Меню админов"),
        ("cancel", "Отменить действие")
    ])

def main():
    init_database()

    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Токен не найден")

    application = Application.builder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .build()

    # Регистрация обработчиков
    for handler in get_handlers():
        application.add_handler(handler)

    # Настройка заданий
    timezone = pytz.timezone(TIMEZONE)
    desired_time = datetime.strptime("07:00", "%H:%M").time()
    local_dt = timezone.localize(datetime.combine(datetime.now().date(), desired_time))
    utc_time = local_dt.astimezone(pytz.utc).time()

    application.job_queue.run_daily(
        send_event_notifications,
        time=utc_time
    )

    application.run_polling()

if __name__ == '__main__':
    main()
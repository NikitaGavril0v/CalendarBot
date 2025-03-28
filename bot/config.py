import os
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
DB_NAME = os.getenv("DB_NAME", "events.db")
DEFAULT_ADMIN_ID = os.getenv("ADMIN_ID")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
DB_NAME = "/app/data/" + DB_NAME

# Состояния ConversationHandler
(NAME, DATE, EVENT_NAME, EVENT_DESCRIPTION, EVENT_TIME, EVENT_MAX, PHONE,
 EDIT_CHOICE, EDIT_NAME, EDIT_DESCRIPTION, EDIT_TIME, EDIT_DATE, EDIT_MAX,
 CONFIRM_DELETE, ADMIN_MENU, ADD_ADMIN, REMOVE_ADMIN) = range(17)
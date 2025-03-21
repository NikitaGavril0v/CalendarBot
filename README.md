# CalendarBot

Бот-календарь для записи на ивенты

## Перед запуском

- Установить пакет sqlite3:
```bash
sudo apt install sqlite3
```
- Рекомендуется изпользовать виртуальное окружение python, пример создания:
```bash
python3 -m venv bot-venv
```
- Установить зависимости python:
```bash
pip install python-telegram-bot python-dotenv
```
- Создать файл .env в папке с bot.py и записать в него токен для бота в виде:
```env
TELEGRAM_BOT_TOKEN=<TOKEN>
```
## Запуск
```bash
python3 bot.py
```

## Добавление админа
- Открыть БД:
```bash
sqlite3 events.db
```
- Внести ид пользователя телеграмм в таблицу admins:
```SQL
INSERT INTO admins (user_id) VALUES (<id)>
```
- Выход:
```SQL
.exit
```

## Архитектура системы
Компоненты системы
- Telegram Bot
- Ядро бота, обрабатывающее запросы через Telegram API.
- Использует библиотеку python-telegram-bot для асинхронной работы.
- Webhook/Поллинг
- - Режим взаимодействия с Telegram (по умолчанию — поллинг).
- База данных SQLite для хранения данных о событиях, участниках и администраторах.
- - Таблицы: events, participants, admins, users.

## Как пользоваться ботом
Команды:
- /start – запуск бота.
- /events – просмотр событий.

Работа с календарем:
- Выберите дату → Просмотрите события → Запишитесь кнопкой "Записаться".

# CalendarBot

Бот-календарь для записи на ивенты

## Перед запуском

- Установить docker и docker-compose:
```bash
sudo apt install docker docker-compose
```
- Создать файл .env в папке с docker-compose.yml и заполнить его в виде:
```env
TELEGRAM_BOT_TOKEN=<TOKEN>
DB_NAME=events.db
ADMIN_ID=<User_Telegram_ID>
TIMEZONE=Europe/Moscow
```
## Запуск
```bash
sudo docker-compose up -d
```

## Добавление админа
- Добавить админа можно через чат-бота в меню админов (команда /admins)

## Архитектура системы
Компоненты системы
- Telegram Bot
- Ядро бота, обрабатывающее запросы через Telegram API.
- Использует библиотеку python-telegram-bot для асинхронной работы.
- Webhook/Поллинг
- - Режим взаимодействия с Telegram (по умолчанию — поллинг).
- База данных SQLite для хранения данных о событиях, участниках и администраторах.
- Таблицы: events, participants, admins, users, user_contacts.
  
```bash
.
├── bot/                 # Исходный код
│   ├── handlers.py      # Логика обработки сообщений
│   ├── database.py      # Работа с БД
│   ├── tg_calendar.py   # Генератор календаря
│   ├── config.py        # Файл конфигурации
│   └── main.py.         # Исполняемый файл
├── data/                # Персистентные данные
│   └── events.db       
├── Dockerfile           # Конфигурация контейнера
└── docker-compose.yml   # Оркестрация сервисов
```
## Как пользоваться ботом
Команды:
- /start - Начать работу с ботом
- /help - Показать это сообщение
- /events - Просмотреть доступные события
- /cancel - Отменить текущее действие

Админ-команды:
- /addevent - Создать новое событие
- /admins - Управление администраторами

Работа с календарем:
- Выберите дату → Просмотрите события → Запишитесь кнопкой "Записаться".

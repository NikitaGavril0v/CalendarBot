import sqlite3
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
import os


DB_NAME = 'events.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            creator_id INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            event_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY(event_id, user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

class Calendar:
    @staticmethod
    def create_calendar(year=None, month=None):
        now = datetime.now()
        year = year or now.year
        month = month or now.month

        keyboard = []
        first_day = datetime(year, month, 1)
        
        # Русские названия месяцев
        months_ru = [
            'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
            'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
        ]
        header = f"{months_ru[month-1]} {year}"
        keyboard.append([InlineKeyboardButton(header, callback_data='ignore')])
        
        # Дни недели на русском
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        keyboard.append([InlineKeyboardButton(day, callback_data='ignore') for day in days])
        
        month_days = []
        day = first_day
        while day.month == month:
            month_days.append(day.day)
            day += timedelta(days=1)
        
        week = []
        # Корректный расчет отступов для понедельника
        for _ in range(first_day.weekday() % 7):
            week.append(InlineKeyboardButton(" ", callback_data='ignore'))
        
        for d in month_days:
            week.append(InlineKeyboardButton(str(d), callback_data=f'view_{year}-{month:02}-{d:02}'))
            if len(week) == 7:
                keyboard.append(week)
                week = []
        
        # Дополняем последнюю неделю пустыми кнопками
        if week:
            while len(week) < 7:
                week.append(InlineKeyboardButton(" ", callback_data='ignore'))
            keyboard.append(week)
        
        # Кнопки навигации
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        
        keyboard.append([
            InlineKeyboardButton("<", callback_data=f'nav_{prev_year}-{prev_month}'),
            InlineKeyboardButton(">", callback_data=f'nav_{next_year}-{next_month}')
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def get_current_month():
        now = datetime.now()
        return now.year, now.month

def is_admin(user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def update_user_info(user: dict):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, first_name, last_name, username)
        VALUES (?, ?, ?, ?)
    ''', (
        user['id'],
        user.get('first_name', ''),
        user.get('last_name', ''),
        user.get('username', '')
    ))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    update_user_info({
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username
    })
    
    await update.message.reply_text(
        "Привет! Я бот для управления событиями.\n"
        "Админы могут создавать события через /addevent\n"
        "Все пользователи могут просматривать и записываться на события через /events"
    )

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав для создания событий!")
        return
    markup = Calendar.create_calendar()
    await update.message.reply_text("Выберите дату для события:", reply_markup=markup)

async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = Calendar.create_calendar()
    await update.message.reply_text("Выберите дату для просмотра событий:", reply_markup=markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith('nav_'):
        if data == 'nav_current':
            year, month = Calendar.get_current_month()
        else:
            try:
                year, month = map(int, data.split('_')[1].split('-'))
            except ValueError:
                await query.edit_message_text("Ошибка навигации")
                return
        
        markup = Calendar.create_calendar(year, month)
        await query.edit_message_text(text="Выберите дату:", reply_markup=markup)
    
    elif data.startswith('view_'):
        date = data.split('_')[1]
        await show_events_for_date(query, date, user_id)
    
    elif data.startswith('event_'):
        action, event_id = data.split('_')[1:]
        await handle_event_action(query, event_id, action, user_id)
    
    elif data.startswith('create_'):
        if not is_admin(user_id):
            await query.edit_message_text("⛔ Только админы могут создавать события!")
            return
        date = data.split('_')[1]
        context.user_data['event_date'] = date
        await query.edit_message_text(f"📅 Создание события на {date}\nВведите описание события:")

async def show_events_for_date(query, date: str, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT e.id, e.description 
        FROM events e 
        WHERE e.date = ?
    ''', (date,))
    events = cursor.fetchall()
    conn.close()

    if not events:
        await query.edit_message_text(f"На {date} нет событий")

    response = f"📅 События на {date}:\n\n"
    keyboard = []
    for event_id, description in events:
        response += f"▪️ {description}\n"
        keyboard.append([
            InlineKeyboardButton(
                f"🎫 {description[:15]}...", 
                callback_data=f'event_details_{event_id}'
            )
        ])
    
    if is_admin(user_id):
        keyboard.append([
            InlineKeyboardButton("➕ Создать событие", callback_data=f'create_{date}')
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к календарю", callback_data='nav_current')])
    
    await query.edit_message_text(
        text=response,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_event_action(query, event_id: int, action: str, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        if action == 'details':
            cursor.execute('''
                SELECT e.date, e.description, 
                (SELECT COUNT(*) FROM participants WHERE event_id = e.id),
                EXISTS(SELECT 1 FROM participants WHERE event_id = e.id AND user_id = ?)
                FROM events e WHERE e.id = ?
            ''', (user_id, event_id))
            event_data = cursor.fetchone()
            
            user = {
                'id': user_id,
                'first_name': query.from_user.first_name,
                'last_name': query.from_user.last_name,
                'username': query.from_user.username
            }
            update_user_info(user)
            
            if not event_data:
                await query.edit_message_text("Событие не найдено")
                return
                
            date, desc, participants_count, is_registered = event_data
            status = "✅ Вы записаны" if is_registered else "❌ Вы не записаны"
            
            text = f"""
📅 Дата: {date}
📝 Описание: {desc}
👥 Участников: {participants_count}
{status}
            """.strip()
            
            keyboard = [
                [InlineKeyboardButton("👥 Показать участников", callback_data=f'event_participants_{event_id}')],
                [InlineKeyboardButton("📝 Записаться" if not is_registered else "❌ Отменить запись", 
                callback_data=f'event_{"join" if not is_registered else "leave"}_{event_id}')],
                [InlineKeyboardButton("🔙 Назад", callback_data=f'view_{date}')]
            ]
            
            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif action == 'join':
            try:
                cursor.execute('INSERT INTO participants VALUES (?, ?)', (event_id, user_id))
                conn.commit()
                await query.answer("✅ Вы успешно записались!")
                await handle_event_action(query, event_id, 'details', user_id)
            except sqlite3.IntegrityError:
                await query.answer("⚠️ Вы уже записаны на это событие")
        
        elif action == 'leave':
            cursor.execute('DELETE FROM participants WHERE event_id = ? AND user_id = ?', (event_id, user_id))
            conn.commit()
            await query.answer("✅ Запись отменена")
            await handle_event_action(query, event_id, 'details', user_id)
        
        elif action == 'participants':
            cursor.execute('''
                SELECT u.first_name, u.last_name, u.username
                FROM participants p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.event_id = ?
            ''', (event_id,))
            participants = cursor.fetchall()
            
            if not participants:
                await query.answer("На это событие пока никто не записался")
                return
            
            response = "👥 Участники события:\n\n"
            for i, (first, last, username) in enumerate(participants, 1):
                name = f"{first} {last}".strip()
                if username:
                    response += f"{i}. @{username} ({name})\n"
                else:
                    response += f"{i}. {name}\n"
            
            if is_admin(user_id):
                cursor.execute('SELECT user_id FROM participants WHERE event_id = ?', (event_id,))
                user_ids = [str(row[0]) for row in cursor.fetchall()]
                response += f"\n🆔 ID участников: {', '.join(user_ids)}"
            
            await query.edit_message_text(
                text=response,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data=f'event_details_{event_id}')]
                ]))
    
    finally:
        conn.close()

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав для создания событий!")
        return
    
    text = update.message.text
    date = context.user_data.get('event_date')
    
    if date:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO events (date, description, creator_id) VALUES (?, ?, ?)', 
                      (date, text, user_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Событие на {date} создано!")
        del context.user_data['event_date']

def main():
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('addevent', add_event))
    application.add_handler(CommandHandler('events', show_events))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    application.run_polling()

if __name__ == '__main__':
    main()
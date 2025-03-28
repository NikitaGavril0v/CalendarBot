from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import sqlite3
from config import DB_NAME

class Calendar:
    @staticmethod
    def create_calendar(year=None, month=None, user_id=None):
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        
        # Получаем данные из БД
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            
            # Даты с любыми событиями
            cursor.execute('''
                SELECT DISTINCT date 
                FROM events 
                WHERE strftime('%Y-%m', date) = ?
            ''', (f"{year}-{month:02}",))
            event_dates = {row[0] for row in cursor.fetchall()}
            
            # Даты с участием пользователя
            user_event_dates = set()
            if user_id:
                cursor.execute('''
                    SELECT DISTINCT e.date
                    FROM events e
                    JOIN participants p ON e.id = p.event_id
                    WHERE p.user_id = ? 
                    AND strftime('%Y-%m', e.date) = ?
                ''', (user_id, f"{year}-{month:02}"))
                user_event_dates = {row[0] for row in cursor.fetchall()}

        # Локализация
        months_ru = [
            'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
            'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
        ]
        
        # Создаем структуру календаря
        keyboard = [
            [InlineKeyboardButton(f"{months_ru[month-1]} {year}", callback_data='ignore')],
            [InlineKeyboardButton(day, callback_data='ignore') for day in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]]
        ]

        # Рассчитываем дни месяца
        first_day = datetime(year, month, 1)
        last_day = datetime(year + month//12, month%12 + 1, 1) - timedelta(days=1)
        
        # Пустые дни в начале
        week = [InlineKeyboardButton(" ", callback_data='ignore') 
               for _ in range(first_day.weekday() % 7)]

        # Заполняем дни
        for day in range(1, last_day.day + 1):
            current_date = datetime(year, month, day)
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Определяем стиль кнопки
            is_today = current_date.date() == now.date()
            has_events = date_str in event_dates
            has_participation = date_str in user_event_dates
            
            emoji = ""
            if has_participation:
                emoji = "📌"
            elif has_events:
                emoji = "|"
                
            day_str = f"{emoji}{day}{'|' if has_events and not has_participation else ''}"

            week.append(InlineKeyboardButton(
                day_str,
                callback_data=f'view_{date_str}'
            ))
            
            # Новая неделя
            if len(week) == 7:
                keyboard.append(week)
                week = []

        # Пустые дни в конце
        if week:
            week += [InlineKeyboardButton(" ", callback_data='ignore')] * (7 - len(week))
            keyboard.append(week)

        # Навигация
        prev_year, prev_month = (year-1, 12) if month == 1 else (year, month-1)
        next_year, next_month = (year+1, 1) if month == 12 else (year, month+1)
        
        keyboard.append([
            InlineKeyboardButton("<", callback_data=f'nav_{prev_year}-{prev_month}'),
            InlineKeyboardButton(">", callback_data=f'nav_{next_year}-{next_month}')
        ])

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_current_month():
        now = datetime.now()
        return now.year, now.month
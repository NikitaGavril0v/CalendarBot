import sqlite3
from config import DB_NAME, DEFAULT_ADMIN_ID, logger

class DatabaseHandler:
    @staticmethod
    def init_db():
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
    
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT
                )
            ''')
    
            # Таблица событий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    time TEXT,
                    name TEXT,
                    description TEXT,
                    creator_id INTEGER,
                    max_participants INTEGER DEFAULT 0
                )
            ''')
    
            # Таблица участников
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    event_id INTEGER,
                    user_id INTEGER,
                    PRIMARY KEY(event_id, user_id)
                )
            ''')
    
            # Таблица администраторов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY
                )
            ''')
    
            # Таблица контактов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_contacts (
                    user_id INTEGER PRIMARY KEY,
                    phone TEXT
                )
            ''')
    
            # Добавляем администратора по умолчанию
            if DEFAULT_ADMIN_ID:
                try:
                    admin_id = int(DEFAULT_ADMIN_ID)
                    cursor.execute('''
                        INSERT OR IGNORE INTO admins (user_id)
                        VALUES (?)
                    ''', (admin_id,))
                    conn.commit()
                    logger.info(f"Администратор {admin_id} добавлен через переменную окружения")
                except ValueError:
                    logger.error("Неверный формат ADMIN_ID в переменных окружения")
            
            # Индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_date ON events(date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_participants_event_id ON participants(event_id)')
            conn.commit()
    
    @staticmethod
    def get_user_phone(user_id: int) -> str:
        with sqlite3.connect(DB_NAME) as conn:
            result = conn.execute('SELECT phone FROM user_contacts WHERE user_id = ?', (user_id,)).fetchone()
            return result[0] if result else None

    @staticmethod
    def update_contact(user_id: int, phone: str):
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO user_contacts
                VALUES (?, ?)
            ''', (user_id, phone))
            conn.commit()

    @staticmethod
    def is_admin(user_id: int) -> bool:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
            return cursor.fetchone() is not None

    @staticmethod
    def update_user_info(user: dict):
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO users
                VALUES (?, ?, ?, ?)
            ''', (
                user['id'],
                user.get('first_name', ''),
                user.get('last_name', ''),
                user.get('username', '')
            ))
            conn.commit()
    @staticmethod
    def get_event_dates(year: int, month: int) -> list:
        """Возвращает список дат с событиями в формате 'YYYY-MM-DD' для указанного месяца"""
        month_str = f"{year}-{month:02}"
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT date 
                FROM events 
                WHERE strftime('%Y-%m', date) = ?
            ''', (month_str,))
            return [row[0] for row in cursor.fetchall()]
    @staticmethod
    def get_user_event_dates(user_id: int, year: int, month: int) -> list:
        """Возвращает даты с событиями пользователя в формате 'YYYY-MM-DD'"""
        month_str = f"{year}-{month:02}"
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT e.date
                FROM events e
                JOIN participants p ON e.id = p.event_id
                WHERE p.user_id = ? 
                AND strftime('%Y-%m', e.date) = ?
            ''', (user_id, month_str))
            return [row[0] for row in cursor.fetchall()]
    @staticmethod
    def get_admins():
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM admins')
            return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def get_admins_with_info():
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.user_id, u.first_name, u.last_name, u.username 
                FROM admins a
                LEFT JOIN users u ON a.user_id = u.user_id
            ''')
            return cursor.fetchall()
    @staticmethod
    def get_all_users():
        """Получить всех зарегистрированных пользователей"""
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, first_name, last_name, username 
                FROM users
                ORDER BY first_name, last_name
            ''')
            return cursor.fetchall()

def init_database():
    DatabaseHandler.init_db()
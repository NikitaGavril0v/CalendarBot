from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from config import DB_NAME, TIMEZONE, logger
from database import DatabaseHandler
from tg_calendar import Calendar
import pytz
import sqlite3
from datetime import datetime

# Импорт состояний из config
from config import (
    NAME, DATE, EVENT_NAME, EVENT_DESCRIPTION, EVENT_TIME, EVENT_MAX, PHONE,
    EDIT_CHOICE, EDIT_NAME, EDIT_DESCRIPTION, EDIT_TIME, EDIT_DATE, EDIT_MAX,
    CONFIRM_DELETE, ADMIN_MENU, ADD_ADMIN, REMOVE_ADMIN
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    DatabaseHandler.update_user_info({
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username
    })

    if not DatabaseHandler.get_user_phone(user.id):
        contact_button = KeyboardButton("📱 Поделиться контактом", request_contact=True)
        await update.message.reply_text(
            "Для использования бота необходимо поделиться контактом:",
            reply_markup=ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True)
        )
        return PHONE

    await update.message.reply_text(
        "Привет! Я бот для управления событиями.\n"
        "Админы могут создавать события через /addevent\n"
        "Все пользователи могут просматривать и записываться на события через /events",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    phone = update.message.contact.phone_number
    DatabaseHandler.update_contact(user.id, phone)
    await update.message.reply_text("✅ Спасибо! Теперь вы можете использовать бота.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not DatabaseHandler.is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав для создания событий!")
        return

    context.user_data['creating_event'] = {}
    markup = Calendar.create_calendar()
    await update.message.reply_text("Выберите дату для события:", reply_markup=markup)
    return DATE

async def date_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith('nav_'):
        year, month = map(int, query.data.split('_')[1].split('-'))
        await query.edit_message_text(
            text="Выберите дату:",
            reply_markup=Calendar.create_calendar(year, month))

    if query.data.startswith('view_'):
        date = query.data.split('_')[1]
        context.user_data['creating_event']['date'] = date
        await query.edit_message_text("📝 Введите название события:")
        return EVENT_NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("❌ Название не может быть пустым!")
        return EVENT_NAME

    context.user_data['creating_event']['name'] = name
    await update.message.reply_text("📄 Введите описание события:")
    return EVENT_DESCRIPTION

async def description_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Описание не может быть пустым!")
        return EVENT_DESCRIPTION

    context.user_data['creating_event']['description'] = text
    await update.message.reply_text("⏰ Введите время события в формате ЧЧ:ММ (например 14:30):")
    return EVENT_TIME

async def time_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        datetime.strptime(time_str, "%H:%M")
        context.user_data['creating_event']['time'] = time_str
        await update.message.reply_text("👥 Введите максимальное количество участников (0 - без ограничений):")
        return EVENT_MAX
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Используйте ЧЧ:ММ (например 14:30)")
        return EVENT_TIME

async def max_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_part = int(update.message.text.strip())
        if max_part < 0:
            raise ValueError

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('''
                INSERT INTO events (date, time, name, description, creator_id, max_participants)
                 VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                context.user_data['creating_event']['date'],
                context.user_data['creating_event'].get('time', ''),
                context.user_data['creating_event']['name'],  # Добавлено имя
                context.user_data['creating_event']['description'],
                update.message.from_user.id,
                max_part
            ))
            conn.commit()

        await update.message.reply_text("✅ Событие успешно создано!")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите целое число больше или равное 0")
        return EVENT_MAX

async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    markup = Calendar.create_calendar(user_id=user_id)
    await update.message.reply_text("Выберите дату для просмотра событий:", reply_markup=markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    try:
        if data.startswith('edit_'):
            event_id = data.split('_')[1]
            return await start_edit_event(update, context)

        elif data.startswith('delete_'):
            event_id = data.split('_')[1]
            return await confirm_delete_handler(update, context)

        elif data.startswith('nav_'):
            year, month = map(int, data.split('_')[1].split('-'))
            await query.edit_message_text(
                text="Выберите дату:",
                reply_markup=Calendar.create_calendar(year, month, user_id)
            )

        elif data.startswith('view_'):
            date = data.split('_')[1]
            await show_events_for_date(query, date, user_id)

        elif data.startswith('event_'):
            parts = data.split('_')
            if len(parts) == 3:
                action, event_id = parts[1], parts[2]
                await handle_event_action(query, event_id, action, user_id)
            else:
                await query.edit_message_text("Ошибка обработки запроса")

    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}")
        await query.answer("⚠️ Произошла ошибка")

async def show_events_for_date(query, date: str, user_id: int):
    try:
        # Парсим дату для получения года и месяца
        selected_date = datetime.strptime(date, "%Y-%m-%d")
        year = selected_date.year
        month = selected_date.month
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, time, name
                FROM events
                WHERE date = ?
                ORDER BY time
            ''', (date,))
            events = cursor.fetchall()

        if not events:
            await query.edit_message_text(f"На {date} нет событий", reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Назад к календарю", callback_data=f'nav_{year}-{month}')]
                    ]))
            return

        # Если событие только одно - сразу показываем его
        if len(events) == 1:
            event_id, time, desc = events[0]
            await show_single_event(query, event_id, user_id, date)
            return

        # Если событий несколько - показываем список
        keyboard = []
        for eid, time, name in events:
            btn_text = f"{time} - {name[:15]}..." if time else name[:20]
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f'event_details_{eid}')])

        keyboard.append([InlineKeyboardButton("🔙 Назад к календарю", callback_data=f'nav_{year}-{month}')])

        try:
            await query.edit_message_text(
                text=f"📅 События на {date}:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                await query.answer()
            else:
                raise

    except Exception as e:
        logger.error(f"Ошибка показа событий: {e}")
        await query.answer("⚠️ Произошла ошибка")

async def show_single_event(query, event_id: int, user_id: int, date: str):
    try:
        # Парсим дату для получения года и месяца
        selected_date = datetime.strptime(date, "%Y-%m-%d")
        year = selected_date.year
        month = selected_date.month
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT e.name, e.date, e.time, e.description,
                e.max_participants, COUNT(p.user_id),
                EXISTS(SELECT 1 FROM participants WHERE event_id = e.id AND user_id = ?)
                FROM events e
                LEFT JOIN participants p ON e.id = p.event_id
                WHERE e.id = ?
                GROUP BY e.id
            ''', (user_id, event_id))
            event_data = cursor.fetchone()

            if not event_data:
                await query.edit_message_text("Событие не найдено")
                return

            name, date, time, desc, max_part, participants_count, is_registered = event_data
            participants_text = ""

            if DatabaseHandler.is_admin(user_id):
                participants = conn.execute('''
                    SELECT u.username, u.first_name, uc.phone
                    FROM participants p
                    JOIN users u ON p.user_id = u.user_id
                    LEFT JOIN user_contacts uc ON p.user_id = uc.user_id
                    WHERE p.event_id = ?
                ''', (event_id,)).fetchall()
                participants_text = "\n👥 Участники:\n" + "\n".join(
                    f"• @{un} ({ph})" if un and ph else
                    f"• {fn} ({ph})" if ph else
                    f"• @{un}" if un else f"• {fn}"
                    for un, fn, ph in participants
                )
            else:
                if max_part > 0:
                    participants_text = f"\n👥 Записано: {participants_count}/{max_part}"
                else:
                    participants_text = f"\n👥 Записано: {participants_count}"

            text = f"""
🏷 Название: {name}
📅 Дата: {date}
⏰ Время: {time or 'Не указано'}
📄 Описание: {desc}
{participants_text}
            """.strip()

            keyboard = []
            if is_registered:
                keyboard.append([InlineKeyboardButton("❌ Отменить запись", callback_data=f'event_leave_{event_id}')])
            else:
                if max_part == 0 or participants_count < max_part:
                    keyboard.append([InlineKeyboardButton("✅ Записаться", callback_data=f'event_join_{event_id}')])

            if DatabaseHandler.is_admin(user_id):
                keyboard.append([
                    InlineKeyboardButton("✏️ Редактировать", callback_data=f'edit_{event_id}'),
                    InlineKeyboardButton("🗑 Удалить", callback_data=f'delete_{event_id}')
                ])

            keyboard.append([InlineKeyboardButton("🔙 Назад к календарю", callback_data=f'nav_{year}-{month}')])

            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                if "Message is not modified" in str(e):
                    await query.answer()
                else:
                    raise

    except Exception as e:
        logger.error(f"Ошибка показа события: {e}")
        await query.answer("⚠️ Произошла ошибка")

async def handle_event_action(query, event_id: int, action: str, user_id: int):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()

            if action == 'details':
                cursor.execute('''
                    SELECT e.name, e.date, e.time, e.description,
                    e.max_participants, COUNT(p.user_id),
                    EXISTS(SELECT 1 FROM participants WHERE event_id = e.id AND user_id = ?)
                    FROM events e
                    LEFT JOIN participants p ON e.id = p.event_id
                    WHERE e.id = ?
                    GROUP BY e.id
                ''', (user_id, event_id))
                event_data = cursor.fetchone()

                if not event_data:
                    await query.edit_message_text("Событие не найдено")
                    return

                name, date, time, desc, max_part, participants_count, is_registered = event_data
                participants_text = ""

                if DatabaseHandler.is_admin(user_id):
                    participants = conn.execute('''
                        SELECT u.username, u.first_name, uc.phone
                        FROM participants p
                        JOIN users u ON p.user_id = u.user_id
                        LEFT JOIN user_contacts uc ON p.user_id = uc.user_id
                        WHERE p.event_id = ?
                    ''', (event_id,)).fetchall()
                    participants_text = "\n👥 Участники:\n" + "\n".join(
                        f"• @{un} ({ph})" if un and ph else
                        f"• {fn} ({ph})" if ph else
                        f"• @{un}" if un else f"• {fn}"
                        for un, fn, ph in participants
                    )
                else:
                    if max_part > 0:
                        participants_text = f"\n👥 Записано: {participants_count}/{max_part}"
                    else:
                        participants_text = f"\n👥 Записано: {participants_count}"

                text = f"""
🏷 Название: {name}
📅 Дата: {date}
⏰ Время: {time or 'Не указано'}
📄 Описание: {desc}
{participants_text}
                """.strip()

                keyboard = []
                if is_registered:
                    keyboard.append([InlineKeyboardButton("❌ Отменить запись", callback_data=f'event_leave_{event_id}')])
                else:
                    if max_part == 0 or participants_count < max_part:
                        keyboard.append([InlineKeyboardButton("✅ Записаться", callback_data=f'event_join_{event_id}')])

                if DatabaseHandler.is_admin(user_id):
                    keyboard.append([
                        InlineKeyboardButton("✏️ Редактировать", callback_data=f'edit_{event_id}'),
                        InlineKeyboardButton("🗑 Удалить", callback_data=f'delete_{event_id}')
                    ])

                keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'view_{date}')])

                await query.edit_message_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard))

            elif action in ('join', 'leave'):
                cursor.execute('''
                    SELECT max_participants, COUNT(p.user_id)
                    FROM events e
                    LEFT JOIN participants p ON e.id = p.event_id
                    WHERE e.id = ?
                ''', (event_id,))
                max_part, current = cursor.fetchone()
                cursor.execute('''
                    SELECT e.name, e.date, e.time, e.description,
                    e.max_participants, COUNT(p.user_id),
                    EXISTS(SELECT 1 FROM participants WHERE event_id = e.id AND user_id = ?)
                    FROM events e
                    LEFT JOIN participants p ON e.id = p.event_id
                    WHERE e.id = ?
                    GROUP BY e.id
                ''', (user_id, event_id))
                event_data = cursor.fetchone()
                name, date, time, desc, max_part, participants_count, is_registered = event_data
                with sqlite3.connect(DB_NAME) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT id, time, name
                        FROM events
                        WHERE date = ?
                        ORDER BY time
                ''', (date,))
                events = cursor.fetchall()

                if action == 'join':
                    try:
                        cursor.execute('INSERT INTO participants VALUES (?, ?)', (event_id, user_id))
                        conn.commit()
                        await query.answer("✅ Вы успешно записались!")
                    except sqlite3.IntegrityError:
                        await query.answer("⚠️ Вы уже записаны")

                elif action == 'leave':
                    cursor.execute('DELETE FROM participants WHERE event_id = ? AND user_id = ?', (event_id, user_id))
                    conn.commit()
                    await query.answer("✅ Запись отменена")

                if len(events) == 1:
                    event_id, time, desc = events[0]
                    await show_single_event(query, event_id, user_id, date)
                    return
                # Обновляем информацию о событии
                await handle_event_action(query, event_id, 'details', user_id)

    except Exception as e:
        logger.error(f"Ошибка обработки события: {e}")
        await query.answer("⚠️ Произошла ошибка")

async def start_edit_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split('_')[1])

    context.user_data['editing_event'] = {'id': event_id}

    keyboard = [
        [
            InlineKeyboardButton("Название", callback_data='edit_name'),
            InlineKeyboardButton("Описание", callback_data='edit_desc'),
        ],
        [
            InlineKeyboardButton("Дату", callback_data='edit_date'),
            InlineKeyboardButton("Время", callback_data='edit_time'),
        ],
        [
            InlineKeyboardButton("Участников", callback_data='edit_max'),
            InlineKeyboardButton("Удалить", callback_data='delete_event'),
        ],
        [InlineKeyboardButton("Отмена", callback_data='cancel_edit')]
    ]

    await query.edit_message_text(
        text="✏️ Выберите что редактировать:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_CHOICE

async def edit_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == 'edit_name':
        await query.edit_message_text("📝 Введите новое название:")
        return EDIT_NAME
    elif choice == 'edit_desc':
        await query.edit_message_text("📄 Введите новое описание:")
        return EDIT_DESCRIPTION
    elif choice == 'edit_time':
        await query.edit_message_text("⏰ Введите новое время (ЧЧ:ММ):")
        return EDIT_TIME
    elif choice == 'edit_date':
        await query.edit_message_text("📅 Выберите новую дату:",
                                    reply_markup=Calendar.create_calendar())
        return EDIT_DATE
    elif choice == 'edit_max':
        await query.edit_message_text("👥 Введите новое макс. количество участников:")
        return EDIT_MAX
    elif choice == 'delete_event':
        await query.edit_message_text("❌ Вы уверены что хотите удалить событие?",
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("Да", callback_data='confirm_delete'),
                                         InlineKeyboardButton("Нет", callback_data='cancel_edit')]
                                    ]))
        return CONFIRM_DELETE
    elif choice == 'cancel_edit':
        return await cancel_edit(update, context)

async def edit_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    event_id = context.user_data['editing_event']['id']
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('UPDATE events SET name = ? WHERE id = ?', (new_name, event_id))
        conn.commit()
    with sqlite3.connect(DB_NAME) as conn:
        event_date = conn.execute('SELECT date FROM events WHERE id = ?', (event_id,)).fetchone()[0]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 К событию", callback_data=f'view_{event_date}')]
    ])    
    await update.message.reply_text("✅ Название обновлено!", reply_markup=keyboard)
    return ConversationHandler.END

async def edit_description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_desc = update.message.text.strip()
    event_id = context.user_data['editing_event']['id']

    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('UPDATE events SET description = ? WHERE id = ?', (new_desc, event_id))
        conn.commit()
    with sqlite3.connect(DB_NAME) as conn:
        event_date = conn.execute('SELECT date FROM events WHERE id = ?', (event_id,)).fetchone()[0]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 К событию", callback_data=f'view_{event_date}')]
    ])
    await update.message.reply_text("✅ Описание обновлено!", reply_markup=keyboard)
    return ConversationHandler.END

async def edit_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        datetime.strptime(time_str, "%H:%M")
        event_id = context.user_data['editing_event']['id']

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('UPDATE events SET time = ? WHERE id = ?', (time_str, event_id))
            conn.commit()
        with sqlite3.connect(DB_NAME) as conn:
            event_date = conn.execute('SELECT date FROM events WHERE id = ?', (event_id,)).fetchone()[0]

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 К событию", callback_data=f'view_{event_date}')]
        ])
        await update.message.reply_text("✅ Время обновлено!",reply_markup=keyboard)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени!")
        return EDIT_TIME

async def edit_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith('view_'):
        new_date = query.data.split('_')[1]
        event_id = context.user_data['editing_event']['id']

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('UPDATE events SET date = ? WHERE id = ?', (new_date, event_id))
            conn.commit()
        with sqlite3.connect(DB_NAME) as conn:
            event_date = conn.execute('SELECT date FROM events WHERE id = ?', (event_id,)).fetchone()[0]

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 К событию", callback_data=f'view_{event_date}')]
        ])
        await query.edit_message_text("✅ Дата обновлена!", reply_markup=keyboard)
        
        return ConversationHandler.END

    elif query.data.startswith('nav_'):
        year, month = map(int, query.data.split('_')[1].split('-'))
        await query.edit_message_reply_markup(Calendar.create_calendar(year, month))
        return EDIT_DATE

async def edit_max_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_part = int(update.message.text.strip())
        if max_part < 0:
            raise ValueError

        event_id = context.user_data['editing_event']['id']

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('UPDATE events SET max_participants = ? WHERE id = ?', (max_part, event_id))
            conn.commit()
        with sqlite3.connect(DB_NAME) as conn:
            event_date = conn.execute('SELECT date FROM events WHERE id = ?', (event_id,)).fetchone()[0]

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 К событию", callback_data=f'view_{event_date}')]
        ])
        await update.message.reply_text("✅ Лимит участников обновлен!", reply_markup=keyboard)

        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите число ≥ 0!")
        return EDIT_MAX

async def confirm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'confirm_delete':
        event_id = context.user_data['editing_event']['id']

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('DELETE FROM participants WHERE event_id = ?', (event_id,))
            conn.execute('DELETE FROM events WHERE id = ?', (event_id,))
            conn.commit()

        await query.edit_message_text("🗑 Событие успешно удалено!")
    else:
        await query.edit_message_text("❌ Удаление отменено")

    return ConversationHandler.END

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✖️ Редактирование отменено")
    return ConversationHandler.END
    
    text = f"""
🏷 Название: {event[1]}
📅 Дата: {event[0]}
⏰ Время: {event[3] or 'Не указано'}
📄 Описание: {event[2]}
👥 Макс. участников: {event[4] if event[4] > 0 else 'Без ограничений'}
    """.strip()
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад к событиям", callback_data=f'view_{event[0]}')]
        ])
    )

async def delete_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.split('_')[1]

    context.user_data['deleting_event'] = event_id
    await query.edit_message_text(
        text="❌ Вы уверены что хотите удалить событие?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Да", callback_data='confirm_delete'),
             InlineKeyboardButton("Нет", callback_data='cancel_delete')]
        ])
    )
    return CONFIRM_DELETE

async def send_event_notifications(context: ContextTypes.DEFAULT_TYPE):
    # Получаем часовой пояс из переменной окружения
    timezone_str = TIMEZONE
    timezone = pytz.timezone(timezone_str)
    
    # Используем текущее время с учетом часового пояса
    today = datetime.now(timezone).strftime("%Y-%m-%d")
    
    with sqlite3.connect(DB_NAME) as conn:
        events = conn.execute('''
            SELECT id, name, time
            FROM events
            WHERE date = ?
        ''', (today,)).fetchall()

        for event_id, name, time in events: 
            participants = conn.execute('''
                SELECT user_id FROM participants WHERE event_id = ?
            ''', (event_id,)).fetchall()

            for (user_id,) in participants:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text = f"⏰ Напоминание: сегодня в {time} - {name}" 
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not DatabaseHandler.is_admin(user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ Доступ запрещён!", show_alert=True)
        else:
            await update.message.reply_text("⛔ У вас нет прав доступа к этому меню!")
        return ConversationHandler.END

    admins = DatabaseHandler.get_admins_with_info()
    text = "👑 Список администраторов:\n\n"
    
    for admin in admins:
        user_id, first_name, last_name, username = admin
        name = f"{first_name} {last_name}".strip() or username or f"ID: {user_id}"
        text += f"• {name} (ID: {user_id})\n"

    keyboard = [
        [InlineKeyboardButton("➕ Добавить", callback_data='admin_add'),
         InlineKeyboardButton("➖ Удалить", callback_data='admin_remove')],
        [InlineKeyboardButton("❌ Закрыть", callback_data='admin_close')]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ADMIN_MENU

async def admin_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Получаем список пользователей из базы
    users = DatabaseHandler.get_all_users()
    
    if not users:
        await query.edit_message_text("❌ Нет зарегистрированных пользователей")
        return ADMIN_MENU
    
    # Создаем кнопки с пользователями
    keyboard = []
    temp_row = []
    for user in users:
        user_id, first_name, last_name, username = user
        name = f"{first_name} {last_name}".strip() or username or f"ID: {user_id}"
        btn = InlineKeyboardButton(name, callback_data=f'add_admin_{user_id}')
        
        # Размещаем по 2 кнопки в строке
        if len(temp_row) < 2:
            temp_row.append(btn)
        else:
            keyboard.append(temp_row)
            temp_row = [btn]
    
    if temp_row:
        keyboard.append(temp_row)
    
    # Кнопка возврата
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_back')])
    
    await query.edit_message_text(
        "Выберите пользователя из списка:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADD_ADMIN

async def add_admin_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split('_')[2])
    
    if DatabaseHandler.is_admin(user_id):
        await query.edit_message_text("⚠️ Этот пользователь уже администратор!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 В меню админов", callback_data='admin_back')]
        ]))
        return ADMIN_MENU
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('INSERT INTO admins (user_id) VALUES (?)', (user_id,))
        conn.commit()

    user_info = next((u for u in DatabaseHandler.get_all_users() if u[0] == user_id), None)
    name = f"ID: {user_id}"
    if user_info:
        name = f"{user_info[1]} {user_info[2]}".strip() or user_info[3] or name
    
    await query.edit_message_text(
        f"✅ {name} успешно добавлен в администраторы!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 В меню админов", callback_data='admin_back')]
        ])
    )
    return ADMIN_MENU

async def admin_remove_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    admins = DatabaseHandler.get_admins_with_info()
    keyboard = []
    for admin in admins:
        user_id, first_name, last_name, username = admin
        name = f"{first_name} {last_name}".strip() or username or f"ID: {user_id}"
        keyboard.append([InlineKeyboardButton(f"❌ {name}", callback_data=f'remove_admin_{user_id}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_back')])
    await query.edit_message_text("Выберите администратора для удаления:", 
                                reply_markup=InlineKeyboardMarkup(keyboard))
    return REMOVE_ADMIN

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = int(query.data.split('_')[2])

    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
        conn.commit()
    
    await query.edit_message_text(
        f"✅ Администратор {admin_id} удален!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 В меню админов", callback_data='admin_back')]
        ])
    )
    return ADMIN_MENU

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📖 *Доступные команды:*

/start - Начать работу с ботом
/help - Показать это сообщение
/events - Просмотреть доступные события
/myevents - Показать мои записи
/cancel - Отменить текущее действие

⚙️ *Админ-команды:*
/addevent - Создать новое событие
/admins - Управление администраторами
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')
    
async def my_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    context.user_data['my_events_page'] = 0
    await show_my_events_page(update, context, user_id, 0)

def get_handlers():
    # Обработчик начала работы и получения контакта
    start_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PHONE: [MessageHandler(filters.CONTACT, contact_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Обработчик создания событий
    event_creation_conv = ConversationHandler(
        entry_points=[CommandHandler('addevent', add_event)],
        states={
            DATE: [CallbackQueryHandler(date_received)],
            EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            EVENT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_received)],
            EVENT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, time_received)],
            EVENT_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, max_received)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Обработчик редактирования событий
    edit_event_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pattern=r'^edit_(\d+)$', callback=start_edit_event)],
        states={
            EDIT_CHOICE: [CallbackQueryHandler(edit_choice_handler)],
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name_handler)],
            EDIT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_description_handler)],
            EDIT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_time_handler)],
            EDIT_DATE: [CallbackQueryHandler(edit_date_handler)],
            EDIT_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_max_handler)],
            CONFIRM_DELETE: [CallbackQueryHandler(confirm_delete_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel_edit)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    # Обработчик управления администраторами
    admin_management_conv = ConversationHandler(
        entry_points=[CommandHandler('admins', manage_admins)],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_add_handler, pattern='^admin_add$'),
                CallbackQueryHandler(admin_remove_handler, pattern='^admin_remove$'),
                CallbackQueryHandler(admin_close, pattern='^admin_close$'),
                CallbackQueryHandler(manage_admins, pattern='^admin_back$')
            ],
            ADD_ADMIN: [
                CallbackQueryHandler(add_admin_selected, pattern=r'^add_admin_\d+$'),
                CallbackQueryHandler(manage_admins, pattern='^admin_back$')
            ],
            REMOVE_ADMIN: [
                CallbackQueryHandler(remove_admin, pattern=r'^remove_admin_\d+$'),
                CallbackQueryHandler(manage_admins, pattern='^admin_back$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    return [
        start_conv,
        event_creation_conv,
        edit_event_conv,
        admin_management_conv,
        CommandHandler('events', show_events),
        CommandHandler('help', help_command),
        CommandHandler('myevents', my_events),
        CallbackQueryHandler(button_handler),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    ]

# Добавляем обработчик для обычных текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я не понимаю текстовые сообщения. Используйте команды из меню.")
    return ConversationHandler.END
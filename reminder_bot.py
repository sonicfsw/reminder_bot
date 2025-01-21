import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from apscheduler.schedulers.background import BackgroundScheduler
from pymongo import MongoClient
from datetime import datetime, timedelta, date

API_TOKEN = 'Yor tokken'

client = MongoClient('mongodb://localhost:27017/')
db = client['reminder_bot']
reminders_collection = db['reminders']

bot = telebot.TeleBot(API_TOKEN)
scheduler = BackgroundScheduler()
scheduler.start()

# Хранение данных временно
user_data = {}

# Названия месяцев
MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


# Функция для создания обычных кнопок
def create_reply_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton('Добавить напоминание'),
               telebot.types.KeyboardButton('Список напоминаний'))
    markup.add(telebot.types.KeyboardButton('Удалить напоминание'))
    return markup


# Функция для создания инлайн-кнопок
def create_inline_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Добавить напоминание", callback_data='add_reminder'))
    markup.add(InlineKeyboardButton("Список напоминаний", callback_data='list_reminders'))
    markup.add(InlineKeyboardButton("Удалить напоминание", callback_data='delete_reminder'))
    return markup


# Команда /start
@bot.message_handler(commands=['start'])
def start_message(message: Message):
    if message.chat.type == 'private':  # Личный чат
        bot.send_message(
            message.chat.id,
            "Привет! Я помогу напомнить о важных событиях. Выберите действие:",
            reply_markup=create_reply_keyboard()
        )
    else:  # Групповой чат
        bot.send_message(
            message.chat.id,
            "Привет! Я помогу напомнить о важных событиях. Выберите действие:",
            reply_markup=create_inline_keyboard()
        )


# Генерация календаря
def generate_calendar(year, month):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(f"{MONTH_NAMES[month - 1]} {year}", callback_data='ignore')
    )
    days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    markup.row(*[InlineKeyboardButton(day, callback_data='ignore') for day in days])

    first_day = date(year, month, 1)
    last_day = (first_day.replace(month=month % 12 + 1, day=1) - timedelta(days=1)).day

    for week in range(6):
        row = []
        for day in range(7):
            current_date = week * 7 + day - first_day.weekday() + 1
            if current_date < 1 or current_date > last_day:
                row.append(InlineKeyboardButton(' ', callback_data='ignore'))
            else:
                row.append(
                    InlineKeyboardButton(str(current_date), callback_data=f"calendar:{year}:{month}:{current_date}"))
        markup.row(*row)

    prev_month = month - 1 if month > 1 else 12
    next_month = month + 1 if month < 12 else 1
    prev_year = year - 1 if month == 1 else year
    next_year = year + 1 if month == 12 else year

    markup.row(
        InlineKeyboardButton("<<", callback_data=f"change_month:{prev_year}:{prev_month}"),
        InlineKeyboardButton(">>", callback_data=f"change_month:{next_year}:{next_month}")
    )
    return markup


# Обработка команды "Добавить напоминание" для личных чатов
@bot.message_handler(func=lambda message: message.text == 'Добавить напоминание')
def add_reminder_private(message: Message):
    if message.chat.type == 'private':
        chat_id = message.chat.id
        today = datetime.now()
        bot.send_message(chat_id, "Выберите дату:", reply_markup=generate_calendar(today.year, today.month))


# Обработка инлайн-кнопки "Добавить напоминание" для групп
@bot.callback_query_handler(func=lambda call: call.data == 'add_reminder')
def add_reminder_group(call: CallbackQuery):
    chat_id = call.message.chat.id
    today = datetime.now()
    bot.edit_message_text(
        "Выберите дату:",
        chat_id,
        call.message.message_id,
        reply_markup=generate_calendar(today.year, today.month)
    )


# Обработка выбора даты
@bot.callback_query_handler(func=lambda call: call.data.startswith('calendar:'))
def handle_calendar(call: CallbackQuery):
    _, year, month, day = call.data.split(':')
    selected_date = datetime(int(year), int(month), int(day))
    chat_id = call.message.chat.id

    user_data[chat_id] = {"date": selected_date}
    new_text = f"Вы выбрали дату: {selected_date.strftime('%Y-%m-%d')}\nТеперь введите время в формате чч:мм:"

    bot.edit_message_text(new_text, chat_id, call.message.message_id)
    bot.register_next_step_handler_by_chat_id(chat_id, get_time)


# Переключение месяцев в календаре
@bot.callback_query_handler(func=lambda call: call.data.startswith('change_month:'))
def change_month(call: CallbackQuery):
    _, year, month = call.data.split(':')
    chat_id = call.message.chat.id
    bot.edit_message_reply_markup(chat_id, call.message.message_id,
                                  reply_markup=generate_calendar(int(year), int(month)))


# Получение времени
def get_time(message: Message):
    chat_id = message.chat.id
    try:
        time_str = message.text.strip()
        selected_time = datetime.strptime(time_str, "%H:%M").time()
        user_data[chat_id]["time"] = selected_time
        bot.send_message(chat_id, "Введите текст напоминания (до 500 символов):")
        bot.register_next_step_handler_by_chat_id(chat_id, get_reminder_text)
    except ValueError:
        bot.send_message(chat_id, "Неправильный формат времени! Введите время в формате чч:мм:")
        bot.register_next_step_handler_by_chat_id(chat_id, get_time)


# Получение текста напоминания
def get_reminder_text(message: Message):
    chat_id = message.chat.id
    if len(message.text) > 500:
        bot.send_message(chat_id, "Текст напоминания слишком длинный! Введите текст заново (до 500 символов):")
        bot.register_next_step_handler_by_chat_id(chat_id, get_reminder_text)
        return

    user_data[chat_id]["text"] = message.text
    selected_date = user_data[chat_id]["date"]
    selected_time = user_data[chat_id]["time"]
    selected_datetime = datetime.combine(selected_date, selected_time)

    reminder_dates = [
        selected_datetime - timedelta(days=3),
        selected_datetime - timedelta(days=1),
        selected_datetime
    ]

    reminders_collection.insert_one({
        "chat_id": chat_id,
        "date": selected_date.strftime("%Y-%m-%d"),
        "time": selected_time.strftime("%H:%M"),
        "text": message.text,
        "reminder_dates": [dt.strftime("%Y-%m-%d %H:%M") for dt in reminder_dates]
    })

    for date in reminder_dates:
        if date > datetime.now():
            scheduler.add_job(send_reminder, 'date', run_date=date,
                              args=[chat_id, message.text, date.strftime("%Y-%m-%d %H:%M")])

    bot.send_message(chat_id,
                     f"Напоминание добавлено на {selected_date.strftime('%Y-%m-%d')} {selected_time.strftime('%H:%M')}:\n{message.text}")
    user_data.pop(chat_id, None)


# Функция отправки напоминания
def send_reminder(chat_id, reminder_text, date_time):
    bot.send_message(chat_id, f"Напоминание на {date_time}: {reminder_text}")


# Обработка инлайн-кнопки "Список напоминаний"
@bot.callback_query_handler(func=lambda call: call.data == 'list_reminders')
def list_reminders(call: CallbackQuery):
    chat_id = call.message.chat.id
    reminders = list(reminders_collection.find({"chat_id": chat_id}))

    if not reminders:
        bot.edit_message_text("У вас нет запланированных напоминаний.", chat_id, call.message.message_id)
    else:
        response = "Ваши напоминания:\n"
        for reminder in reminders:
            response += f"- {reminder['date']} {reminder['time']}: {reminder['text']}\n"
        bot.edit_message_text(response, chat_id, call.message.message_id)


# Обработка инлайн-кнопки "Удалить напоминание"
@bot.callback_query_handler(func=lambda call: call.data == 'delete_reminder')
def delete_reminder_prompt(call: CallbackQuery):
    bot.edit_message_text("Введите дату и время напоминания, которое нужно удалить, в формате:\nгггг-мм-дд чч:мм",
                          call.message.chat.id, call.message.message_id)


# Удаление напоминания
@bot.message_handler(func=lambda message: True)
def delete_reminder(message: Message):
    try:
        chat_id = message.chat.id
        date_time = message.text.strip()
        date_str, time_str = date_time.split(' ')

        result = reminders_collection.delete_one({"chat_id": chat_id, "date": date_str, "time": time_str})
        if result.deleted_count > 0:
            bot.send_message(chat_id, f"Напоминание на {date_time} удалено.")
        else:
            bot.send_message(chat_id, "Напоминание с такой датой и временем не найдено.")
    except ValueError:
        bot.send_message(chat_id, "Неправильный формат! Введите в формате: гггг-мм-дд чч:мм.")


# Запуск бота
bot.polling(none_stop=True)

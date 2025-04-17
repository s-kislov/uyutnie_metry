import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union, List, Tuple

import aiohttp
import telebot
from telebot import types
from flask import Flask, request, jsonify, render_template_string, redirect, Response
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Настройки и константы из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
PDF_FILE_ID = os.getenv('PDF_FILE_ID')
BOT_USERNAME = os.getenv('BOT_USERNAME')
GOOGLE_DRIVE_PDF_URL = os.getenv('GOOGLE_DRIVE_PDF_URL')
BONUS_PDF_URL = os.getenv('BONUS_PDF_URL', GOOGLE_DRIVE_PDF_URL)
IMAGE_URL = os.getenv('IMAGE_URL', '')
CHANNEL_POST_TITLE = os.getenv('CHANNEL_POST_TITLE', 'ПОДАРОК ДЛЯ ВАС 🎁')
CHANNEL_POST_DESCRIPTION = os.getenv('CHANNEL_POST_DESCRIPTION',
                                     'Мы подготовили подробный *ЧЕК-ЛИСТ по всем этапам ремонта* — простой и понятный инструмент, который поможет:\n\n✔️ пройти ремонт шаг за шагом\n✔️ избежать типичных ошибок\n✔️ держать всё под контролем')
CHANNEL_POST_CALL = os.getenv('CHANNEL_POST_CALL', '📥 Забирайте чек-лист бесплатно')
CHANNEL_LINK = os.getenv('CHANNEL_LINK', 'https://t.me/uyutnie_metry')
CHANNEL_BUTTON_TEXT = os.getenv('CHANNEL_BUTTON_TEXT', 'ЗАБРАТЬ ПОДАРОК')

# Преобразование описания с звездочками в HTML теги
CHANNEL_POST_DESCRIPTION = (CHANNEL_POST_DESCRIPTION
                            .replace('<br>', '\n')
                            .replace('<br/>', '\n')
                            .replace('<br />', '\n'))
CHANNEL_POST_DESCRIPTION = ''.join(f'<b>{part}</b>' if i % 2 else part
                                   for i, part in enumerate(CHANNEL_POST_DESCRIPTION.split('*')))

# Создаем экземпляр бота
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# Хранилище для отслеживания пользователей
users: Dict[int, Dict[str, Any]] = {}

# Настройки сообщений
CONFIG = {
    'channel_name': CHANNEL_ID.replace('@', ''),
    'channel_username': CHANNEL_ID,

    # Сообщения
    'welcome_message': f'Привет! Подпишитесь на канал {CHANNEL_ID} и нажмите кнопку, чтобы получить чек-лист.',
    'subscription_request': f'Чтобы получить чек-лист подготовки к ремонту, подпишитесь на канал {CHANNEL_ID} и нажмите /check для проверки подписки.',
    'pdf_message': 'Спасибо за подписку на канал! 🎁\n\nВот Ваш чек-лист для подготовки к ремонту:',
    'pdf_message_repeat': 'Вот Ваш чек-лист для подготовки к ремонту:',

    # Кнопки
    'checklist_button_text': 'Получить чек-лист',
}

# Настройка путей к данным
DATA_DIR = os.path.join(os.getcwd(), '.data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')


# Функции для работы с хранилищем пользователей
def save_users() -> None:
    """Сохраняет данные пользователей в файл."""
    try:
        # Создаем директорию, если её нет
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

        # Преобразуем datetime объекты в строки для сериализации
        serializable_users = {}
        for user_id, user_data in users.items():
            serializable_user = user_data.copy()
            if 'last_activity' in serializable_user and isinstance(serializable_user['last_activity'], datetime):
                serializable_user['last_activity'] = serializable_user['last_activity'].isoformat()
            if 'last_checked' in serializable_user and isinstance(serializable_user['last_checked'], datetime):
                serializable_user['last_checked'] = serializable_user['last_checked'].isoformat()
            serializable_users[str(user_id)] = serializable_user

        # Сохраняем данные пользователей в файл
        with open(USERS_FILE, 'w', encoding='utf-8') as file:
            json.dump(serializable_users, file, ensure_ascii=False, indent=2)

        logger.info(f'Данные пользователей сохранены, всего: {len(users)}')
    except Exception as e:
        logger.error(f'Ошибка сохранения данных пользователей: {e}')


def load_users() -> None:
    """Загружает данные пользователей из файла."""
    global users
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as file:
                loaded_users = json.load(file)

            # Преобразуем строковые ключи обратно в целые числа и обрабатываем даты
            for user_id_str, user_data in loaded_users.items():
                user_id = int(user_id_str)
                if 'last_activity' in user_data and isinstance(user_data['last_activity'], str):
                    try:
                        user_data['last_activity'] = datetime.fromisoformat(user_data['last_activity'])
                    except ValueError:
                        user_data['last_activity'] = datetime.now()
                if 'last_checked' in user_data and isinstance(user_data['last_checked'], str):
                    try:
                        user_data['last_checked'] = datetime.fromisoformat(user_data['last_checked'])
                    except ValueError:
                        user_data['last_checked'] = datetime.now()
                users[user_id] = user_data

            logger.info(f'Загружены данные {len(users)} пользователей')
        else:
            logger.info('Файл с данными пользователей не найден, создаем новый')
    except Exception as e:
        logger.error(f'Ошибка загрузки данных пользователей: {e}')


# Функция для отправки приветствия с кнопкой
def send_welcome_with_button(chat_id: int) -> None:
    """Отправляет приветственное сообщение с кнопкой для получения чек-листа."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton(CONFIG['checklist_button_text']))

    bot.send_message(chat_id, CONFIG['welcome_message'], reply_markup=keyboard)


# Функция отправки запроса на подписку
def send_subscription_request(chat_id: int) -> None:
    """Отправляет запрос на подписку на канал."""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="Перейти в канал",
        url=f"https://t.me/{CONFIG['channel_username'].replace('@', '')}"
    ))

    bot.send_message(chat_id, CONFIG['subscription_request'], reply_markup=keyboard)


# Улучшенная функция проверки подписки на канал
async def check_subscription(user_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.

    Args:
        user_id: ID пользователя для проверки

    Returns:
        bool: True если пользователь подписан, иначе False
    """
    # Максимальное количество попыток проверки
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            # Небольшая задержка перед запросом для надежности
            await asyncio.sleep(0.5)

            # Проверка подписки через API бота
            chat_member = bot.get_chat_member(CHANNEL_ID, user_id)
            status = chat_member.status

            # Проверяем статус подписки
            # Только member, administrator и creator считаются подписанными
            is_subscribed = status in ['member', 'administrator', 'creator']

            logger.info(f'Попытка {attempt + 1}: Статус подписки пользователя {user_id}: {status} ({is_subscribed})')

            # Если пользователь подписан, обновляем статус и возвращаем результат
            if is_subscribed:
                # Обновляем статус в хранилище
                if user_id in users:
                    users[user_id]['is_subscribed'] = True
                    users[user_id]['last_checked'] = datetime.now()
                return True

            # Если не подписан и это не последняя попытка, ждем немного
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f'Ошибка при проверке подписки (попытка {attempt + 1}): {e}')
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)

    # Если после всех попыток пользователь не подписан
    if user_id in users:
        users[user_id]['is_subscribed'] = False
        users[user_id]['last_checked'] = datetime.now()

    return False


# Синхронная обертка для асинхронной функции проверки подписки
def check_subscription_sync(user_id: int) -> bool:
    """Синхронная обертка для проверки подписки."""
    import asyncio

    try:
        # Создаем новый цикл событий
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Выполняем асинхронную функцию в цикле событий
        result = loop.run_until_complete(check_subscription(user_id))

        # Закрываем цикл событий
        loop.close()

        return result
    except Exception as e:
        logger.error(f'Ошибка в синхронной обертке проверки подписки: {e}')
        return False


# Функция для отправки PDF документа
async def send_pdf_document(chat_id: int, user_id: int) -> bool:
    """
    Отправляет PDF документ пользователю.

    Args:
        chat_id: ID чата для отправки документа
        user_id: ID пользователя

    Returns:
        bool: True если документ был успешно отправлен, иначе False
    """
    try:
        # Проверяем, отправляли ли уже PDF этому пользователю
        already_sent = users.get(user_id, {}).get('pdf_sent', False)

        # Отмечаем, что PDF был отправлен
        if user_id in users:
            users[user_id]['pdf_sent'] = True

        # Отправляем разные сообщения для первой и повторной отправки
        message_text = CONFIG['pdf_message_repeat'] if already_sent else CONFIG['pdf_message']

        # Отправляем сообщение перед PDF
        bot.send_message(chat_id, message_text)

        try:
            # Скачиваем PDF с указанного URL
            logger.info(f'Отправка PDF пользователю {user_id}')

            # Имя файла для отправки
            file_name = 'Чек-лист.pdf'

            # Скачиваем файл с увеличенным таймаутом
            async with aiohttp.ClientSession() as session:
                async with session.get(BONUS_PDF_URL, timeout=30) as response:
                    if response.status != 200:
                        raise Exception(f"Ошибка при скачивании PDF: статус {response.status}")

                    # Читаем файл в байтовый объект
                    file_content = await response.read()

                    # Проверяем, что файл не пустой
                    if len(file_content) <= 0:
                        raise Exception("Получен пустой файл")

                    # Проверяем заголовок файла PDF (байты %PDF)
                    if len(file_content) >= 4 and not (
                            file_content[0] == 0x25 and  # %
                            file_content[1] == 0x50 and  # P
                            file_content[2] == 0x44 and  # D
                            file_content[3] == 0x46):  # F
                        logger.warning('Полученный файл может быть не PDF форматом')

                    # Отправляем файл напрямую как документ
                    bot.send_document(
                        chat_id,
                        (file_name, file_content),
                        caption='Чек-лист подготовки к ремонту'
                    )

            logger.info(f'PDF успешно отправлен пользователю {user_id}')
            return True

        except Exception as error:
            logger.error(f'Ошибка при отправке PDF как документа: {error}')

            try:
                # Вторая попытка - отправка файла по URL
                logger.info('Повторная попытка отправки PDF по URL...')

                # Отправляем файл по url
                bot.send_document(
                    chat_id,
                    BONUS_PDF_URL,
                    caption='Чек-лист подготовки к ремонту'
                )

                logger.info(f'PDF успешно отправлен по URL пользователю {user_id}')
                return True

            except Exception as second_error:
                logger.error(f'Ошибка второй попытки отправки PDF: {second_error}')

                # Если все попытки отправки файла не удались, отправляем ссылку
                bot.send_message(
                    chat_id,
                    f'К сожалению, не удалось отправить документ. Скачайте PDF по ссылке: {BONUS_PDF_URL}'
                )

                return False

    except Exception as error:
        logger.error(f'Критическая ошибка при отправке PDF: {error}')

        # Отправляем ссылку в случае ошибки
        bot.send_message(
            chat_id,
            f'Произошла ошибка при отправке PDF. Скачайте его по ссылке: {BONUS_PDF_URL}'
        )

        return False


# Синхронная обертка для асинхронной функции отправки PDF
def send_pdf_document_sync(chat_id: int, user_id: int) -> bool:
    """Синхронная обертка для отправки PDF документа."""
    import asyncio

    try:
        # Создаем новый цикл событий
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Выполняем асинхронную функцию в цикле событий
        result = loop.run_until_complete(send_pdf_document(chat_id, user_id))

        # Закрываем цикл событий
        loop.close()

        return result
    except Exception as e:
        logger.error(f'Ошибка в синхронной обертке отправки PDF: {e}')
        return False


# Функция для проверки подписки и отправки PDF
def check_and_send_pdf(chat_id: int, user_id: int) -> bool:
    """
    Проверяет подписку и отправляет PDF, если пользователь подписан.

    Args:
        chat_id: ID чата для отправки сообщений
        user_id: ID пользователя для проверки

    Returns:
        bool: True если PDF был отправлен, иначе False
    """
    # Проверяем подписку
    is_subscribed = check_subscription_sync(user_id)

    if is_subscribed:
        # Если подписан, отправляем PDF
        return send_pdf_document_sync(chat_id, user_id)
    else:
        # Если не подписан, отправляем запрос на подписку
        send_subscription_request(chat_id)
        return False


# Функция для публикации поста в канал
async def publish_post_to_channel() -> str:
    """
    Публикует пост в канал с изображением и кнопкой.

    Returns:
        str: Сообщение о статусе публикации
    """
    try:
        # Проверяем наличие тегов <b> и убеждаемся, что они корректно парные
        clean_description = CHANNEL_POST_DESCRIPTION

        # Подсчитываем количество открывающих и закрывающих тегов
        open_tags = clean_description.count('<b>')
        close_tags = clean_description.count('</b>')

        # Если количество не совпадает, используем более безопасный метод
        if open_tags != close_tags:
            logger.warning(f'Неравное количество тегов <b> ({open_tags}) и </b> ({close_tags}). Переформатируем.')
            # Удаляем все существующие теги <b> и заново применяем форматирование
            clean_description = clean_description.replace('<b>', '').replace('</b>', '')
            clean_description = ''.join(f'<b>{part}</b>' if i % 2 else part
                                        for i, part in enumerate(clean_description.split('*')))

        # Формируем финальный текст поста
        post_text = f"<b>{CHANNEL_POST_TITLE}</b>\n\n{clean_description}\n\n<b>{CHANNEL_POST_CALL}</b>\n\nСоздавайте уютный и функциональный дом \nвместе с <a href=\"{CHANNEL_LINK}\">Уютные метры</a>🏡"

        # Для отладки - выводим финальный текст в консоль
        logger.info('Финальный текст поста:')
        logger.info(post_text)

        # Кнопка для поста
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            text=CHANNEL_BUTTON_TEXT,
            url=f"https://t.me/{BOT_USERNAME}?start=checklist"
        ))

        # Проверяем, есть ли URL изображения
        if IMAGE_URL:
            # Отправляем фото с подписью и кнопкой
            bot.send_photo(
                CHANNEL_ID,
                IMAGE_URL,
                caption=post_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )

            logger.info("Пост с изображением успешно опубликован в канале!")
            return "Пост с изображением успешно опубликован!"
        else:
            # Отправляем только текст с кнопкой
            bot.send_message(
                CHANNEL_ID,
                post_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )

            logger.info("Текстовый пост успешно опубликован в канале!")
            return "Текстовый пост успешно опубликован!"

    except Exception as error:
        error_msg = f'Ошибка публикации поста: {error}'
        logger.error(error_msg)
        raise Exception(error_msg)


# Синхронная обертка для публикации поста
def publish_post_to_channel_sync() -> str:
    """Синхронная обертка для публикации поста в канал."""
    import asyncio

    try:
        # Создаем новый цикл событий
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Выполняем асинхронную функцию в цикле событий
        result = loop.run_until_complete(publish_post_to_channel())

        # Закрываем цикл событий
        loop.close()

        return result
    except Exception as e:
        logger.error(f'Ошибка в синхронной обертке публикации поста: {e}')
        return f"Ошибка публикации поста: {e}"


# Функция для HTML-форматирования
def html_to_editable(text: str) -> str:
    """Преобразует HTML-теги в звездочки для редактирования."""
    if not text:
        return ''

    # Заменяем <b> теги на звездочки
    text = text.replace('<b>', '*').replace('</b>', '*')

    # Заменяем разные виды <br> на переносы строк
    text = text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')

    return text


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Сохраняем информацию о пользователе
    if user_id not in users:
        users[user_id] = {
            'user_id': user_id,
            'username': message.from_user.username or '',
            'welcome_sent': False,
            'pdf_sent': False,
            'is_subscribed': False,
            'last_activity': datetime.now()
        }

    # Обновляем активность пользователя
    users[user_id]['last_activity'] = datetime.now()

    # Отправляем приветствие с клавиатурой
    send_welcome_with_button(chat_id)

    # Проверяем подписку и отправляем PDF, если пользователь подписан
    check_and_send_pdf(chat_id, user_id)

    # Отмечаем, что приветствие отправлено
    users[user_id]['welcome_sent'] = True

    logger.info(f'Пользователь {user_id} запустил бота')


# Обработчик команды /check
@bot.message_handler(commands=['check'])
def handle_check(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    logger.info(f'Пользователь {user_id} запросил проверку подписки')

    # Отправляем сообщение о проверке
    status_msg = bot.send_message(chat_id, "Проверяем вашу подписку...")

    try:
        # Проверяем подписку
        is_subscribed = check_subscription_sync(user_id)

        if is_subscribed:
            # Удаляем сообщение о проверке
            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass

            # Отправляем PDF подписчику
            send_pdf_document_sync(chat_id, user_id)
        else:
            # Обновляем сообщение о проверке
            try:
                bot.edit_message_text(
                    "К сожалению, вы еще не подписаны на канал.",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
            except Exception:
                pass

            # Отправляем запрос на подписку с небольшой задержкой
            time.sleep(1)
            send_subscription_request(chat_id)

    except Exception as error:
        logger.error(f'Ошибка при обработке команды /check: {error}')

        # В случае ошибки сообщаем пользователю
        try:
            bot.edit_message_text(
                "Произошла ошибка при проверке подписки. Пожалуйста, попробуйте позже.",
                chat_id=chat_id,
                message_id=status_msg.message_id
            )
        except Exception:
            pass


# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    if not message.text:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text

    logger.info(f'Получено сообщение от {user_id}: {text}')

    # Обновляем активность пользователя
    if user_id in users:
        users[user_id]['last_activity'] = datetime.now()

    # Если текст совпадает с текстом кнопки получения чек-листа
    if text == CONFIG['checklist_button_text']:
        check_and_send_pdf(chat_id, user_id)
    else:
        # Для других сообщений отправляем напоминание
        if user_id in users and users[user_id].get('welcome_sent'):
            bot.send_message(
                chat_id,
                f"Чтобы получить чек-лист, нажмите кнопку \"{CONFIG['checklist_button_text']}\" или отправьте /check для проверки подписки."
            )
        else:
            # Если пользователь новый, отправляем приветствие
            send_welcome_with_button(chat_id)

            if user_id in users:
                users[user_id]['welcome_sent'] = True
            else:
                users[user_id] = {
                    'user_id': user_id,
                    'username': message.from_user.username or '',
                    'welcome_sent': True,
                    'pdf_sent': False,
                    'is_subscribed': False,
                    'last_activity': datetime.now()
                }


# Создаем Flask-приложение для веб-интерфейса
app = Flask(__name__)


# Функция генерации CSV со списком пользователей
def generate_users_csv() -> str:
    """Генерирует CSV-файл со списком пользователей."""
    csv_content = 'ID,Username,Subscription Status,PDF Sent,Last Activity\n'

    for user_id, user_data in users.items():
        is_subscribed = 'Subscribed' if user_data.get('is_subscribed', False) else 'Not Subscribed'
        pdf_sent = 'Yes' if user_data.get('pdf_sent', False) else 'No'
        username = user_data.get('username', 'no_username')
        last_activity = user_data.get('last_activity', datetime.now())

        if isinstance(last_activity, datetime):
            last_activity = last_activity.isoformat()

        csv_content += f"{user_id},{username},{is_subscribed},{pdf_sent},{last_activity}\n"

    return csv_content


# Административная панель
@app.route('/admin')
def admin_panel():
    user_count = len(users)
    subscribed_users = sum(1 for user in users.values() if user.get('is_subscribed', False))
    pdf_sent_count = sum(1 for user in users.values() if user.get('pdf_sent', False))

    # Подготавливаем текст описания для редактирования
    editable_description = html_to_editable(CHANNEL_POST_DESCRIPTION)

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Панель управления ботом</title>
      <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1, h2 { color: #2c3e50; }
        .card { background: #f9f9f9; border-radius: 5px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stats { display: flex; justify-content: space-between; flex-wrap: wrap; }
        .stat-card { background: #fff; border-left: 4px solid #3498db; padding: 10px; width: 30%; margin-bottom: 15px; }
        button, .button { background: #3498db; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; }
        button:hover, .button:hover { background: #2980b9; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        table, th, td { border: 1px solid #ddd; }
        th, td { padding: 12px; text-align: left; }
        th { background-color: #f2f2f2; }
        form { margin-bottom: 20px; }
        input, textarea { width: 100%; padding: 8px; margin: 8px 0; box-sizing: border-box; }
        .help-text { color: #666; font-style: italic; margin: 5px 0; font-size: 0.9em; }
      </style>
    </head>
    <body>
      <h1>Панель управления Telegram-ботом</h1>
      
      <div class="card">
        <h2>Статистика</h2>
        <div class="stats">
          <div class="stat-card">
            <h3>Всего пользователей</h3>
            <p>{{ user_count }}</p>
          </div>
          <div class="stat-card">
            <h3>Подписчиков канала</h3>
            <p>{{ subscribed_users }}</p>
          </div>
          <div class="stat-card">
            <h3>Отправлено PDF</h3>
            <p>{{ pdf_sent_count }}</p>
          </div>
        </div>
      </div>
      
      <div class="card">
        <h2>Настройки PDF и бонусных файлов</h2>
        <form action="/update-pdf-settings" method="post">
          <label for="bonusPdfUrl">URL бонусного PDF-файла (отправляется подписчикам):</label>
          <input type="text" id="bonusPdfUrl" name="bonusPdfUrl" value="{{ bonus_pdf_url }}">
          
          <button type="submit">Обновить настройки PDF</button>
        </form>
      </div>
      
      <div class="card">
        <h2>Публикация в канал</h2>
        <form action="/publish-post" method="post">
          <label for="title">Заголовок:</label>
          <input type="text" id="title" name="title" value="{{ channel_post_title }}">
          
          <label for="description">Описание:</label>
          <p class="help-text">Используйте *звездочки* для выделения текста жирным шрифтом</p>
          <textarea id="description" name="description" rows="5">{{ editable_description }}</textarea>
          
          <label for="call">Призыв к действию:</label>
          <input type="text" id="call" name="call" value="{{ channel_post_call }}">
          
          <label for="buttonText">Текст кнопки:</label>
          <input type="text" id="buttonText" name="buttonText" value="{{ channel_button_text }}">
          
          <label for="imageUrl">URL изображения (оставьте пустым для текстового поста):</label>
          <input type="text" id="imageUrl" name="imageUrl" value="{{ image_url }}">
          
          <button type="submit">Опубликовать пост</button>
        </form>
      </div>
      
      <div class="card">
        <h2>Действия</h2>
        <p><a href="/save-users" class="button">Сохранить данные пользователей</a></p>
        <p><a href="/test-bot" class="button">Проверить работу бота</a></p>
        <p><a href="/test-pdf" class="button">Проверить отправку PDF</a></p>
        <p><a href="/clear-users" class="button" onclick="return confirm('Вы уверены, что хотите удалить всех пользователей?')">Очистить данные пользователей</a></p>
      </div>
      <div class="card">
        <h2>Экспорт данных</h2>
        <p><a href="/export-users" class="button" download>Скачать список пользователей (CSV)</a></p>
        <p><a href="/export-users-json" class="button" download>Скачать детальный список пользователей (JSON)</a></p>
      </div>
    </body>
    </html>
    """

    return render_template_string(
        html_template,
        user_count=user_count,
        subscribed_users=subscribed_users,
        pdf_sent_count=pdf_sent_count,
        bonus_pdf_url=BONUS_PDF_URL,
        channel_post_title=CHANNEL_POST_TITLE,
        editable_description=editable_description,
        channel_post_call=CHANNEL_POST_CALL,
        channel_button_text=CHANNEL_BUTTON_TEXT,
        image_url=IMAGE_URL or ''
    )

# Маршрут для экспорта пользователей в CSV
@app.route('/export-users')
def export_users():
    csv_content = generate_users_csv()

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=users.csv'}
    )

# Маршрут для экспорта пользователей в JSON
@app.route('/export-users-json')
def export_users_json():
    # Преобразуем datetime объекты для JSON-сериализации
    serializable_users = {}
    for user_id, user_data in users.items():
        serializable_user = user_data.copy()
        if 'last_activity' in serializable_user and isinstance(serializable_user['last_activity'], datetime):
            serializable_user['last_activity'] = serializable_user['last_activity'].isoformat()
        if 'last_checked' in serializable_user and isinstance(serializable_user['last_checked'], datetime):
            serializable_user['last_checked'] = serializable_user['last_checked'].isoformat()
        serializable_users[str(user_id)] = serializable_user

    return Response(
        json.dumps(serializable_users, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=users.json'}
    )

# Маршрут для обновления настроек PDF
@app.route('/update-pdf-settings', methods=['POST'])
def update_pdf_settings():
    global BONUS_PDF_URL

    try:
        bonus_pdf_url = request.form.get('bonusPdfUrl')

        # Обновляем URL бонусного PDF
        BONUS_PDF_URL = bonus_pdf_url

        html_response = """
        <h1>Настройки PDF успешно обновлены!</h1>
        <p>Новый URL бонусного PDF: {}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_response.format(bonus_pdf_url)
    except Exception as e:
        html_error = """
        <h1>Ошибка обновления настроек PDF</h1>
        <p>{}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_error.format(str(e)), 500

# Маршрут для публикации поста
@app.route('/publish-post', methods=['POST'])
def publish_post():
    global CHANNEL_POST_TITLE, CHANNEL_POST_DESCRIPTION, CHANNEL_POST_CALL, CHANNEL_BUTTON_TEXT, IMAGE_URL

    try:
        title = request.form.get('title')
        description = request.form.get('description')
        call = request.form.get('call')
        button_text = request.form.get('buttonText')
        image_url = request.form.get('imageUrl')

        # Обновляем глобальные переменные
        CHANNEL_POST_TITLE = title

        # Форматируем описание
        formatted_description = description.replace('\r\n', '\n').replace('\n{3,}', '\n\n').strip()
        CHANNEL_POST_DESCRIPTION = ''.join(f'<b>{part}</b>' if i % 2 else part
                                         for i, part in enumerate(formatted_description.split('*')))

        CHANNEL_POST_CALL = call
        CHANNEL_BUTTON_TEXT = button_text
        IMAGE_URL = image_url

        # Публикуем пост
        result = publish_post_to_channel_sync()

        html_response = """
        <h1>Пост успешно опубликован!</h1>
        <p>{}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_response.format(result)
    except Exception as e:
        logger.error(f"Ошибка при публикации поста: {e}")

        html_error = """
        <h1>Ошибка публикации поста</h1>
        <p>{}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_error.format(str(e)), 500

# Маршрут для сохранения пользователей
@app.route('/save-users')
def save_users_route():
    save_users()

    html_response = """
    <h1>Данные пользователей сохранены</h1>
    <p><a href="/admin">Вернуться в панель управления</a></p>
    """

    return html_response

# Маршрут для проверки бота
@app.route('/test-bot')
def test_bot():
    try:
        me = bot.get_me()

        html_response = """
        <h1>Бот работает корректно</h1>
        <p>Имя бота: {}</p>
        <p>Имя пользователя: @{}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_response.format(me.first_name, me.username)
    except Exception as e:
        html_error = """
        <h1>Ошибка проверки бота</h1>
        <p>{}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_error.format(str(e)), 500

# Маршрут для проверки PDF
@app.route('/test-pdf')
def test_pdf():
    try:
        import aiohttp
        import asyncio

        async def check_pdf():
            async with aiohttp.ClientSession() as session:
                async with session.get(BONUS_PDF_URL, timeout=30) as response:
                    status = response.status
                    content_type = response.headers.get('Content-Type', '')

                    file_content = await response.read()
                    file_size = len(file_content)

                    is_pdf = (
                        file_size >= 4 and
                        file_content[0] == 0x25 and  # %
                        file_content[1] == 0x50 and  # P
                        file_content[2] == 0x44 and  # D
                        file_content[3] == 0x46      # F
                    )

                    first_20_bytes = ''.join(f'{b:02x}' for b in file_content[:20])

                    return {
                        'status': status,
                        'content_type': content_type,
                        'file_size': file_size,
                        'is_pdf': is_pdf,
                        'first_20_bytes': first_20_bytes
                    }

        # Запускаем асинхронную функцию
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(check_pdf())
        loop.close()

        html_response = """
        <h1>Результат проверки PDF-файла</h1>
        <p>URL: {url}</p>
        <p>HTTP статус: {status}</p>
        <p>Content-Type: {content_type}</p>
        <p>Размер файла: {size} КБ</p>
        <p>Формат PDF: {is_pdf}</p>
        <p>Первые 20 байт: {bytes}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_response.format(
            url=BONUS_PDF_URL,
            status=result['status'],
            content_type=result['content_type'],
            size=round(result['file_size'] / 1024, 2),
            is_pdf='Да' if result['is_pdf'] else 'Нет',
            bytes=result['first_20_bytes']
        )
    except Exception as e:
        html_error = """
        <h1>Ошибка проверки PDF-файла</h1>
        <p>URL: {url}</p>
        <p>Ошибка: {error}</p>
        <p><a href="/admin">Вернуться в панель управления</a></p>
        """

        return html_error.format(url=BONUS_PDF_URL, error=str(e)), 500

# Маршрут для очистки данных пользователей
@app.route('/clear-users')
def clear_users():
    # Очищаем данные пользователей
    users.clear()
    save_users()

    html_response = """
    <h1>Данные пользователей очищены</h1>
    <p><a href="/admin">Вернуться в панель управления</a></p>
    """

    return html_response

# Маршрут для ручной публикации поста
@app.route('/publish-post-manually')
def publish_post_manually():
    try:
        result = publish_post_to_channel_sync()
        return result
    except Exception as e:
        return f'Ошибка публикации поста: {e}', 500

# Редирект с корневого URL на админ-панель для удобства
@app.route('/')
def root():
    return redirect('/admin')

# Маршрут для мониторинга
@app.route('/ping')
def ping():
    return 'OK', 200

# Функция периодического сохранения данных пользователей
def periodic_save():
    while True:
        time.sleep(60)  # Сохранение каждую минуту
        try:
            save_users()
        except Exception as e:
            logger.error(f'Ошибка при периодическом сохранении данных: {e}')

# Основная функция запуска приложения
def main():
    import threading
    import asyncio

    # Загружаем данные пользователей при запуске
    load_users()

    # Запускаем поток для периодического сохранения данных
    save_thread = threading.Thread(target=periodic_save, daemon=True)
    save_thread.start()

    # Порт для веб-приложения
    port = int(os.environ.get('PORT', 8080))

    # Запускаем flask-приложение в отдельном потоке
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()

    logger.info(f'Сервер запущен на порту {port}')
    logger.info('Бот запущен!')

    # Запускаем бота (этот вызов блокирующий)
    bot.polling(none_stop=True, interval=1)

if __name__ == '__main__':
    # Импортируем asyncio только здесь для совместимости
    import asyncio
    main()
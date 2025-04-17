# Telegram Чек-лист Бот

Telegram-бот для раздачи PDF чек-листов подписчикам канала. Бот проверяет подписку пользователя на указанный канал и отправляет PDF-файл подписчикам.

## Особенности

- Проверка подписки на канал
- Отправка PDF-файлов подписчикам
- Отслеживание пользователей и их активности
- Административная панель для управления ботом
- Экспорт данных пользователей
- Публикация постов в канал
- Настройка PDF и бонусных материалов

## Установка

1. Клонируйте репозиторий
   ```
   git clone https://github.com/yourusername/telegram-checklist-bot.git
   cd telegram-checklist-bot
   ```

2. Создайте и активируйте виртуальное окружение
   ```
   python -m venv venv
   source venv/bin/activate  # Для Linux/Mac
   # или
   venv\Scripts\activate  # Для Windows
   ```

3. Установите зависимости
   ```
   pip install -r requirements.txt
   ```

4. Создайте файл `.env` со следующими переменными:
   ```
   BOT_TOKEN=your_telegram_bot_token
   CHANNEL_ID=@your_channel_id
   PDF_FILE_ID=your_pdf_file_id
   BOT_USERNAME=your_bot_username
   GOOGLE_DRIVE_PDF_URL=url_to_your_pdf_file
   BONUS_PDF_URL=url_to_your_bonus_pdf_file
   IMAGE_URL=url_to_image_for_channel_post
   CHANNEL_POST_TITLE=ПОДАРОК ДЛЯ ВАС 🎁
   CHANNEL_POST_DESCRIPTION=Описание поста
   CHANNEL_POST_CALL=Призыв к действию
   CHANNEL_LINK=https://t.me/your_channel
   CHANNEL_BUTTON_TEXT=ЗАБРАТЬ ПОДАРОК
   ```

## Запуск

```
python main.py
```

Веб-интерфейс будет доступен по адресу http://localhost:8080/admin

## Развертывание на сервере

1. Настройте сервер с Python 3.12
2. Клонируйте репозиторий 
3. Установите зависимости
4. Настройте supervisor или systemd для запуска бота как службы

Пример конфигурации для systemd (`/etc/systemd/system/telegram-bot.service`):

```
[Unit]
Description=Telegram Checklist Bot
After=network.target

[Service]
User=yourusername
WorkingDirectory=/path/to/telegram-checklist-bot
ExecStart=/path/to/telegram-checklist-bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активация службы:
```
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

## Административная панель

После запуска перейдите по адресу `http://your-server-ip:8080/admin` для доступа к административной панели.

Функции административной панели:
- Просмотр статистики пользователей
- Обновление URL PDF-файла
- Публикация постов в канал
- Экспорт данных пользователей
- Тестирование работы бота и проверка PDF

## Команды бота

- `/start` - начало работы с ботом
- `/check` - проверка подписки на канал

## Контакты

Для вопросов и предложений, пожалуйста, свяжитесь с @yourusername в Telegram.
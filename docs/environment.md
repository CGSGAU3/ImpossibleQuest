## Запуск Telegram-бота

Бот берет параметры из переменных окружения. Файл `.env` сам не загружается.

| Переменная | Для чего нужна | По умолчанию |
| --- | --- | --- |
| `BOT_TOKEN` | Токен тестового бота | Нужен для `--serve` |
| `TRANSPORT` | `webhook` или `polling` | `webhook` |
| `WEBHOOK_BASE_URL` | Публичный HTTPS-адрес без query и fragment | Нужен для webhook |
| `WEBHOOK_SECRET` | Секрет webhook, от 1 до 256 символов `A-Z a-z 0-9 _ -` | Нужен для webhook |
| `BIND_HOST` | Адрес, на котором слушает приложение | `127.0.0.1` |
| `PORT` | Порт приложения | `8080` |
| `DATABASE_URL` | URL базы SQLite | `sqlite+aiosqlite:///quest.db` |
| `QUEST_PATH` | Путь к другой карте JSON | Карта из пакета |
| `RULES_PATH` | Путь к JSON с настройками механик | Значения из `Rules` |
| `LOG_PATH` | Файл журнала | `quest.log` |
| `LOG_LEVEL` | Уровень сообщений квеста, например `DEBUG` | `INFO` |
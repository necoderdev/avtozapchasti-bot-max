# MAX Auto Parts Delivery Bot

[Русский](#русский) · [English](#english)

---

## Русский

Чат-бот для оформления доставки автозапчастей через мессенджер MAX. Бот последовательно запрашивает VIN автомобиля, название запчасти, адрес доставки и номер телефона, после чего показывает заявку для подтверждения и отправляет её администраторам.

### Возможности

- адаптивные inline-кнопки вместо текстовых команд;
- проверка формата VIN и номера телефона;
- подтверждение и отмена заявки;
- защита от повторного подтверждения и использования устаревших кнопок;
- отправка заявки одному или нескольким администраторам;
- ответы администратора клиенту от имени бота;
- автоматическое удаление незавершённых заявок через час;
- ограничение частоты обращений к MAX API;
- безопасное TLS-подключение с сертификатом Минцифры;
- поддержка Railway, Docker и локального запуска.

### Требования

- Python 3.13 или новее;
- созданный и настроенный бот в MAX;
- токен MAX Bot API;
- ID хотя бы одного администратора.

### Локальная установка

1. Клонируйте репозиторий и перейдите в его каталог.
2. Создайте локальный файл окружения:

```powershell
Copy-Item .env.example .env
```

3. Заполните `.env`:

```dotenv
BOT_TOKEN=новый_токен_вашего_бота
ADMIN_IDS=123456789
LOG_LEVEL=INFO
```

Несколько ID администраторов можно разделить запятыми:

```dotenv
ADMIN_IDS=123456789,987654321
```

4. Установите зависимости и запустите бота:

```powershell
python -m pip install -r requirements.txt
python max_bot.py
```

### Запуск через Docker

```bash
docker build -t max-auto-parts-bot .
docker run --env-file .env --restart unless-stopped max-auto-parts-bot
```

Контейнер запускается от непривилегированного пользователя.

### Развёртывание на Railway

1. Подключите GitHub-репозиторий к Railway.
2. Добавьте в разделе **Variables** переменные `BOT_TOKEN`, `ADMIN_IDS` и при необходимости `LOG_LEVEL`.
3. Разверните сервис. Команда запуска и политика перезапуска уже находятся в `railway.json`.
4. Установите одну реплику сервиса.

Не запускайте локальную и серверную копии одновременно с одним токеном: экземпляры Long Polling будут конкурировать за обновления.

### Проверка

```powershell
python -m unittest discover -s tests -v
python -m pip check
```

### Безопасность

- Никогда не добавляйте `.env` в Git и не записывайте токен в код, Dockerfile или логи.
- Настоящий `.env` уже исключён через `.gitignore` и `.dockerignore`.
- Перед первой публикацией перевыпустите любой токен, который ранее находился в исходном коде.
- Храните секреты в Railway Variables или в менеджере секретов вашего сервера.
- Включите в GitHub функции Secret Scanning и Push Protection.
- Не публикуйте логи с VIN, адресами и телефонами клиентов.

Дополнительные рекомендации находятся в [SECURITY.md](SECURITY.md).

### Ограничения

Сейчас бот получает события через Long Polling. Для небольшой нагрузки достаточно одного постоянно работающего процесса, однако MAX рекомендует использовать Webhook в production. Для Webhook потребуется публичный HTTPS-адрес и отдельный секрет.

---

## English

A chatbot for arranging auto-parts delivery through the MAX messenger. The bot collects the vehicle VIN, required part, delivery address, and phone number, displays the completed request for confirmation, and forwards it to the configured administrators.

### Features

- responsive inline buttons instead of text commands;
- VIN and phone number validation;
- order confirmation and cancellation;
- protection against duplicate confirmations and stale buttons;
- delivery of requests to one or more administrators;
- administrator replies to customers on behalf of the bot;
- automatic removal of incomplete requests after one hour;
- MAX API request-rate limiting;
- secure TLS connection with the required Ministry of Digital Development certificate;
- Railway, Docker, and local deployment support.

### Requirements

- Python 3.13 or newer;
- a configured MAX bot;
- a MAX Bot API token;
- at least one administrator ID.

### Local installation

1. Clone the repository and open its directory.
2. Create a local environment file:

```powershell
Copy-Item .env.example .env
```

3. Configure `.env`:

```dotenv
BOT_TOKEN=your_new_bot_token
ADMIN_IDS=123456789
LOG_LEVEL=INFO
```

Multiple administrator IDs can be separated with commas:

```dotenv
ADMIN_IDS=123456789,987654321
```

4. Install the dependencies and start the bot:

```powershell
python -m pip install -r requirements.txt
python max_bot.py
```

### Running with Docker

```bash
docker build -t max-auto-parts-bot .
docker run --env-file .env --restart unless-stopped max-auto-parts-bot
```

The container runs as a non-root user.

### Deploying to Railway

1. Connect the GitHub repository to Railway.
2. Add `BOT_TOKEN`, `ADMIN_IDS`, and optionally `LOG_LEVEL` under **Variables**.
3. Deploy the service. The start command and restart policy are already defined in `railway.json`.
4. Keep the service at one replica.

Do not run local and remote instances with the same token at the same time. Multiple Long Polling instances will compete for updates.

### Verification

```powershell
python -m unittest discover -s tests -v
python -m pip check
```

### Security

- Never commit `.env` or place the token in source code, Dockerfile instructions, or logs.
- The real `.env` is excluded through `.gitignore` and `.dockerignore`.
- Rotate any token that has previously appeared in source code before the first public push.
- Store production secrets in Railway Variables or your server's secret manager.
- Enable GitHub Secret Scanning and Push Protection.
- Do not publish logs containing customer VINs, addresses, or phone numbers.

See [SECURITY.md](SECURITY.md) for additional recommendations.

### Limitations

The bot currently receives events through Long Polling. A single continuously running process is sufficient for a small workload, but MAX recommends Webhooks for production. A Webhook deployment requires a public HTTPS endpoint and a separate secret.

## License

No license has been specified yet. Add a `LICENSE` file before allowing third-party reuse or redistribution.

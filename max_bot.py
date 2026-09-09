import asyncio
import json
import logging
import os
import re
import secrets
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import aiohttp
import certifi
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=PROJECT_DIR / ".env", override=False)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def require_bot_token() -> str:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN. Добавьте его в .env или в Variables на Railway.")
    if len(token) > 512 or any(char.isspace() for char in token):
        raise RuntimeError("BOT_TOKEN имеет недопустимый формат.")
    return token


def read_admin_ids() -> tuple[int, ...]:
    result = []
    for value in re.split(r"[,;\s]+", os.getenv("ADMIN_IDS", "").strip()):
        if not value:
            continue
        try:
            admin_id = int(value)
            if admin_id <= 0:
                raise ValueError
            result.append(admin_id)
        except ValueError:
            logger.warning("Пропущен некорректный ADMIN_IDS: %r", value)
    return tuple(dict.fromkeys(result))


ADMIN_IDS = read_admin_ids()
API_URL = "https://platform-api2.max.ru"
MAX_REQUESTS_PER_SECOND = 25


class MaxClient:
    def __init__(self, token: str):
        self.headers = {"Authorization": token}
        self.session: aiohttp.ClientSession | None = None
        self._rate_lock = asyncio.Lock()
        self._last_request = 0.0

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=100)
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.load_verify_locations(PROJECT_DIR / "certificates" / "russian_trusted_root_ca.pem")
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(
            headers=self.headers, timeout=timeout, connector=connector
        )
        return self

    async def __aexit__(self, *_):
        if self.session:
            await self.session.close()

    async def request(self, method: str, path: str, **kwargs) -> dict:
        if not self.session:
            raise RuntimeError("MAX API client is not started")
        async with self._rate_lock:
            delay = (1 / MAX_REQUESTS_PER_SECOND) - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()
        async with self.session.request(method, API_URL + path, **kwargs) as response:
            if response.status >= 400:
                # Не включаем тело ответа в исключение: оно может содержать данные клиента.
                raise RuntimeError(f"MAX API вернул HTTP {response.status}")
            raw = await response.read()
            if not raw:
                return {}
            return json.loads(raw)

    async def send_message(self, text: str, *, user_id: int | None = None,
                           chat_id: int | None = None,
                           buttons: list[list[dict]] | None = None) -> dict:
        if user_id is None and chat_id is None:
            raise ValueError("Для сообщения нужен user_id или chat_id")
        params = {"user_id": user_id} if user_id is not None else {"chat_id": chat_id}
        body: dict = {"text": text}
        if buttons:
            body["attachments"] = [{
                "type": "inline_keyboard",
                "payload": {"buttons": buttons},
            }]
        return await self.request("POST", "/messages", params=params, json=body)

    async def answer_callback(self, callback_id: str) -> dict:
        return await self.request(
            "POST", "/answers", params={"callback_id": callback_id}, json={}
        )


client: MaxClient


@dataclass
class Order:
    step: str = "vin"
    vin: str = ""
    part: str = ""
    address: str = ""
    phone: str = ""
    nonce: str = ""
    updated_at: float = 0.0

    def __post_init__(self):
        self.nonce = secrets.token_urlsafe(9)
        self.updated_at = time.monotonic()

    def touch(self) -> None:
        self.updated_at = time.monotonic()


orders: dict[int, Order] = {}


def callback_button(text: str, payload: str, intent: str = "default") -> dict:
    return {"type": "callback", "text": text, "payload": payload, "intent": intent}


MAIN_BUTTONS = [
    [callback_button("🚗 Заказать запчасть", "order:start", "positive")],
    [callback_button("☎️ Поддержка", "menu:support")],
]
ORDER_TTL_SECONDS = 60 * 60
MAX_ACTIVE_ORDERS = 10_000


def cancel_buttons(order: Order) -> list[list[dict]]:
    return [[callback_button("Отменить", f"order:cancel:{order.nonce}", "negative")]]


def confirm_buttons(order: Order) -> list[list[dict]]:
    return [[
        callback_button("✅ Подтвердить", f"order:confirm:{order.nonce}", "positive"),
        callback_button("Отменить", f"order:cancel:{order.nonce}", "negative"),
    ]]


def remove_expired_orders() -> None:
    deadline = time.monotonic() - ORDER_TTL_SECONDS
    expired = [user_id for user_id, order in orders.items()
               if order.updated_at < deadline]
    for user_id in expired:
        orders.pop(user_id, None)


def main_text() -> str:
    return ("👋 Добро пожаловать!\n\n"
            "🚗 Подбор и доставка автозапчастей по Краснодару.\n"
            "Выберите нужное действие:")


def command_from(text: str) -> str:
    first = text.strip().split(maxsplit=1)[0].lower() if text.strip() else ""
    return first.split("@", maxsplit=1)[0]


def valid_vin(value: str) -> bool:
    return bool(re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value.upper()))


def order_summary(order: Order) -> str:
    return ("Проверьте заявку:\n\n"
            f"VIN: {order.vin}\nЗапчасть: {order.part}\n"
            f"Адрес доставки: {order.address}\nТелефон: {order.phone}\n\n"
            "Подтвердите данные кнопкой ниже.")


async def notify_admins(user_id: int, order: Order) -> bool:
    if not ADMIN_IDS:
        logger.error("Заявка пользователя %s не отправлена: ADMIN_IDS не задан", user_id)
        return False
    message = ("🚘 Новая заявка на автозапчасть\n\n"
               f"Пользователь MAX: {user_id}\nVIN: {order.vin}\n"
               f"Запчасть: {order.part}\nАдрес: {order.address}\nТелефон: {order.phone}")
    delivered = False
    for admin_id in ADMIN_IDS:
        try:
            await client.send_message(user_id=admin_id, text=message)
            delivered = True
        except Exception:
            logger.exception("Не удалось отправить заявку администратору %s", admin_id)
    return delivered


async def handle_message(user_id: int, text: str,
                         answer: Callable[..., Awaitable[object]]) -> None:
    remove_expired_orders()
    text = "".join(char for char in text[:4000]
                   if char in "\n\t" or ord(char) >= 32).strip()
    command = command_from(text)

    if command in {"/start", "/help"}:
        orders.pop(user_id, None)
        await answer(main_text(), buttons=MAIN_BUTTONS)
        return
    if command == "/support":
        await answer("☎️ Поддержка\n\nАндрей\nТелефон: 8 (928) 840-36-32",
                     buttons=MAIN_BUTTONS)
        return
    if command == "/cancel":
        cancelled = orders.pop(user_id, None)
        text = "Оформление заявки отменено." if cancelled else "Сейчас у вас нет незавершённой заявки."
        await answer(text, buttons=MAIN_BUTTONS)
        return
    if command == "/order":
        if user_id not in orders and len(orders) >= MAX_ACTIVE_ORDERS:
            await answer("Сервис временно перегружен. Попробуйте немного позже.",
                         buttons=MAIN_BUTTONS)
            return
        order = Order()
        orders[user_id] = order
        await answer("Введите 17-значный VIN автомобиля (латинские буквы и цифры).",
                     buttons=cancel_buttons(order))
        return

    order = orders.get(user_id)
    if order is None:
        await answer("Выберите нужное действие с помощью кнопок:", buttons=MAIN_BUTTONS)
        return
    if order.step == "vin":
        vin = re.sub(r"[\s-]", "", text).upper()
        if not valid_vin(vin):
            order.touch()
            await answer("VIN должен состоять из 17 латинских букв и цифр (буквы I, O, Q не используются). Проверьте номер и отправьте ещё раз.", buttons=cancel_buttons(order))
            return
        order.vin, order.step = vin, "part"
        order.touch()
        await answer("Какую запчасть нужно найти? Укажите название и, если знаете, артикул.", buttons=cancel_buttons(order))
        return
    if order.step == "part":
        if len(text) < 2:
            order.touch()
            await answer("Опишите нужную запчасть подробнее.", buttons=cancel_buttons(order))
            return
        order.part, order.step = text[:1000], "address"
        order.touch()
        await answer("Укажите адрес доставки в Краснодаре.", buttons=cancel_buttons(order))
        return
    if order.step == "address":
        if len(text) < 5:
            order.touch()
            await answer("Укажите полный адрес доставки.", buttons=cancel_buttons(order))
            return
        order.address, order.step = text[:500], "phone"
        order.touch()
        await answer("Укажите номер телефона для связи.", buttons=cancel_buttons(order))
        return
    if order.step == "phone":
        if not 10 <= len(re.sub(r"\D", "", text)) <= 15:
            order.touch()
            await answer("Не удалось распознать телефон. Например: +7 999 123-45-67", buttons=cancel_buttons(order))
            return
        order.phone, order.step = text[:100], "confirm"
        order.touch()
        await answer(order_summary(order), buttons=confirm_buttons(order))
        return
    if order.step == "confirm":
        if text.lower() not in {"да", "yes", "подтверждаю"}:
            await answer("Подтвердите или отмените заявку кнопкой ниже.", buttons=confirm_buttons(order))
            return
        order.step = "submitting"
        if await notify_admins(user_id, order):
            orders.pop(user_id, None)
            await answer("✅ Заявка принята! Мы свяжемся с вами для уточнения цены и срока доставки.", buttons=MAIN_BUTTONS)
        else:
            order.step = "confirm"
            order.touch()
            await answer("Не удалось передать заявку администратору. Позвоните в поддержку или попробуйте позже; введённые данные сохранены.", buttons=confirm_buttons(order))


async def process_update(update: dict) -> None:
    update_type = update.get("update_type")
    if update_type == "bot_started":
        chat_id = update.get("chat_id")
        user_id = (update.get("user") or {}).get("user_id")
        text = main_text()
        if chat_id is not None:
            await client.send_message(chat_id=chat_id, text=text, buttons=MAIN_BUTTONS)
        elif user_id is not None:
            await client.send_message(user_id=user_id, text=text, buttons=MAIN_BUTTONS)
        return

    if update_type == "message_callback":
        callback = update.get("callback") or {}
        user_id = (callback.get("user") or {}).get("user_id")
        callback_id = callback.get("callback_id")
        payload = callback.get("payload")
        if callback_id:
            try:
                await client.answer_callback(callback_id)
            except Exception:
                logger.warning("Не удалось подтвердить callback MAX")
        if user_id is None or not isinstance(payload, str):
            return

        async def answer(reply: str, **kwargs):
            return await client.send_message(user_id=user_id, text=reply, **kwargs)

        static_actions = {
            "order:start": "/order",
            "menu:support": "/support",
            "menu:main": "/start",
        }
        if payload in static_actions:
            await handle_message(user_id, static_actions[payload], answer)
            return

        parts = payload.split(":", maxsplit=2)
        if len(parts) == 3 and parts[0] == "order":
            action, nonce = parts[1], parts[2]
            order = orders.get(user_id)
            if order is None or not secrets.compare_digest(order.nonce, nonce):
                await answer("Эта кнопка относится к старой заявке.", buttons=MAIN_BUTTONS)
                return
            if action == "cancel":
                await handle_message(user_id, "/cancel", answer)
            elif action == "confirm" and order.step == "confirm":
                await handle_message(user_id, "да", answer)
        return

    if update_type != "message_created":
        return
    message = update.get("message") or {}
    sender = message.get("sender") or {}
    body = message.get("body") or {}
    user_id = sender.get("user_id")
    text = body.get("text")
    if user_id is None or not isinstance(text, str):
        return

    async def answer(reply: str, **kwargs):
        return await client.send_message(user_id=user_id, text=reply, **kwargs)

    await handle_message(user_id, text, answer)


async def start_polling() -> None:
    marker = None
    while True:
        params = {"timeout": 30, "limit": 100,
                  "types": "message_created,message_callback,bot_started"}
        if marker is not None:
            params["marker"] = marker
        try:
            data = await client.request("GET", "/updates", params=params)
            for update in data.get("updates", []):
                try:
                    await process_update(update)
                except Exception:
                    logger.exception("Ошибка обработки обновления")
            marker = data.get("marker", marker)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка Long Polling; повтор через 5 секунд")
            await asyncio.sleep(5)


async def main():
    global client
    if not ADMIN_IDS:
        raise RuntimeError("Не задан ADMIN_IDS — заявки некому отправлять.")
    async with MaxClient(require_bot_token()) as client:
        me = await client.request("GET", "/me")
        logger.info("Авторизация успешна: @%s", me.get("username", "unknown"))
        logger.info("Бот запущен в режиме Long Polling")
        await start_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception:
        logger.exception("Бот остановлен из-за ошибки")
        raise

import asyncio
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ADMIN_IDS", "123")

import max_bot


class FakeClient:
    def __init__(self):
        self.messages = []
        self.callbacks = []

    async def send_message(self, text, **kwargs):
        self.messages.append((text, kwargs))
        return {}

    async def answer_callback(self, callback_id):
        self.callbacks.append(callback_id)
        return {}


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = FakeClient()
        max_bot.client = self.client
        max_bot.ADMIN_IDS = (123,)
        max_bot.orders.clear()

    async def click(self, payload, callback_id="callback", user_id=777):
        await max_bot.process_update({
            "update_type": "message_callback",
            "callback": {
                "callback_id": callback_id,
                "payload": payload,
                "user": {"user_id": user_id},
            },
        })

    async def message(self, text, user_id=777):
        await max_bot.process_update({
            "update_type": "message_created",
            "message": {
                "sender": {"user_id": user_id},
                "body": {"text": text},
            },
        })

    async def test_complete_order(self):
        await self.click("order:start")
        order = max_bot.orders[777]
        await self.message("WVWZZZ1JZXW000001")
        await self.message("brake pads")
        await self.message("Krasnodar, Krasnaya 1")
        await self.message("+7 928 000 00 00")
        await self.click(f"order:confirm:{order.nonce}", "confirm")
        await self.click(f"order:confirm:{order.nonce}", "duplicate")
        self.assertNotIn(777, max_bot.orders)
        admin_messages = [item for item in self.client.messages
                          if item[1].get("user_id") == 123]
        self.assertEqual(len(admin_messages), 1)

    async def test_stale_button_cannot_confirm_new_order(self):
        await self.click("order:start")
        old_nonce = max_bot.orders[777].nonce
        await self.click("order:start")
        new_nonce = max_bot.orders[777].nonce
        await self.click(f"order:confirm:{old_nonce}")
        self.assertEqual(max_bot.orders[777].nonce, new_nonce)
        self.assertFalse(any(item[1].get("user_id") == 123
                             for item in self.client.messages))

    def test_expired_orders_are_removed(self):
        order = max_bot.Order()
        order.updated_at = time.monotonic() - max_bot.ORDER_TTL_SECONDS - 1
        max_bot.orders[777] = order
        max_bot.remove_expired_orders()
        self.assertNotIn(777, max_bot.orders)

    def test_vin_validation(self):
        self.assertTrue(max_bot.valid_vin("WVWZZZ1JZXW000001"))
        self.assertFalse(max_bot.valid_vin("INVALID"))


if __name__ == "__main__":
    unittest.main()

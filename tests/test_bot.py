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
        max_bot.reply_targets.clear()
        max_bot.admin_replies.clear()

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
        await self.message("Toyota")
        await self.message("2018")
        await self.message("brake pads")
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
        max_bot.remove_expired_state()
        self.assertNotIn(777, max_bot.orders)

    async def test_admin_can_reply_to_client(self):
        await self.click("order:start")
        order = max_bot.orders[777]
        await self.message("WVWZZZ1JZXW000001")
        await self.message("Toyota")
        await self.message("2018")
        await self.message("brake pads")
        await self.message("+7 928 000 00 00")
        await self.click(f"order:confirm:{order.nonce}", "confirm")

        admin_order = next(item for item in self.client.messages
                           if item[1].get("user_id") == 123)
        reply_payload = admin_order[1]["buttons"][0][0]["payload"]
        reply_nonce = reply_payload.rsplit(":", 1)[1]
        await self.click(reply_payload, "reply", user_id=123)
        self.assertIn(123, max_bot.admin_replies)

        await self.message("The part is available tomorrow.", user_id=123)
        client_replies = [item for item in self.client.messages
                          if item[1].get("user_id") == 777
                          and "The part is available" in item[0]]
        self.assertEqual(len(client_replies), 1)

        await self.click(f"reply:finish:{reply_nonce}", "finish", user_id=123)
        self.assertNotIn(123, max_bot.admin_replies)

    def test_vin_validation(self):
        self.assertTrue(max_bot.valid_vin("WVWZZZ1JZXW000001"))
        self.assertFalse(max_bot.valid_vin("INVALID"))

    async def test_invalid_year_does_not_advance_order(self):
        await self.click("order:start")
        await self.message("WVWZZZ1JZXW000001")
        await self.message("Toyota")
        await self.message("18")
        self.assertEqual(max_bot.orders[777].step, "year")


if __name__ == "__main__":
    unittest.main()

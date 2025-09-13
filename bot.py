# bot.py
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, Message
)
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties

# === Загружаем переменные окружения ===
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
CRYPTOPAY_TOKEN = os.getenv("CRYPTOPAY_TOKEN")

if not API_TOKEN:
    raise ValueError("❌ Укажи API_TOKEN в .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher(storage=MemoryStorage())

# === CRYPTOBOT функции ===
BASE_URL = "https://pay.crypt.bot/api/"

async def get_exchange_rate(asset="TON"):
    url = BASE_URL + "getExchangeRates"
    headers = {"Crypto-Pay-API-Token": CRYPTOPAY_TOKEN}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            result = await resp.json()
            for rate in result["result"]:
                if rate["source"] == "USD" and rate["target"] == asset:
                    return float(rate["rate"])
            for rate in result["result"]:
                if rate["source"] == asset and rate["target"] == "USD":
                    return 1 / float(rate["rate"])
    raise Exception(f"Не удалось получить курс {asset}")

async def create_crypto_invoice(amount_usd=1, asset="TON"):
    rate = await get_exchange_rate(asset)
    amount = round(amount_usd * rate, 4)
    url = BASE_URL + "createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTOPAY_TOKEN}
    data = {"amount": amount, "asset": asset, "description": f"Оплата ({amount_usd}$ в {asset})"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            result = await resp.json()
            if "result" in result:
                return result["result"]
            else:
                raise Exception(result.get("error", "Неизвестная ошибка"))

async def check_invoice(invoice_id):
    url = BASE_URL + f"getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTOPAY_TOKEN}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            result = await resp.json()
            return result["result"]["items"][0]

async def wait_for_payment(user_id, invoice_id):
    for _ in range(30):  # ждём до 5 минут
        await asyncio.sleep(10)
        invoice = await check_invoice(invoice_id)
        if invoice["status"] == "paid":
            try:
                expire_time = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
                invite_link = await bot.create_chat_invite_link(
                    chat_id=CHANNEL_ID,
                    expire_date=expire_time,
                    member_limit=1,
                    name=f"Оплата от {user_id}"
                )
                await bot.send_message(user_id, f"✅ Оплата успешна!\n🔗 {invite_link.invite_link}")
                await bot.send_message(ADMIN_ID, f"💳 Оплата от {user_id}\n🔗 {invite_link.invite_link}")
            except Exception as e:
                logging.error(f"Ошибка при создании ссылки: {e}")
            return

# === Хендлеры ===
@dp.message(F.text == "/start")
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Оплатить", callback_data="pay_options")],
    ])
    await message.answer("Привет! 👋 Выберите способ оплаты:", reply_markup=kb)

@dp.callback_query(F.data == "pay_options")
async def payment_options(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 TON", callback_data="crypto_TON")],
        [InlineKeyboardButton(text="💵 USDT", callback_data="crypto_USDT")],
        [InlineKeyboardButton(text="₿ BTC", callback_data="crypto_BTC")],
    ])
    await callback.message.edit_text("Выберите валюту:", reply_markup=kb)

@dp.callback_query(F.data.startswith("crypto_"))
async def crypto_payment(callback: types.CallbackQuery):
    asset = callback.data.split("_")[1]
    try:
        invoice = await create_crypto_invoice(amount_usd=1, asset=asset)
        asyncio.create_task(wait_for_payment(callback.from_user.id, invoice["invoice_id"]))
        await callback.message.answer(f"Оплатите по ссылке:\n{invoice['pay_url']}")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")

# === Звёзды ===
@dp.callback_query(F.data == "pay_stars")
async def pay_stars(callback: types.CallbackQuery):
    price = [LabeledPrice(label="Подписка", amount=100)]
    await callback.message.answer_invoice(
        title="Подписка",
        description="Оплата приватного канала",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=price,
        payload="stars_payment"
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def payment_success(message: Message):
    expire_time = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
    invite_link = await bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        expire_date=expire_time,
        member_limit=1,
        name=f"Оплата от {message.from_user.id}"
    )
    await message.answer(f"✅ Оплата прошла!\n🔗 {invite_link.invite_link}")

# === MAIN ===
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())









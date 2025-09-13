# bot.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import aiohttp
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, Message
)
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties

# === ЗАГРУЖАЕМ ПЕРЕМЕННЫЕ ИЗ .env ===
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
CRYPTOPAY_TOKEN = os.getenv("CRYPTOPAY_TOKEN")

if not API_TOKEN:
    raise ValueError("Пожалуйста, укажите API_TOKEN в файле .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher(storage=MemoryStorage())

# === ФУНКЦИИ CRYPTOBOT ===
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
    data = {
        "amount": amount,
        "asset": asset,
        "description": f"Оплата приватного канала ({amount_usd}$ в {asset})"
    }
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
                await bot.send_message(
                    user_id,
                    f"✅ Оплата прошла успешно!\n\n"
                    f"🔗 Ваша ссылка на канал:\n{invite_link.invite_link}\n\n"
                    f"⏳ Ссылка действует 10 минут и только для одного входа."
                )
                await bot.send_message(
                    ADMIN_ID,
                    f"💳 Новая оплата CRYPTOBOT!\n"
                    f"👤 Пользователь: {user_id}\n"
                    f"🔗 Ссылка: {invite_link.invite_link}"
                )
            except Exception as e:
                logging.error(f"Ошибка при создании ссылки: {e}")
            return

# === ХЕНДЛЕРЫ ===
@dp.message(F.text == "/start")
async def start(message: types.Message):
    text = (
        "Добро пожаловать в *Altushki*\n\n"
        "- Доступ к приватному материалу.\n"
        "- Более 3000 видео и 4000 фото.\n"
        "- Быстрое обновление контента.\n\n"
        "⛃ *Оплата навсегда:*\n"
        "- 99р (карта / крипта)\n"
        "- Цена в звёздах 100 ✰\n\n"
        "После оплаты вы получите одноразовую ссылку на приватный канал."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 ОПЛАТА ПРИВАТНОГО КАНАЛА", callback_data="pay_options")],
        [InlineKeyboardButton(text="⭐ ОТЗЫВЫ", url="https://t.me/+FkWlpM6bH5RmNzVi")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "pay_options")
async def payment_options(callback: types.CallbackQuery):
    await callback.answer()
    text = "*ВЫБЕРИТЕ СПОСОБ ОПЛАТЫ*"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 УКР КАРТА", callback_data="ukr_card")],
        [InlineKeyboardButton(text="💳 РУ КАРТА", callback_data="ru_card")],
        [InlineKeyboardButton(text="💰 CRYPTOBOT", callback_data="crypto_choose")],
        [InlineKeyboardButton(text="✨ ЗВЁЗДАМИ", callback_data="pay_stars")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "crypto_choose")
async def crypto_choose(callback: types.CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 TON", callback_data="crypto_TON")],
        [InlineKeyboardButton(text="💵 USDT", callback_data="crypto_USDT")],
        [InlineKeyboardButton(text="₿ BTC", callback_data="crypto_BTC")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="pay_options")]
    ])
    await callback.message.edit_text("Выберите валюту для оплаты:", reply_markup=kb)

@dp.callback_query(F.data.startswith("crypto_"))
async def crypto_payment(callback: types.CallbackQuery):
    await callback.answer()
    asset = callback.data.split("_")[1]
    try:
        invoice = await create_crypto_invoice(amount_usd=1, asset=asset)
        pay_url = invoice["pay_url"]
        invoice_id = invoice["invoice_id"]
        await callback.message.answer(
            f"💰 Оплата приватного канала (1$ в {asset})\n\n"
            f"👉 Перейдите по ссылке:\n{pay_url}\n\n"
            f"После оплаты бот вышлет доступ ✅"
        )
        asyncio.create_task(wait_for_payment(callback.from_user.id, invoice_id))
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при создании счета: {e}")

# === УКР КАРТА ===
@dp.callback_query(F.data == "ukr_card")
async def ukr_card(callback: types.CallbackQuery):
    text = (
        "*ОПЛАТА ПРИВАТА КАРТОЙ (УКР):*\n\n"
        "5168752022336435 | Приватбанк\n"
        "4441114432331898 | Монобанк\n\n"
        "⛃ *50 гривен* стоит приватка.\n"
        "В комментарии укажите свой юзер в Telegram.\n\n"
        "Если не получается написать комментарий — напишите @altushkisupport с квитанцией.\n"
        "После успешной оплаты администратор скинет вам ссылку на приватный канал."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="pay_options")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

# === РУ КАРТА ===
@dp.callback_query(F.data == "ru_card")
async def ru_card(callback: types.CallbackQuery):
    text = (
        "*ОПЛАТА ПРИВАТА FUNPAY (РУ):*\n\n"
        "https://funpay.com/lots/offer?id=51992416 | Funpay\n\n"
        "После успешной оплаты администратор скинет вам ссылку на приватный канал."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="pay_options")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

# === ЗВЁЗДЫ ===
@dp.callback_query(F.data == "pay_stars")
async def pay_stars(callback: types.CallbackQuery):
    await callback.answer()
    price = [LabeledPrice(label="Подписка", amount=100)]
    await callback.message.answer_invoice(
        title="Altushki privat",
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
    try:
        await message.answer("✅ Оплата прошла успешно! Создаю ссылку...")
        expire_time = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
        invite_link = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            expire_date=expire_time,
            member_limit=1,
            name=f"Оплата от {message.from_user.id}"
        )
        await message.answer(
            f"🔗 *Ваша персональная ссылка на канал:*\n"
            f"{invite_link.invite_link}\n\n"
            f"⏳ Ссылка действует 10 минут и только для одного входа!"
        )
        await bot.send_message(
            ADMIN_ID,
            f"💳 *Новая оплата звёздами!*\n"
            f"👤 Пользователь: @{message.from_user.username or 'без username'} "
            f"(ID: {message.from_user.id})\n"
            f"🔗 Ссылка: {invite_link.invite_link}"
        )
    except Exception as e:
        logging.error(f"Ошибка при создании ссылки: {e}")
        await message.answer("❌ Произошла ошибка при создании ссылки. Напишите @altushkisupport")

# === MAIN ===
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())








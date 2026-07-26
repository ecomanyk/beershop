import asyncio
import logging
import os
import sys
import json

from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ═══════════════════════════════════════════════════════════════
#  НАЛАШТУВАННЯ ЧЕРЕЗ ЗМІННІ ОТОЧЕННЯ (для Render)
# ═══════════════════════════════════════════════════════════════
# У Render Dashboard → Environment додай:
#   BOT_TOKEN = 8872901197:AAFz5lyKIOpbMdwA70hxLoP5i1EU5r4Fn5s
#   CHAT_ID_MANAGERS = 4991707736 (наприклад: -1001234567890 або 123456789)
#   WEB_APP_URL = https://ecomanyk.github.io/beershop/index.html
#
# Render автоматично дає змінну RENDER_EXTERNAL_URL

API_TOKEN = os.getenv("BOT_TOKEN", "8872901197:AAFgViAeYRWkPUMk6h7RBZZsoRCXB1jAMbM")
CHAT_ID_MANAGERS = os.getenv("CHAT_ID_MANAGERS", "4991707736")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://ecomanyk.github.io/beershop/index.html")

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}" if RENDER_URL else os.getenv("WEBHOOK_URL", "")

PORT = int(os.getenv("PORT", "8080"))

# ═══════════════════════════════════════════════════════════════
#  ІНІЦІАЛІЗАЦІЯ
# ═══════════════════════════════════════════════════════════════
if not API_TOKEN:
    raise ValueError("BOT_TOKEN не задано! Додай його в Environment Variables на Render.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  СТАНИ FSM
# ═══════════════════════════════════════════════════════════════
class OrderStates(StatesGroup):
    choosing_delivery = State()
    waiting_for_house = State()
    waiting_for_floor = State()
    waiting_for_apartment = State()
    waiting_for_phone = State()
    waiting_for_promo = State()

# ═══════════════════════════════════════════════════════════════
#  ДОПОМІЖНІ ФУНКЦІЇ
# ═══════════════════════════════════════════════════════════════
NEWLINE = "\n"

def format_cart(cart: dict):
    lines = []
    total = 0
    for item_id, info in cart.items():
        name = info.get("name", "Товар")
        price = int(info.get("price", 0))
        count = info.get("count", 1)
        unit = info.get("unit", "шт")

        if unit == "г":
            qty_units = count / 50
            item_total = int(price * qty_units)
            qty_str = f"{int(count)} г"
        else:
            qty_units = count / 0.5
            item_total = int(price * qty_units)
            qty_str = f"{count} л"

        total += item_total
        lines.append(f"• {name} — {qty_str} — {item_total} грн")

    return NEWLINE.join(lines), total

# ═══════════════════════════════════════════════════════════════
#  ХЕНДЛЕРИ
# ═══════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    inline_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🍺 Відкрити Меню Магазину",
                    web_app=types.WebAppInfo(url=WEB_APP_URL),
                )
            ]
        ]
    )
    text = (
        f"Привіт, {message.from_user.first_name}! 🍻" + NEWLINE + NEWLINE +
        "Ласкаво просимо до <b>Пивного Крафту</b>!" + NEWLINE +
        "У нас — розливне крафтове пиво, вино, квас, лимонад та закуски." + NEWLINE + NEWLINE +
        "🚚 <b>Доставка</b> по ЖК Навігатор (пров. Балтійський)" + NEWLINE +
        "🏪 <b>Самовивіз</b> — пров. Балтійський, 5" + NEWLINE + NEWLINE +
        "🛵 <b>Мінімальне замовлення на доставку: 300 грн</b>" + NEWLINE + NEWLINE +
        "Натискай кнопку нижче, щоб обрати напої та закуски!"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=inline_kb)


@dp.message(F.web_app_data)
async def parse_web_app_data(message: types.Message, state: FSMContext):
    logger.info(f"[WEBAPP] Отримано дані: {message.web_app_data.data[:200]}")
    try:
        raw_data = message.web_app_data.data
        order_json = json.loads(raw_data)

        products = order_json.get("products", {})
        total_sum = order_json.get("total", 0)

        logger.info(f"[WEBAPP] Товарів: {len(products)}, сума: {total_sum}")

        if not products:
            await message.answer(
                "🍺 Здається, ваш кошик порожній.",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(
                                text="🍺 Відкрити Меню",
                                web_app=types.WebAppInfo(url=WEB_APP_URL),
                            )
                        ]
                    ]
                ),
            )
            return

        await state.update_data(cart=products, total=total_sum)
        await state.set_state(OrderStates.choosing_delivery)

        delivery_kb = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="🚚 Доставка по ЖК Навігатор")],
                [types.KeyboardButton(text="🏪 Самовивіз (пров. Балтійський, 5)")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        await message.answer(
            "📦 <b>Як отримаєте замовлення?</b>" + NEWLINE + NEWLINE + "Оберіть спосіб отримання:",
            parse_mode="HTML",
            reply_markup=delivery_kb,
        )
    except Exception as e:
        logger.error(f"[WEBAPP] Помилка: {e}")
        await message.answer("⚠️ Помилка зчитування кошика. Спробуйте ще раз.")


@dp.message(OrderStates.choosing_delivery, F.text == "🏪 Самовивіз (пров. Балтійський, 5)")
async def process_pickup(message: types.Message, state: FSMContext):
    await state.update_data(
        delivery_type="pickup", house="—", floor="—", apartment="—"
    )
    await state.set_state(OrderStates.waiting_for_phone)

    phone_kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📱 Поділитися номером", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "🏪 <b>Самовивіз обрано!</b>" + NEWLINE +
        "Адреса: пров. Балтійський, 5" + NEWLINE + NEWLINE +
        "Тепер вкажіть <b>номер телефону</b> для зв'язку:",
        parse_mode="HTML",
        reply_markup=phone_kb,
    )


@dp.message(OrderStates.choosing_delivery, F.text == "🚚 Доставка по ЖК Навігатор")
async def process_delivery(message: types.Message, state: FSMContext):
    await state.update_data(delivery_type="delivery")
    await state.set_state(OrderStates.waiting_for_house)

    house_kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="1"), types.KeyboardButton(text="3")],
            [types.KeyboardButton(text="3а"), types.KeyboardButton(text="5")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "🚚 <b>Доставка по ЖК Навігатор</b>" + NEWLINE + NEWLINE +
        "Оберіть <b>номер вашого будинку</b>:",
        parse_mode="HTML",
        reply_markup=house_kb,
    )


@dp.message(OrderStates.choosing_delivery)
async def process_delivery_invalid(message: types.Message):
    await message.answer("Будь ласка, оберіть спосіб отримання кнопками нижче 👇")


@dp.message(OrderStates.waiting_for_house, F.text.in_({"1", "3", "3а", "5"}))
async def process_house(message: types.Message, state: FSMContext):
    await state.update_data(house=message.text)
    await state.set_state(OrderStates.waiting_for_floor)
    await message.answer(
        f"🏠 Будинок <b>{message.text}</b> прийнято. 👍" + NEWLINE + NEWLINE +
        "Напишіть ваш <b>поверх</b>:",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove(),
    )


@dp.message(OrderStates.waiting_for_house)
async def process_house_invalid(message: types.Message):
    await message.answer("Будь ласка, оберіть будинок із кнопок (1, 3, 3а або 5).")


@dp.message(OrderStates.waiting_for_floor)
async def process_floor(message: types.Message, state: FSMContext):
    await state.update_data(floor=message.text)
    await state.set_state(OrderStates.waiting_for_apartment)
    await message.answer("Вкажіть <b>номер квартири</b>:", parse_mode="HTML")


@dp.message(OrderStates.waiting_for_apartment)
async def process_apartment(message: types.Message, state: FSMContext):
    await state.update_data(apartment=message.text)
    await state.set_state(OrderStates.waiting_for_phone)

    phone_kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📱 Поділитися номером", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "📞 Вкажіть <b>номер телефону</b> для зв'язку." + NEWLINE +
        "Менеджер зателефонує для підтвердження, а кур'єру він теж знадобиться.",
        parse_mode="HTML",
        reply_markup=phone_kb,
    )


@dp.message(OrderStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text.strip()
        digits = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not digits.isdigit() or len(digits) < 9:
            await message.answer(
                "⚠️ Введіть коректний номер (мінімум 9 цифр) або натисніть 'Поділитися номером'."
            )
            return

    await state.update_data(phone=phone)
    await state.set_state(OrderStates.waiting_for_promo)

    promo_kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="⏩ Пропустити")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "🎁 <b>Маєте промокод?</b>" + NEWLINE +
        "Введіть його нижче або натисніть «Пропустити»:",
        parse_mode="HTML",
        reply_markup=promo_kb,
    )


@dp.message(OrderStates.waiting_for_promo)
async def process_promo_and_finish(message: types.Message, state: FSMContext):
    promo_entered = message.text.strip().upper()
    user_data = await state.get_data()

    cart = user_data.get("cart", {})
    total_sum = int(user_data.get("total", 0))
    house = user_data.get("house", "—")
    floor = user_data.get("floor", "—")
    apartment = user_data.get("apartment", "—")
    phone = user_data.get("phone", "—")
    delivery_type = user_data.get("delivery_type", "delivery")

    discount_text = ""
    if promo_entered == "PIVO10":
        discount = int(total_sum * 0.10)
        total_sum -= discount
        discount_text = f"🎁 <b>Промокод:</b> PIVO10 (-{discount} грн)" + NEWLINE
    elif promo_entered not in ["⏩ ПРОПУСТИТИ", "", "⏩ Пропустити"]:
        discount_text = f"⚠️ Промокод <code>{promo_entered}</code> не знайдено" + NEWLINE

    items_text, _ = format_cart(cart)

    if delivery_type == "pickup":
        address_text = "🏪 <b>Самовивіз</b>" + NEWLINE + "📍 пров. Балтійський, 5 (Пивний Крафт)" + NEWLINE
    else:
        address_text = (
            f"📍 <b>Адреса:</b> ЖК Навігатор, пров. Балтійський" + NEWLINE +
            f"🏠 <b>Будинок:</b> {house} | 🏢 <b>Поверх:</b> {floor} | 🚪 <b>Кв:</b> {apartment}" + NEWLINE
        )

    order_details = (
        address_text +
        f"📞 <b>Телефон:</b> {phone}" + NEWLINE + NEWLINE +
        "📦 <b>Склад замовлення:</b>" + NEWLINE +
        items_text + NEWLINE + NEWLINE +
        discount_text +
        f"💵 <b>Разом до сплати:</b> {total_sum} грн"
    )

    # --- Менеджеру ---
    delivery_icon = "🏪" if delivery_type == "pickup" else "🚚"
    manager_report = (
        f"🔔 <b>НОВЕ ЗАМОВЛЕННЯ З ПИВНОГО КРАФТУ!</b>" + NEWLINE +
        "━━━━━━━━━━━━━━━━━━━━━" + NEWLINE + NEWLINE +
        f"👤 <b>Клієнт:</b> {message.from_user.full_name}" + NEWLINE +
        f"🔗 <b>Юзер:</b> @{message.from_user.username or 'немає'}" + NEWLINE +
        f"{delivery_icon} <b>Тип:</b> {'Самовивіз' if delivery_type == 'pickup' else 'Доставка'}" + NEWLINE + NEWLINE +
        order_details + NEWLINE +
        NEWLINE + "━━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        await bot.send_message(
            chat_id=CHAT_ID_MANAGERS,
            text=manager_report,
            parse_mode="HTML",
        )
        logger.info(f"[ORDER] Відправлено менеджеру. Клієнт: {message.from_user.id}")
    except Exception as e:
        logger.error(f"[ORDER] Помилка відправки менеджеру: {e}")

    # --- Клієнту ---
    return_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🍺 Відкрити Меню Знову",
                    web_app=types.WebAppInfo(url=WEB_APP_URL),
                )
            ]
        ]
    )

    client_report = (
        f"🎉 <b>Ваше замовлення прийнято!</b>" + NEWLINE + NEWLINE +
        ("🏪 Готуємо ваше замовлення для самовивозу!" if delivery_type == "pickup" else "🚚 Кур'єр готується до виїзду!") + NEWLINE +
        "Менеджер зателефонує для підтвердження." + NEWLINE + NEWLINE +
        "━━━━━━━━━━━━━━━━━━━━━" + NEWLINE +
        order_details + NEWLINE +
        "━━━━━━━━━━━━━━━━━━━━━" + NEWLINE + NEWLINE +
        "Дякуємо, що обрали Пивний Крафт! 🍻"
    )

    await message.answer(
        text=client_report,
        parse_mode="HTML",
        reply_markup=return_kb,
    )
    await state.clear()


# ═══════════════════════════════════════════════════════════════
#  WEBHOOK + AIOHTTP СЕРВЕР (для Render)
# ═══════════════════════════════════════════════════════════════

async def on_startup(bot: Bot):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logger.info(f"✅ Webhook встановлено: {WEBHOOK_URL}")
    else:
        logger.warning("⚠️ WEBHOOK_URL не задано! Бот не отримуватиме оновлення.")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logger.info("🛑 Webhook видалено")


def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    # Healthcheck — Render перевіряє, чи живий сервіс
    async def health(request):
        return web.Response(text="🍺 Пивний Крафт бот працює!")

    app.router.add_get("/", health)

    # Webhook endpoint
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()

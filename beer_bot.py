import asyncio
import logging
import json
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ═══════════════════════════════════════════════════════════════
#  НАЛАШТУВАННЯ БОТА
# ═══════════════════════════════════════════════════════════════
# ⚠️ ЗАМІНИТИ НА СВОЇ ЗНАЧЕННЯ:
API_TOKEN = '8872901197:AAFz5lyKIOpbMdwA70hxLoP5i1EU5r4Fn5s'          # Токен від @BotFather
CHAT_ID_MANAGERS = '4991707736'  # ID чату/групи менеджерів (число, може бути з мінусом)

# Посилання на Web App меню
WEB_APP_URL = "https://ecomanyk.github.io/beershop/index.html"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    stream=sys.stdout
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
def format_cart(cart: dict) -> tuple[str, int]:
    """Форматує кошик у текст та підраховує суму з урахуванням одиниць."""
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

    return "\n".join(lines), total

# ═══════════════════════════════════════════════════════════════
#  ЛОГУВАННЯ ВСІХ ВХІДНИХ ПОВІДОМЛЕНЬ (для відладки)
# ═══════════════════════════════════════════════════════════════
@dp.message()
async def log_all_messages(message: types.Message):
    """Логує всі вхідні повідомлення для відладки."""
    has_webapp = "ТАК" if message.web_app_data else "НІ"
    logger.info(f"[LOG] Від {message.from_user.id} | web_app_data: {has_webapp} | текст: {message.text[:50] if message.text else '(немає)'} | contact: {bool(message.contact)}")

# ═══════════════════════════════════════════════════════════════
#  1. СТАРТ
# ═══════════════════════════════════════════════════════════════
@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    inline_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🍺 Відкрити Меню Магазину",
                web_app=types.WebAppInfo(url=WEB_APP_URL)
            )]
        ]
    )
    await message.answer(
        f"Привіт, {message.from_user.first_name}! 🍻\n\n"
        "Ласкаво просимо до <b>Пивного Крафту</b>!\n"
        "У нас — розливне крафтове пиво, вино, квас, лимонад та закуски.\n\n"
        "🚚 <b>Доставка</b> по ЖК Навігатор (пров. Балтійський)\n"
        "🏪 <b>Самовивіз</b> — пров. Балтійський, 5\n\n"
        "🛵 <b>Мінімальне замовлення на доставку: 300 грн</b>\n\n"
        "Натискай кнопку нижче, щоб обрати напої та закуски!",
        parse_mode="HTML",
        reply_markup=inline_kb
    )

# ═══════════════════════════════════════════════════════════════
#  2. ОБРОБКА ДАНИХ З WEB APP
# ═══════════════════════════════════════════════════════════════
@dp.message(F.web_app_data)
async def parse_web_app_data(message: types.Message, state: FSMContext):
    logger.info(f"[WEBAPP] Отримано дані від WebApp: {message.web_app_data.data[:200]}")
    try:
        raw_data = message.web_app_data.data
        order_json = json.loads(raw_data)

        products = order_json.get("products", {})
        total_sum = order_json.get("total", 0)

        logger.info(f"[WEBAPP] Товарів: {len(products)}, сума: {total_sum}")

        if not products:
            await message.answer(
                "🍺 Здається, ваш кошик порожній. Додайте щось смачненьке!",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(
                            text="🍺 Відкрити Меню",
                            web_app=types.WebAppInfo(url=WEB_APP_URL)
                        )]
                    ]
                )
            )
            return

        await state.update_data(cart=products, total=total_sum)
        await state.set_state(OrderStates.choosing_delivery)

        delivery_kb = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="🚚 Доставка по ЖК Навігатор")],
                [types.KeyboardButton(text="🏪 Самовивіз (пров. Балтійський, 5)")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await message.answer(
            "📦 <b>Як отримаєте замовлення?</b>\n\n"
            "Оберіть спосіб отримання:",
            parse_mode="HTML",
            reply_markup=delivery_kb
        )
        logger.info("[WEBAPP] Запитано спосіб доставки")

    except json.JSONDecodeError as e:
        logger.error(f"[WEBAPP] Помилка JSON: {e} | raw: {raw_data[:200]}")
        await message.answer(
            "⚠️ Помилка зчитування кошика. Спробуйте ще раз або напишіть менеджеру."
        )
    except Exception as e:
        logger.error(f"[WEBAPP] Невідома помилка: {e}")
        await message.answer(
            "⚠️ Ой, виникла помилка при зчитуванні кошика. Спробуйте ще раз."
        )

# ═══════════════════════════════════════════════════════════════
#  3. ВИБІР СПОСОБУ ОТРИМАННЯ
# ═══════════════════════════════════════════════════════════════
@dp.message(OrderStates.choosing_delivery, F.text == "🏪 Самовивіз (пров. Балтійський, 5)")
async def process_pickup(message: types.Message, state: FSMContext):
    await state.update_data(delivery_type="pickup", house="—", floor="—", apartment="—")
    await state.set_state(OrderStates.waiting_for_phone)

    phone_kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📱 Поділитися номером", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "🏪 <b>Самовивіз обрано!</b>\n"
        "Адреса: пров. Балтійський, 5\n\n"
        "Тепер вкажіть <b>номер телефону</b> для зв'язку:",
        parse_mode="HTML",
        reply_markup=phone_kb
    )

@dp.message(OrderStates.choosing_delivery, F.text == "🚚 Доставка по ЖК Навігатор")
async def process_delivery(message: types.Message, state: FSMContext):
    await state.update_data(delivery_type="delivery")
    await state.set_state(OrderStates.waiting_for_house)

    house_kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="1"), types.KeyboardButton(text="3")],
            [types.KeyboardButton(text="3а"), types.KeyboardButton(text="5")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "🚚 <b>Доставка по ЖК Навігатор</b>\n\n"
        "Оберіть <b>номер вашого будинку</b>:",
        parse_mode="HTML",
        reply_markup=house_kb
    )

@dp.message(OrderStates.choosing_delivery)
async def process_delivery_invalid(message: types.Message):
    await message.answer("Будь ласка, оберіть спосіб отримання кнопками нижче 👇")

# ═══════════════════════════════════════════════════════════════
#  4. АДРЕСА (для доставки)
# ═══════════════════════════════════════════════════════════════
@dp.message(OrderStates.waiting_for_house, F.text.in_({"1", "3", "3а", "5"}))
async def process_house(message: types.Message, state: FSMContext):
    await state.update_data(house=message.text)
    await state.set_state(OrderStates.waiting_for_floor)
    await message.answer(
        f"🏠 Будинок <b>{message.text}</b> прийнято. 👍\n\n"
        "Напишіть ваш <b>поверх</b>:",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove()
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
        one_time_keyboard=True
    )

    await message.answer(
        "📞 Вкажіть <b>номер телефону</b> для зв'язку.\n"
        "Менеджер зателефонує для підтвердження, а кур'єру він теж знадобиться.",
        parse_mode="HTML",
        reply_markup=phone_kb
    )

# ═══════════════════════════════════════════════════════════════
#  5. ТЕЛЕФОН
# ═══════════════════════════════════════════════════════════════
@dp.message(OrderStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text.strip()
        digits_only = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not digits_only.isdigit() or len(digits_only) < 9:
            await message.answer(
                "⚠️ Будь ласка, введіть коректний номер телефону (мінімум 9 цифр) або натисніть кнопку 'Поділитися номером'."
            )
            return

    await state.update_data(phone=phone)
    await state.set_state(OrderStates.waiting_for_promo)

    promo_kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="⏩ Пропустити")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "🎁 <b>Маєте промокод?</b>\n"
        "Введіть його нижче або натисніть «Пропустити»:",
        parse_mode="HTML",
        reply_markup=promo_kb
    )

# ═══════════════════════════════════════════════════════════════
#  6. ФІНАЛ — ПРОМОКОД ТА ВІДПРАВКА
# ═══════════════════════════════════════════════════════════════
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

    # Промокоди
    discount_text = ""
    if promo_entered == "PIVO10":
        discount = int(total_sum * 0.10)
        total_sum -= discount
        discount_text = f"🎁 <b>Промокод:</b> PIVO10 (-{discount} грн)\n"
    elif promo_entered not in ["⏩ ПРОПУСТИТИ", "", "⏩ Пропустити"]:
        discount_text = f"⚠️ Промокод <code>{promo_entered}</code> не знайдено\n"

    # Форматування кошика
    items_text, _ = format_cart(cart)

    # Адреса або самовивіз
    if delivery_type == "pickup":
        address_text = (
            "🏪 <b>Самовивіз</b>\n"
            "📍 пров. Балтійський, 5 (Пивний Крафт)\n"
        )
    else:
        address_text = (
            f"📍 <b>Адреса:</b> ЖК Навігатор, пров. Балтійський\n"
            f"🏠 <b>Будинок:</b> {house} | 🏢 <b>Поверх:</b> {floor} | 🚪 <b>Кв:</b> {apartment}\n"
        )

    order_details = (
        f"{address_text}"
        f"📞 <b>Телефон:</b> {phone}\n\n"
        f"📦 <b>Склад замовлення:</b>\n"
        f"{items_text}\n\n"
        f"{discount_text}"
        f"💵 <b>Разом до сплати:</b> {total_sum} грн"
    )

    # ── Повідомлення менеджеру ──
    delivery_icon = "🏪" if delivery_type == "pickup" else "🚚"
    manager_report = (
        f"🔔 <b>НОВЕ ЗАМОВЛЕННЯ З ПИВНОГО КРАФТУ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Клієнт:</b> {message.from_user.full_name}\n"
        f"🔗 <b>Юзер:</b> @{message.from_user.username or 'немає'}\n"
        f"{delivery_icon} <b>Тип:</b> {'Самовивіз' if delivery_type == 'pickup' else 'Доставка'}\n\n"
        f"{order_details}\n"
        f"\n━━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        await bot.send_message(
            chat_id=CHAT_ID_MANAGERS,
            text=manager_report,
            parse_mode="HTML"
        )
        logger.info(f"[ORDER] Відправлено менеджеру. Клієнт: {message.from_user.id}")
    except Exception as e:
        logger.error(f"[ORDER] Помилка відправки менеджеру: {e}")

    # ── Повідомлення клієнту ──
    return_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🍺 Відкрити Меню Знову",
                web_app=types.WebAppInfo(url=WEB_APP_URL)
            )]
        ]
    )

    client_report = (
        f"🎉 <b>Ваше замовлення прийнято!</b>\n\n"
        f"{'🏪 Готуємо ваше замовлення для самовивозу!' if delivery_type == 'pickup' else '🚚 Курʼєр готується до виїзду!'}\n"
        f"Менеджер зателефонує для підтвердження.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{order_details}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Дякуємо, що обрали Пивний Крафт! 🍻"
    )

    await message.answer(
        text=client_report,
        parse_mode="HTML",
        reply_markup=return_kb
    )
    await state.clear()

# ═══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════════════════════════
async def main():
    logger.info("🤖 Бот запущено!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

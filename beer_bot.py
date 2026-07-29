import logging
import json
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo, 
    ReplyKeyboardRemove
)

BOT_TOKEN = "8872901197:AAFgViAeYRWkPUMk6h7RBZZsoRCXB1jAMbM"
ADMIN_CHAT_ID = -1004991707736  # ID группы/чата менеджеров
WEBAPP_URL = "https://ecomanyk.github.io/beershop/index.html"  # Ссылка на твой WebApp

# Промокоды (код: процент скидки)
PROMO_CODES = {
    "NAVIGATOR10": 10
}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

SHOP_NAMES = {
    "beer": "🍺 BeerMarket",
    "pizza": "🍕 BigPapa",
    "galia": "🥟 Галія",
    "fruits": "🍎 Фрукти & Овочі"
}

# Состояния FSM
class OrderFSM(StatesGroup):
    waiting_for_building = State()
    waiting_for_entrance = State()
    waiting_for_floor = State()
    waiting_for_apt = State()
    waiting_for_phone = State()
    waiting_for_payment = State()
    waiting_for_promo = State()

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Відкрити доставку ЖК", web_app=WebAppInfo(url=WEBAPP_URL))]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🛒 **Ласкаво просимо до сервісу локальної доставки ЖК Навігатор!**\n\n"
        "Натисніть кнопку нижче, щоб відкрити каталог та зробити замовлення:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# Форматирование количества товаров
def format_qty(count: float, unit: str) -> str:
    if unit == "кг":
        return f"{count / 1000:.1f} кг"
    elif unit == "г":
        return f"{int(count)} г"
    elif unit == "л":
        return f"{count} л"
    else:
        return f"{int(count)} шт"

# 1. Прием данных из WebApp и запуск опроса
@dp.message(F.web_app_data)
async def web_app_data_handler(message: types.Message, state: FSMContext):
    try:
        raw_data = message.web_app_data.data
        data = json.loads(raw_data)
        
        shop_code = data.get("shop", "beer")
        shop_name = SHOP_NAMES.get(shop_code, "Локальна доставка")
        products = data.get("products", {})
        total = data.get("total", 0)

        # Сохраняем первичные данные Корзины в FSM
        await state.update_data(
            shop_name=shop_name,
            total=total,
            products=products
        )

        # Клавиатура выбора дома
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="пров. Балтійський, 1"), KeyboardButton(text="пров. Балтійський, 3")],
                [KeyboardButton(text="пров. Балтійський, 3а"), KeyboardButton(text="пров. Балтійський, 5")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await message.answer("Оберіть ваш **будинок**:", reply_markup=kb, parse_mode="Markdown")
        await state.set_state(OrderFSM.waiting_for_building)

    except Exception as e:
        logging.error(f"Error parsing web_app_data: {e}")
        await message.answer("❌ Сталася помилка при обробці замовлення. Спробуйте ще раз.")

# 2. Выбор дома
@dp.message(OrderFSM.waiting_for_building)
async def process_building(message: types.Message, state: FSMContext):
    await state.update_data(building=message.text)
    await message.answer("Вкажіть номер **під'їзду (парадного)**:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderFSM.waiting_for_entrance)

# 3. Подъезд
@dp.message(OrderFSM.waiting_for_entrance)
async def process_entrance(message: types.Message, state: FSMContext):
    await state.update_data(entrance=message.text)
    await message.answer("Вкажіть **поверх**:")
    await state.set_state(OrderFSM.waiting_for_floor)

# 4. Этаж
@dp.message(OrderFSM.waiting_for_floor)
async def process_floor(message: types.Message, state: FSMContext):
    await state.update_data(floor=message.text)
    await message.answer("Вкажіть номер **квартири**:")
    await state.set_state(OrderFSM.waiting_for_apt)

# 5. Квартира -> Запрос телефона
@dp.message(OrderFSM.waiting_for_apt)
async def process_apt(message: types.Message, state: FSMContext):
    await state.update_data(apt=message.text)
    
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Надіслати свій номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Надішліть ваш **номер телефону** (натисніть кнопку або введіть вручну):", reply_markup=kb)
    await state.set_state(OrderFSM.waiting_for_phone)

# 6. Телефон -> Способ оплаты
@dp.message(OrderFSM.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Безготівкова (карткою)")],
            [KeyboardButton(text="💵 Готівкою при отриманні")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Оберіть спосіб **оплати**:", reply_markup=kb)
    await state.set_state(OrderFSM.waiting_for_payment)

# 7. Оплата -> Промокод
@dp.message(OrderFSM.waiting_for_payment)
async def process_payment(message: types.Message, state: FSMContext):
    payment_choice = message.text
    await state.update_data(payment=payment_choice)

    # Уведомление при выборе безнала
    if "Безготівкова" in payment_choice or "карткою" in payment_choice:
        await message.answer("ℹ️ Після формування замовлення менеджер надішле вам посилання/реквізити для оплати.")

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="➡️ Пропустити")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        "У вас є **промокод на знижку**?\n"
        "Введіть його сюди або натисніть **Пропустити**:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(OrderFSM.waiting_for_promo)

# 8. Промокод -> Финал (Формирование чеков для клиента и админов)
@dp.message(OrderFSM.waiting_for_promo)
async def process_promo(message: types.Message, state: FSMContext):
    promo_input = message.text.strip().upper()
    data = await state.get_data()
    
    discount_percent = 0
    discount_applied = False

    if promo_input in PROMO_CODES:
        discount_percent = PROMO_CODES[promo_input]
        discount_applied = True
    elif promo_input != "➡️ ПРОПУСТИТИ" and promo_input != "ПРОПУСТИТИ":
        await message.answer("⚠️ Промокод недійсний або застарів. Оформлюємо замовлення без знижки.")

    # Сборка списка товаров
    products = data.get("products", {})
    subtotal = data.get("total", 0)

    items_text = ""
    for p_id, item in products.items():
        name = item.get("name", "Товар")
        price = item.get("price", 0)
        count = item.get("count", 1)
        unit = item.get("unit", "шт")
        qty_str = format_qty(count, unit)
        
        # Расчет позиции
        if unit == "г":
            item_sum = round(price * (count / 50)) if p_id.startswith("s") else round(price * (count / 100))
        elif unit == "кг":
            item_sum = round(price * (count / 500))
        elif unit == "л":
            item_sum = round(price * (count / 0.5))
        else:
            item_sum = round(price * count)

        items_text += f"• **{name}** — {qty_str} × {price} грн = {item_sum} грн\n"

    # Подсчет итоговой суммы со скидкой
    if discount_applied:
        discount_amount = round((subtotal * discount_percent) / 100)
        final_total = subtotal - discount_amount
        total_text = (
            f"Сума: {subtotal} грн\n"
            f"🎁 **Знижка ({discount_percent}% по промокоду):** -{discount_amount} грн\n"
            f"💰 **Разом до сплати:** {final_total} грн"
        )
    else:
        final_total = subtotal
        total_text = f"💰 **Разом до сплати:** {final_total} грн"

    # Данные клиента для связи
    username = f"@{message.from_user.username}" if message.from_user.username else "Не вказано (немає username)"
    
    # ------------------ ЧЕК ДЛЯ КЛИЕНТА ------------------
    client_msg = (
        "✅ **Замовлення успішно прийнято!**\n\n"
        f"🏪 **Магазин:** {data['shop_name']}\n"
        f"🛒 **Ваші товари:**\n{items_text}\n"
        f"{total_text}\n\n"
        f"📍 **Адреса доставки:** {data['building']}, парадне {data['entrance']}, пов. {data['floor']}, кв. {data['apt']}\n"
        f"📞 **Телефон:** {data['phone']}\n"
        f"💳 **Оплата:** {data['payment']}\n\n"
        "🚚 Менеджер зв'яжеться з вами найближчим часом!"
    )

    await message.answer(client_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

    # ------------------ ЧЕК ДЛЯ МЕНЕДЖЕРОВ В ГРУППУ ------------------
    admin_msg = (
        f"🚨 **НОВЕ ЗАМОВЛЕННЯ!**\n"
        f"🏪 **Магазин:** {data['shop_name']}\n"
        f"👤 **Клієнт:** {message.from_user.full_name} ({username})\n\n"
        f"🛒 **Склад замовлення:**\n{items_text}\n"
        f"{total_text}\n\n"
        f"📍 **Адреса:** {data['building']}, парадне {data['entrance']}, пов. {data['floor']}, кв. {data['apt']}\n"
        f"📞 **Тел:** {data['phone']}\n"
        f"💳 **Спосіб оплати:** {data['payment']}\n"
    )

    if discount_applied:
        admin_msg += f"🎟️ **Застосовано промокод:** `{promo_input}`\n"

    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")

    # Сбрасываем состояние
    await state.clear()

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))

import logging
import json
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove

BOT_TOKEN = "ТВОЙ_ТОКЕН_БОТА"
ADMIN_CHAT_ID = -1001234567890  # ID группы/чата операторов
WEBAPP_URL = "https://your-domain.com/index.html"  # Ссылка на твой HTML WebApp

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Маппинг названий магазинов для красивого чека
SHOP_NAMES = {
    "beer": "🍺 BeerMarket",
    "pizza": "🍕 BigPapa",
    "galia": "🥟 Галія",
    "fruits": "🍎 Фрукти & Овочі"
}

# FSM Состояния
class OrderFSM(StatesGroup):
    waiting_for_entrance = State()
    waiting_for_floor = State()
    waiting_for_apt = State()
    waiting_for_phone = State()
    waiting_for_payment = State()

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
        "У нас ви можете замовити:\n"
        "• 🍺 **BeerMarket** (Крафтове та розливне пиво, закуски)\n"
        "• 🍕 **BigPapa** (Піца та напої)\n"
        "• 🥟 **Галія** (Заморожені напівфабрикати)\n"
        "• 🍎 **Фрукти & Овочі** (Свіжі овочі та фрукти)\n\n"
        "Натисніть кнопку нижче, щоб відкрити каталог та зробити замовлення:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# Форматирование количества товаров для чека
def format_qty(count: float, unit: str) -> str:
    if unit == "кг":
        return f"{count / 1000:.1f} кг"
    elif unit == "г":
        return f"{int(count)} г"
    elif unit == "л":
        return f"{count} л"
    else:
        return f"{int(count)} шт"

# Прием данных из WebApp
@dp.message(F.web_app_data)
async def web_app_data_handler(message: types.Message, state: FSMContext):
    try:
        raw_data = message.web_app_data.data
        data = json.loads(raw_data)
        
        shop_code = data.get("shop", "beer")
        shop_name = SHOP_NAMES.get(shop_code, "Локальна доставка")
        products = data.get("products", {})
        total = data.get("total", 0)

        # Формируем чек замовлення
        order_text = f"🏪 **Магазин:** {shop_name}\n"
        order_text += "🛒 **Ваше замовлення:**\n\n"

        for p_id, item in products.items():
            name = item.get("name", "Товар")
            price = item.get("price", 0)
            count = item.get("count", 1)
            unit = item.get("unit", "шт")

            qty_str = format_qty(count, unit)
            
            # Расчет стоимости позиции
            if unit == "г":
                item_sum = round(price * (count / 50)) if p_id.startswith("s") else round(price * (count / 100))
            elif unit == "кг":
                item_sum = round(price * (count / 500))
            elif unit == "л":
                item_sum = round(price * (count / 0.5))
            else:
                item_sum = round(price * count)

            order_text += f"• **{name}** — {qty_str} × {price} грн = {item_sum} грн\n"
        
        order_text += f"\n💰 **Разом:** {total} грн"

        # Сохраняем данные в FSM
        await state.update_data(
            shop_name=shop_name,
            cart_text=order_text,
            total=total,
            products=products
        )

        await message.answer(
            f"{order_text}\n\n"
            "Чудово! Вкажіть, будь ласка, **номер під'їзду (парадного)**:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(OrderFSM.waiting_for_entrance)

    except Exception as e:
        logging.error(f"Error parsing web_app_data: {e}")
        await message.answer("❌ Сталася помилка при обробці замовлення. Спробуйте ще раз.")

@dp.message(OrderFSM.waiting_for_entrance)
async def process_entrance(message: types.Message, state: FSMContext):
    await state.update_data(entrance=message.text)
    await message.answer("Вкажіть **поверх**:")
    await state.set_state(OrderFSM.waiting_for_floor)

@dp.message(OrderFSM.waiting_for_floor)
async def process_floor(message: types.Message, state: FSMContext):
    await state.update_data(floor=message.text)
    await message.answer("Вкажіть **номер квартири**:")
    await state.set_state(OrderFSM.waiting_for_apt)

@dp.message(OrderFSM.waiting_for_apt)
async def process_apt(message: types.Message, state: FSMContext):
    await state.update_data(apt=message.text)
    
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поділитися номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Надішліть ваш **номер телефону** для зв'язку:", reply_markup=kb)
    await state.set_state(OrderFSM.waiting_for_phone)

@dp.message(OrderFSM.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Карткою (On-line)")],
            [KeyboardButton(text="💵 Готівкою при отриманні")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Оберіть спосіб оплати:", reply_markup=kb)
    await state.set_state(OrderFSM.waiting_for_payment)

@dp.message(OrderFSM.waiting_for_payment)
async def process_payment(message: types.Message, state: FSMContext):
    payment = message.text
    user_data = await state.get_data()

    # Сообщение клиенту
    final_client_msg = (
        "✅ **Замовлення успішно прийнято!**\n\n"
        f"{user_data['cart_text']}\n\n"
        f"📍 **Адреса:** ЖК Навігатор, парадне {user_data['entrance']}, пов. {user_data['floor']}, кв. {user_data['apt']}\n"
        f"📞 **Телефон:** {user_data['phone']}\n"
        f"💳 **Оплата:** {payment}\n\n"
        "Менеджер зателефонує вам для підтвердження!"
    )

    await message.answer(final_client_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

    # Сообщение оператору в чат
    admin_msg = (
        f"🚨 **НОВЕ ЗАМОВЛЕННЯ!**\n"
        f"Клієнт: @{message.from_user.username or 'без_юзернейма'} ({message.from_user.full_name})\n\n"
        f"{user_data['cart_text']}\n\n"
        f"📍 **Парадне:** {user_data['entrance']} | **Поверх:** {user_data['floor']} | **Кв:** {user_data['apt']}\n"
        f"📞 **Тел:** {user_data['phone']}\n"
        f"💳 **Оплата:** {payment}"
    )

    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")
    await state.clear()

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))

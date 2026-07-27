import logging
import json
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove

BOT_TOKEN = "8872901197:AAFgViAeYRWkPUMk6h7RBZZsoRCXB1jAMbM"
ADMIN_CHAT_ID = 4991707736  # ID группы/чата для заказов
WEBAPP_URL = "https://ecomanyk.github.io/beershop/index.html"  # Ссылка на твой HTML

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# FSM Состояния
class OrderFSM(StatesGroup):
    waiting_for_entrance = State()
    waiting_for_floor = State()
    waiting_for_apt = State()
    waiting_for_phone = State()
    waiting_for_payment = State()

# Кнопки
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍺 Відкрити меню", web_app=WebAppInfo(url=WEBAPP_URL))]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🍺 **Ласкаво просимо до «Пивний Крафт»!**\n\n"
        "Доставка розливного пива, напоїв та закусок по ЖК Навігатор.\n"
        "Мінімальна сума замовлення — **300 грн**.\n\n"
        "Натисніть кнопку нижче, щоб відкрити меню та зробити замовлення:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# Прием данных из WebApp
@dp.message(F.web_app_data)
async def web_app_data_handler(message: types.Message, state: FSMContext):
    try:
        raw_data = message.web_app_data.data
        data = json.loads(raw_data)
        
        products = data.get("products", {})
        total = data.get("total", 0)

        if total < 300:
            await message.answer("⚠️ Мінімальна сума замовлення на доставку — 300 грн.")
            return

        # Формируем текст чека
        order_text = "🛒 **Ваше замовлення:**\n\n"
        for p_id, item in products.items():
            order_text += f"• **{item['name']}** — {item['qty_display']} × {item['price']} грн = {item['sum']} грн\n"
        
        order_text += f"\n💰 **Разом:** {total} грн"

        # Сохраняем в FSM
        await state.update_data(
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
    await message.answer("Вкажіть **номер квартиры**:")
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

    # Финальное сообщение клиенту
    final_client_msg = (
        "✅ **Замовлення успішно прийнято!**\n\n"
        f"{user_data['cart_text']}\n\n"
        f"📍 **Адреса:** ЖК Навігатор, парадне {user_data['entrance']}, пов. {user_data['floor']}, кв. {user_data['apt']}\n"
        f"📞 **Телефон:** {user_data['phone']}\n"
        f"💳 **Оплата:** {payment}\n\n"
        "Кур'єр вже готує замовлення!"
    )

    await message.answer(final_client_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

    # Отправка операторам / в канал
    admin_msg = (
        f"🚨 **НОВЕ ЗАМОВЛЕННЯ (Пивний Крафт)!**\n"
        f"Клієнт: @{message.from_user.username or 'без_юзернейма'} ({message.from_user.full_name})\n\n"
        f"{user_data['cart_text']}\n\n"
        f"📍 **Парадне:** {user_data['entrance']} | **Поверх:** {user_data['floor']} | **Кв:** {user_data['apt']}\n"
        f"📞 **Тел:** {user_data['phone']}\n"
        f"💳 **Спосіб оплати:** {payment}"
    )

    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")
    await state.clear()

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
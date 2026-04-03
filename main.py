import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
import os

load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# O'YIN MA'LUMOTLARI
games = {}

ROLES = {
    "Mafia": {"side": "mafia", "desc": "Tunda o'ldiradi."},
    "Don": {"side": "mafia", "desc": "Komissarni qidiradi."},
    "Sherif": {"side": "civilian", "desc": "Tunda tekshiradi."},
    "Doktor": {"side": "civilian", "desc": "Davolaydi."},
    "Maniak": {"side": "neutral", "desc": "Hamma bilan urushadi."},
    "Tinch aholi": {"side": "civilian", "desc": "Kunduzi ovoz beradi."}
    # Bu yerga yana 14 ta rolni xuddi shunday qo'shish mumkin
}

class MafiaGame:
    def __init__(self):
        self.players = {}  # {user_id: {"name": str, "role": str, "alive": bool}}
        self.phase = "registration" # registration, night, day, voting
        self.votes = {} # {voter_id: target_id}
        self.night_actions = {"kills": [], "heals": [], "checks": []}

@dp.message(Command("newgame"))
async def new_game(message: types.Message):
    chat_id = message.chat.id
    games[chat_id] = MafiaGame()
    
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Qo'shilish", callback_data="join")
    await message.answer("🎮 Mafia Elite: Ro'yxatdan o'tish boshlandi!", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "join")
async def join_handler(callback: types.CallbackQuery):
    game = games.get(callback.message.chat.id)
    if not game or len(game.players) >= 20: return
    
    game.players[callback.from_user.id] = {
        "name": callback.from_user.full_name,
        "role": None,
        "alive": True
    }
    await callback.message.edit_text(f"O'yinchilar: {len(game.players)}/20")

@dp.message(Command("startgame"))
async def start_game(message: types.Message):
    game = games.get(message.chat.id)
    if len(game.players) < 4:
        return await message.answer("Kamida 4 kishi kerak!")

    # ROLLRNI TAQSIMLASH
    p_ids = list(game.players.keys())
    random.shuffle(p_ids)
    
    # Soddalashtirilgan taqsimot (Misol uchun 6 kishilik)
    assigned_roles = ["Mafia", "Sherif", "Doktor"] + ["Tinch aholi"] * (len(p_ids)-3)
    
    for i, p_id in enumerate(p_ids):
        role_name = assigned_roles[i]
        game.players[p_id]["role"] = role_name
        try:
            await bot.send_message(p_id, f"Sizning rolingiz: {role_name}\n{ROLES[role_name]['desc']}")
        except:
            pass

    game.phase = "night"
    await message.answer("🏙 Shahar uyquga ketdi. Tun boshlandi...")
    await start_night(message.chat.id)

async def start_night(chat_id):
    game = games[chat_id]
    # Har bir rolga shaxsiy xabarda tugma yuborish kodi...
    await asyncio.sleep(30) # Tun 30 soniya
    await start_day(chat_id)

async def start_day(chat_id):
    game = games[chat_id]
    game.phase = "day"
    await bot.send_message(chat_id, "🌅 Quyosh chiqdi! Muhokama boshlanadi. Ovoz berish uchun /vote bosing.")

@dp.message(Command("vote"))
async def vote_menu(message: types.Message):
    game = games.get(message.chat.id)
    if game.phase != "day": return
    
    kb = InlineKeyboardBuilder()
    for p_id, data in game.players.items():
        if data["alive"]:
            kb.button(text=data["name"], callback_data=f"v_{p_id}")
    
    await message.answer("Kimni osamiz?", reply_markup=kb.as_markup())

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

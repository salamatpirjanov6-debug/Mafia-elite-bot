import logging
import asyncio
import random
import os
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# Railway Variables: TELEGRAM_BOT_TOKEN
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# O'yin holatlari
class GameState(StatesGroup):
    Registration = State()
    Night = State()
    Day = State()
    Voting = State()

# Global o'yin ma'lumotlari
game_data = {
    "players": {}, # {id: {name, role, alive, action_target, votes_received}}
    "is_active": False,
    "chat_id": None,
    "cycle": 1
}

# Rollar tavsifi
ROLE_INFO = {
    "Tinch aholi": "Sizning vazifangiz mafiyani topish va ularni osish.",
    "Kezuvchi": "Bir kecha davomida shaharni zararsizlantiring. Komissarni uxlatmaslikka harakat qiling!",
    "Serjant": "Komissarga yordam bering. U o'lsa, o'rnini egallaysiz.",
    "Komissar": "Mafiyani toping va yo'q qiling! Birinchi tun otish taqiqlanadi.",
    "Doktor": "O'yinchilarni davolang. O'zingizni faqat 1 marta davolay olasiz.",
    "Daydi": "Tunda kimningdir uyiga borib, qotillikka guvoh bo'lishingiz mumkin.",
    "Afsungar": "Sizni tunda o'ldirishsa, qotilni o'zingiz bilan olib ketasiz!",
    "Don": "Mafiya boshlig'isiz. Kimni o'ldirishni hal qiling.",
    "Mafiya": "Shaharni yo'q qiling.",
    "Advokat": "Mafiyani himoya qiling, komissar uni tinch aholi deb ko'radi.",
    "Qotil": "Faqat o'zingiz tirik qolsangiz g'alaba qozonasiz!",
    "Bo'ri": "Siz reenkarnatsiya qila olasiz. Kim sizni birinchi o'ldirsa, o'shaning jamoasiga o'tasiz."
}

@dp.message_handler(commands=['start_mafia'], state="*")
async def cmd_start(message: types.Message):
    if game_data["is_active"]:
        return await message.reply("O'yin allaqachon boshlangan!")
    
    game_data["is_active"] = True
    game_data["chat_id"] = message.chat.id
    game_data["players"] = {}
    await GameState.Registration.set()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("O'yinga qo'shilish ✋", callback_data="join_game"))
    await message.answer("<b>Mafiya o'yini boshlandi!</b>\nRo'yxatga olish ketmoqda...", reply_markup=markup)

@dp.callback_query_handler(text="join_game", state=GameState.Registration)
async def join_callback(call: types.CallbackQuery):
    if call.from_user.id in game_data["players"]:
        return await call.answer("Siz allaqachon qo'shilgansiz!", show_alert=True)
    
    game_data["players"][call.from_user.id] = {
        "name": call.from_user.first_name,
        "role": None,
        "alive": True,
        "target": None,
        "protected_by_lawyer": False,
        "healed": False,
        "blocked": False
    }
    await call.answer("Siz qo'shildingiz!")
    await bot.send_message(game_data["chat_id"], f"✅ {call.from_user.first_name} o'yinga kirdi. Jami: {len(game_data['players'])}")

@dp.message_handler(commands=['go'], state=GameState.Registration)
async def start_game(message: types.Message):
    players_count = len(game_data["players"])
    if players_count < 4:
        return await message.reply("Kamida 4 kishi kerak!")

    # Rollarni taqsimlash
    ids = list(game_data["players"].keys())
    random.shuffle(ids)
    
    # Rollar ro'yxatini dinamik yaratish
    all_roles = ["Don", "Komissar", "Doktor", "Mafiya", "Qotil", "Afsungar", "Bo'ri", "Kezuvchi", "Serjant", "Advokat"]
    remaining = players_count - len(all_roles)
    roles_to_assign = all_roles + (["Tinch aholi"] * max(0, remaining))
    
    for i, p_id in enumerate(ids):
        role = roles_to_assign[i]
        game_data["players"][p_id]["role"] = role
        try:
            await bot.send_message(p_id, f"Sizning rolingiz: <b>{role}</b>\n{ROLE_INFO.get(role, '')}")
        except:
            await message.answer(f"⚠️ {game_data['players'][p_id]['name']} botga start bosmagan!")

    await message.answer("<b>Rollar tarqatildi!</b>\nShahar uyquga ketmoqda... 🌃")
    await asyncio.sleep(3)
    await start_night()

async def start_night():
    await GameState.Night.set()
    for p_id, data in game_data["players"].items():
        if data["alive"] and data["role"] != "Tinch aholi":
            markup = types.InlineKeyboardMarkup(row_width=2)
            for t_id, t_data in game_data["players"].items():
                if t_id != p_id and t_data["alive"]:
                    markup.add(types.InlineKeyboardButton(t_data["name"], callback_data=f"night_{t_id}"))
            
            await bot.send_message(p_id, f"Tungi vazifangizni bajaring ({data['role']}):", reply_markup=markup)

@dp.callback_query_handler(state=GameState.Night, text_startswith="night_")
async def handle_night_action(call: types.CallbackQuery):
    target_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    game_data["players"][user_id]["target"] = target_id
    await call.message.edit_text(f"Tanlov qabul qilindi: {game_data['players'][target_id]['name']}")

    # Hamma harakat qilib bo'lganini tekshirish
    active_players = [p for p in game_data["players"].values() if p["alive"] and p["role"] != "Tinch aholi"]
    done_players = [p for p in active_players if p["target"] is not None]
    
    if len(active_players) == len(done_players):
        await process_night_results()

async def process_night_results():
    players = game_data["players"]
    deaths = []
    
    # 1. Bloklash (Kezuvchi)
    kezuvchi = next((p for p in players.values() if p["role"] == "Kezuvchi" and p["alive"]), None)
    if kezuvchi and kezuvchi["target"]:
        players[kezuvchi["target"]]["blocked"] = True
    
    # 2. Hujumlar va Himoyalar
    for pid, p in players.items():
        if not p["alive"] or p["blocked"]: continue
        
        target = p["target"]
        if not target: continue
        
        if p["role"] in ["Don", "Mafiya", "Qotil"]:
            # Doktor yoki Advokat himoyasini tekshirish
            if players[target]["role"] == "Bo'ri":
                # BO'RI MANTIQI
                if p["role"] in ["Don", "Mafiya"]:
                    players[target]["role"] = "Mafiya"
                    await bot.send_message(target, "Siz endi Mafiyasiz! 🤵🏼")
                elif p["role"] == "Qotil":
                    deaths.append(target)
            elif target != next((id for id, pl in players.items() if pl["role"] == "Doktor" and pl.get("target") == target), None):
                 deaths.append(target)

        # AFSUNGAR MANTIQI
        if target in deaths and players[target]["role"] == "Afsungar":
            deaths.append(pid) # Uni o'ldirgan ham o'ladi

    # O'lganlarni yangilash
    unique_deaths = list(set(deaths))
    for d_id in unique_deaths:
        players[d_id]["alive"] = False

    msg = "Tong otdi! 🌅\n\n"
    if unique_deaths:
        for d_id in unique_deaths:
            msg += f"💀 {players[d_id]['name']} vafot etdi. U {players[d_id]['role']} edi.\n"
    else:
        msg += "Hech kim vafot etmadi. 🕊"
    
    await bot.send_message(game_data["chat_id"], msg)
    await start_day()

async def start_day():
    await GameState.Day.set()
    await bot.send_message(game_data["chat_id"], "Muhokama boshlandi (2 minut). So'ng ovoz berish!")
    await asyncio.sleep(120) # Muhokama vaqti
    await start_voting()

async def start_voting():
    await GameState.Voting.set()
    markup = types.InlineKeyboardMarkup()
    for pid, p in game_data["players"].items():
        if p["alive"]:
            markup.add(types.InlineKeyboardButton(p["name"], callback_data=f"vote_{pid}"))
    await bot.send_message(game_data["chat_id"], "Ovoz bering! Kimni osamiz?", reply_markup=markup)

# ... (Ovoz berish va g'olibni aniqlash funksiyalari davom etadi)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

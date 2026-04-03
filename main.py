import logging
import asyncio
import random
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# --- SOZLAMALAR ---
API_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7718919427:AAH0p85Lh_XFsc-2n0L8O956T8Xw68Y9NqE")
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# O'yin ma'lumotlari bazasi (Vaqtinchalik xotira)
games = {}

async def on_startup(dp):
    await bot.set_my_commands([
        types.BotCommand("create_game", "Yangi o'yin yaratish"),
        types.BotCommand("start", "Botni ishga tushirish")
    ])

# --- YORDAMCHI FUNKSIYALAR ---

def init_game(chat_id, admin_id):
    games[chat_id] = {
        "status": "lobby",
        "admin_id": admin_id,
        "players": {},
        "votes": {},
        "night_actions": {"kill": None, "heal": None, "check": None, "don_check": None},
        "cycle": 1,
        "history": []
    }

def get_alive_players(chat_id):
    return {uid: p for uid, p in games[chat_id]["players"].items() if p["alive"]}

# --- BUYRUQLAR ---

@dp.message_handler(commands=['create_game'])
async def cmd_create(message: types.Message):
    if message.chat.type == 'private':
        return await message.answer("❌ O'yinni guruhda boshlang!")
    
    init_game(message.chat.id, message.from_user.id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Qo'shilish ➕", callback_data=f"join_{message.chat.id}"),
        types.InlineKeyboardButton("O'yinni boshlash ▶️", callback_data=f"start_game_{message.chat.id}")
    )
    
    await message.answer(
        f"🎮 <b>Yangi Mafia o'yini!</b>\n\n"
        f"Admin: {message.from_user.first_name}\n"
        f"Minimal o'yinchilar: 4 ta\n\n"
        f"<i>Qatnashish uchun tugmani bosing va botga o'tib /start bosing!</i>", 
        reply_markup=markup
    )

@dp.callback_query_handler(lambda c: c.data.startswith('join_'))
async def join_player(call: types.CallbackQuery):
    chat_id = int(call.data.split('_')[1])
    uid = call.from_user.id
    
    if chat_id not in games: return await call.answer("O'yin topilmadi.")
    if uid in games[chat_id]["players"]: return await call.answer("Siz kirdingiz!")

    try:
        await bot.send_message(uid, "✅ Siz o'yinga muvaffaqiyatli qo'shildingiz!")
        games[chat_id]["players"][uid] = {"name": call.from_user.first_name, "role": None, "alive": True}
        
        count = len(games[chat_id]["players"])
        text = f"🎮 <b>O'yinchilar: {count} ta</b>\n" + "\n".join([f"👤 {p['name']}" for p in games[chat_id]['players'].values()])
        await call.message.edit_text(text, reply_markup=call.message.reply_markup)
    except:
        await call.answer("Avval botning o'ziga kirib /start bosing!", show_alert=True)

@dp.callback_query_handler(lambda c: c.data.startswith('start_game_'))
async def start_game(call: types.CallbackQuery):
    chat_id = int(call.data.split('_')[2])
    game = games[chat_id]
    
    if call.from_user.id != game["admin_id"]:
        return await call.answer("Faqat admin boshlay oladi!", show_alert=True)
    if len(game["players"]) < 4:
        return await call.answer("Odam yetarli emas! (Min: 4)", show_alert=True)

    # Rollarni taqsimlash mantiqi
    uids = list(game["players"].keys())
    random.shuffle(uids)
    
    roles = ["mafiya", "komissar", "doktor"]
    if len(uids) >= 6: roles.append("don")
    
    for i, uid in enumerate(uids):
        if i < len(roles):
            game["players"][uid]["role"] = roles[i]
        else:
            game["players"][uid]["role"] = "tinch"
        
        # Shaxsiyga rolni yuborish
        role_name = game["players"][uid]["role"].upper()
        await bot.send_message(uid, f"🎭 Sizning rolingiz: <b>{role_name}</b>")

    await call.message.edit_text("🎲 <b>Rollar tarqatildi! O'yin boshlanmoqda...</b>")
    await asyncio.sleep(3)
    await start_night(chat_id)

# --- TUNGI BOSQICH ---

async def start_night(chat_id):
    games[chat_id]["status"] = "night"
    await bot.send_message(chat_id, f"🌃 <b>{games[chat_id]['cycle']}-tun boshlandi.</b>\nShahar uyquga ketdi...")
    
    players = get_alive_players(chat_id)
    
    # Har bir rolga o'z menyusini yuborish
    for uid, data in players.items():
        markup = types.InlineKeyboardMarkup()
        for t_uid, t_data in players.items():
            markup.add(types.InlineKeyboardButton(t_data["name"], callback_data=f"act_{data['role']}_{chat_id}_{t_uid}"))
        
        if data["role"] in ["mafiya", "don"]:
            await bot.send_message(uid, "🌃 <b>Mafiya vaqti!</b> Kimni o'ldiramiz?", reply_markup=markup)
        elif data["role"] == "doktor":
            await bot.send_message(uid, "💊 <b>Shifokor vaqti!</b> Kimni davolaysiz?", reply_markup=markup)
        elif data["role"] == "komissar":
            await bot.send_message(uid, "🔍 <b>Komissar vaqti!</b> Kimni tekshirasiz?", reply_markup=markup)

    await asyncio.sleep(40) # Tungi harakatlar uchun vaqt
    await start_day(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith('act_'))
async def handle_night_actions(call: types.CallbackQuery):
    _, role, chat_id, target_id = call.data.split('_')
    chat_id, target_id = int(chat_id), int(target_id)
    
    if role in ['mafiya', 'don']:
        games[chat_id]["night_actions"]["kill"] = target_id
    elif role == 'doktor':
        games[chat_id]["night_actions"]["heal"] = target_id
    elif role == 'komissar':
        is_maf = games[chat_id]["players"][target_id]["role"] in ["mafiya", "don"]
        res = "MAFIYA 🕵️‍♂️" if is_maf else "Tinch aholi ✅"
        return await call.message.edit_text(f"Natija: {res}")

    await call.message.edit_text("✅ Tanlovingiz qabul qilindi.")

# --- KUNDUZGI BOSQICH ---

async def start_day(chat_id):
    game = games[chat_id]
    game["status"] = "day"
    
    kill = game["night_actions"]["kill"]
    heal = game["night_actions"]["heal"]
    
    msg = f"☀️ <b>{game['cycle']}-kun boshlandi!</b>\n\n"
    if kill and kill != heal:
        victim = game["players"][kill]["name"]
        game["players"][kill]["alive"] = False
        msg += f"💀 Daxshat! Kechasi <b>{victim}</b> shafqatsizlarcha o'ldirildi."
    else:
        msg += "😇 Kechasi tinch o'tdi, hech kim zarar ko'rmadi."

    await bot.send_message(chat_id, msg)
    if await check_finish(chat_id): return

    await bot.send_message(chat_id, "🗣 <b>Muhokama vaqti (60s).</b> Mafiyani toping!")
    await asyncio.sleep(60)
    
    # Ovoz berish
    markup = types.InlineKeyboardMarkup()
    for uid, data in get_alive_players(chat_id).items():
        markup.add(types.InlineKeyboardButton(data["name"], callback_data=f"vote_{chat_id}_{uid}"))
    
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish!</b> Kimni haydaymiz?", reply_markup=markup)
    game["votes"] = {}
    await asyncio.sleep(30)
    await end_voting(chat_id)

async def end_voting(chat_id):
    game = games[chat_id]
    if not game["votes"]:
        await bot.send_message(chat_id, "🚫 Hech kim ovoz bermadi, hech kim haydalmadi.")
    else:
        v_list = list(game["votes"].values())
        target = max(set(v_list), key=v_list.count)
        game["players"][target]["alive"] = False
        await bot.send_message(chat_id, f"🗳 Ovozlar natijasiga ko'ra <b>{game['players'][target]['name']}</b> haydaldi.")

    if await check_finish(chat_id): return
    
    game["cycle"] += 1
    game["night_actions"] = {"kill": None, "heal": None, "check": None}
    await start_night(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith('vote_'))
async def handle_vote(call: types.CallbackQuery):
    _, chat_id, t_id = call.data.split('_')
    games[int(chat_id)]["votes"][call.from_user.id] = int(t_id)
    await call.answer("Ovozingiz olindi!")

async def check_finish(chat_id):
    p = games[chat_id]["players"]
    maf = [u for u, d in p.items() if d["alive"] and d["role"] in ["mafiya", "don"]]
    civ = [u for u, d in p.items() if d["alive"] and d["role"] not in ["mafiya", "don"]]
    
    if not maf:
        await bot.send_message(chat_id, "🎉 <b>G'alaba!</b> Tinch aholi barcha mafiyalarni yo'q qildi!")
        return True
    if len(maf) >= len(civ):
        await bot.send_message(chat_id, "💣 <b>Mafiya g'alaba qozondi!</b> Shahar endi ularning qo'lida.")
        return True
    return False

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

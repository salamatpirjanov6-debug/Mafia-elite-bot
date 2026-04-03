import logging
import asyncio
import random
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# --- SOZLAMALAR ---
# Variables name: TELEGRAM_BOT_TOKEN
API_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7718919427:AAH0p85Lh_XFsc-2n0L8O956T8Xw68Y9NqE")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- O'YIN MA'LUMOTLARI ---
games = {}

ROLES_DESC = {
    "tinch": "👨🏼 Tinch aholi: Mafiyani toping va kunduzi osing.",
    "don": "🤵🏻 Don: Mafiya boshlig'i. Komissar sizni topa olmaydi.",
    "mafiya": "🤵🏼 Mafiya: Tunda shaharni suiqasd qiling.",
    "afsungar": "🧞‍♂️ Afsungar: O'lsangiz, qotilingizni ham olib ketasiz!",
    "komissar": "🕵🏻‍♂️ Komissar: Mafiyani tekshiring va yo'q qiling.",
    "doktor": "👨🏻‍⚕️ Doktor: O'yinchilarni davolang.",
    "qotil": "🔪 Qotil: Faqat o'zingiz tirik qolishingiz kerak.",
    "serjant": "👮🏻‍♂️ Serjant: Komissar o'lsa, uning o'rnini egallaysiz.",
    "kezuvchi": "💃 Kezuvchi: Tunda bir o'yinchini uxlatib qo'yasiz.",
    "daydi": "🧙‍♂️ Daydi: Tungi qotilliklarga guvoh bo'ling.",
    "advokat": "👨‍💼 Advokat: Mafiyani himoya qiling.",
    "bori": "🐺 Bo'ri: Kim sizni otsa, o'shaning jamoasiga o'tasiz."
}

def init_game(chat_id):
    games[chat_id] = {
        "status": "none",
        "players": {},
        "night_actions": {"killed": [], "healed": None, "checked": None},
        "day_count": 0
    }

# --- ROLLARI TAQSIMLASH MANTIQI ---
def distribute_roles(player_ids):
    n = len(player_ids)
    random.shuffle(player_ids)
    assigned = {}

    # Majburiy rollar
    roles_pool = []
    
    # 1. Mafiya jamoasi (Siz aytganingizdek: 1 Don + 5 Mafiya)
    roles_pool.append("don")
    for _ in range(5):
        if len(roles_pool) < n: roles_pool.append("mafiya")

    # 2. Afsungarlar (Odam soniga qarab 2-3 ta)
    afsungar_count = 3 if n >= 15 else 2
    for _ in range(afsungar_count):
        if len(roles_pool) < n: roles_pool.append("afsungar")

    # 3. Muhim yordamchilar
    important = ["komissar", "doktor", "qotil", "serjant", "kezuvchi"]
    for r in important:
        if len(roles_pool) < n: roles_pool.append(r)

    # 4. Qolgan hamma Tinch aholi
    while len(roles_pool) < n:
        roles_pool.append("tinch")

    # Tasodifiy biriktirish
    for i, uid in enumerate(player_ids):
        assigned[uid] = roles_pool[i]
    
    return assigned

# --- KOMANDALAR ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if message.chat.type == 'private':
        await message.answer("🎩 Mafia olamiga xush kelibsiz! O'yinni guruhda /create_game orqali boshlang.")
    else:
        await message.answer("O'yinni boshlash uchun /create_game yozing.")

@dp.message_handler(commands=['create_game'])
async def create_game(message: types.Message):
    chat_id = message.chat.id
    init_game(chat_id)
    games[chat_id]["status"] = "lobby"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("O'yinga qo'shilish ➕", callback_data=f"join_{chat_id}"))
    
    await message.answer("🎮 <b>Yangi Mafia o'yini!</b>\n\nQatnashuvchilar tugmani bosing.", reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data.startswith('join_'))
async def join_callback(call: types.CallbackQuery):
    chat_id = int(call.data.split('_')[1])
    uid = call.from_user.id
    
    if chat_id not in games or games[chat_id]["status"] != "lobby":
        return await call.answer("Ro'yxatga olish tugagan!")
    
    if uid in games[chat_id]["players"]:
        return await call.answer("Siz ro'yxatdasiz.")

    try:
        await bot.send_message(uid, "Siz Mafia o'yiniga qo'shildingiz! Rollar shu yerga yuboriladi.")
    except:
        return await call.answer("Botga shaxsiy xabar yuborib bo'lmayapti! /start bosing.", show_alert=True)

    games[chat_id]["players"][uid] = {"name": call.from_user.first_name, "role": None, "is_alive": True}
    
    count = len(games[chat_id]["players"])
    await call.message.edit_text(f"🎮 <b>O'yinchilar: {count} ta</b>\n" + 
                               "\n".join([f"👤 {p['name']}" for p in games[chat_id]["players"].values()]),
                               reply_markup=call.message.reply_markup)

@dp.message_handler(commands=['start_game'])
async def start_game(message: types.Message):
    chat_id = message.chat.id
    game = games.get(chat_id)
    
    if not game or game["status"] != "lobby": return
    if len(game["players"]) < 12: # Siz aytgan rollar uchun kamida 12 kishi kerak
        return await message.answer("O'yin uchun kamida 12 kishi kerak (5 mafiya, 1 don va tinch aholi uchun).")

    game["status"] = "night"
    player_roles = distribute_roles(list(game["players"].keys()))
    
    for uid, role in player_roles.items():
        game["players"][uid]["role"] = role
        try:
            await bot.send_message(uid, f"🎭 Sizning rolingiz: <b>{role.upper()}</b>\n\n{ROLES_DESC.get(role)}")
        except: pass

    await message.answer("🎲 Rollar tarqatildi! Tun boshlanmoqda...")
    await asyncio.sleep(3)
    await start_night(chat_id)

async def start_night(chat_id):
    game = games[chat_id]
    game["status"] = "night"
    game["night_actions"] = {"killed": [], "healed": None}
    
    await bot.send_message(chat_id, "🌃 <b>Tun boshlandi. Shahar uyquga ketdi...</b>")

    for uid, p in game["players"].items():
        if not p["is_alive"]: continue
        
        # Faqat harakat qila oladigan rollarga tugma yuborish
        if p["role"] in ["mafiya", "don", "qotil", "doktor", "komissar"]:
            markup = types.InlineKeyboardMarkup()
            for tid, tp in game["players"].items():
                if tp["is_alive"] and tid != uid:
                    markup.add(types.InlineKeyboardButton(tp["name"], callback_data=f"night_{chat_id}_{tid}"))
            
            try:
                await bot.send_message(uid, "Tungi harakatingizni tanlang:", reply_markup=markup)
            except: pass

    await asyncio.sleep(40)
    await end_night(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith('night_'))
async def night_callback(call: types.CallbackQuery):
    data = call.data.split('_')
    chat_id, target_id = int(data[1]), int(data[2])
    uid = call.from_user.id
    game = games.get(chat_id)
    
    if not game or game["status"] != "night": return
    
    role = game["players"][uid]["role"]
    if role in ["mafiya", "don", "qotil"]:
        game["night_actions"]["killed"].append(target_id)
    elif role == "doktor":
        game["night_actions"]["healed"] = target_id
        
    await call.message.edit_text("Tanlov qabul qilindi ✅")
    await call.answer()

async def end_night(chat_id):
    game = games[chat_id]
    game["status"] = "day"
    killed = set(game["night_actions"]["killed"])
    healed = game["night_actions"]["healed"]
    
    if healed in killed:
        killed.remove(healed)

    msg = "☀️ <b>Kun yorishdi!</b>\n\n"
    if not killed:
        msg += "Xushxabar! Tunda hech kim jabrlanmadi."
    else:
        for kid in killed:
            game["players"][kid]["is_alive"] = False
            msg += f"💀 <b>{game['players'][kid]['name']}</b> o'ldirildi. U {game['players'][kid]['role']} edi.\n"

    await bot.send_message(chat_id, msg)
    # G'alaba tekshiruvi va kunlik muhokama bu yerda davom etadi...

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

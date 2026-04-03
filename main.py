import logging
import asyncio
import random
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.deep_linking import get_start_link

# 1. SOZLAMALAR
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Ma'lumotlar bazasi va O'yin xotirasi
user_db = {} 
games = {}

# --- YORDAMCHI FUNKSIYALAR ---

def get_user_data(uid):
    if uid not in user_db:
        user_db[uid] = {'money': 100, 'wins': 0, 'losses': 0, 'total': 0, 'shield': 0, 'fake_id': 0}
    return user_db[uid]

def get_mention(uid, name):
    return f"<a href='tg://user?id={uid}'>{name}</a>"

def get_bot_btn(chat_id=None):
    kb = InlineKeyboardMarkup()
    bot_username = "mafia_bot" # O'zingizning botingiz usernamesini yozing
    kb.add(InlineKeyboardButton("🤖 Botga o'tish", url=f"https://t.me/{bot_username}"))
    if chat_id:
        # Guruhga qaytish tugmasi (username bo'lsa osonroq)
        if games.get(chat_id) and games[chat_id].get('group_username'):
            kb.add(InlineKeyboardButton("⬅️ Guruhga qaytish", url=f"https://t.me/{games[chat_id]['group_username']}"))
    return kb

def get_reg_text(chat_id):
    game = games[chat_id]
    text = f"📢 <b>Mafia o'yini boshlanmoqda!</b>\n\n"
    text += f"⏰ Vaqt: <b>{game['timer']} soniya</b> qoldi.\n"
    text += f"👥 Ro'yxat: <b>{len(game['players'])} kishi</b>\n\n"
    for i, (uid, data) in enumerate(game['players'].items(), 1):
        text += f"{i}. {data['name']}\n"
    return text

# --- BUYRUQLAR VA RO'YXATDAN O'TISH ---

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    if message.chat.type == 'private': return
    chat_id = message.chat.id
    games[chat_id] = {
        'players': {}, 'state': 'joining', 'timer': 45, 'reg_msg_id': None,
        'night_actions': {}, 'votes': {}, 'jury': {'l': [], 'd': []},
        'group_username': message.chat.username
    }
    
    link = await get_start_link(payload=f"join_{chat_id}", encode=False)
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🎮 Qo'shilish", url=link),
        InlineKeyboardButton("🚀 Boshlash", callback_data=f"startnow_{chat_id}")
    )
    
    msg = await message.answer(get_reg_text(chat_id), reply_markup=kb)
    games[chat_id]['reg_msg_id'] = msg.message_id
    
    while games[chat_id]['timer'] > 0 and games[chat_id]['state'] == 'joining':
        await asyncio.sleep(5)
        games[chat_id]['timer'] -= 5
        try: await bot.edit_message_text(get_reg_text(chat_id), chat_id, msg.message_id, reply_markup=kb)
        except: pass
    
    if games[chat_id]['state'] == 'joining':
        if len(games[chat_id]['players']) >= 4: await start_game_logic(chat_id)
        else: await message.answer("⚠️ O'yinchilar yetarli emas!")

@dp.message_handler(commands=['time_uzaytirish'])
async def extend_time(message: types.Message):
    cid = message.chat.id
    if cid in games and games[cid]['state'] == 'joining':
        games[cid]['timer'] += 10
        await message.answer("➕ 10 soniya qo'shildi!")

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    get_user_data(uid)
    args = message.get_args()
    
    if args and args.startswith('join_'):
        cid = int(args.split('_')[1])
        if cid in games and games[cid]['state'] == 'joining':
            games[cid]['players'][uid] = {'name': message.from_user.full_name, 'is_alive': True, 'role': None}
            await message.answer("✅ Ro'yxatga qo'shildingiz!", reply_markup=get_bot_btn(cid))
            return

    kb = ReplyKeyboardMarkup(resize_keyboard=True).row("👤 Profil", "🛒 Do'kon").row("📜 Qoidalar")
    await message.answer("Xush kelibsiz! Faqat botda menyulardan foydalana olasiz.", reply_markup=kb)

# --- PROFIL VA DO'KON (FAQAT BOTDA) ---

@dp.message_handler(lambda m: m.text in ["👤 Profil", "🛒 Do'kon"])
async def bot_menus(message: types.Message):
    if message.chat.type != 'private': return
    uid = message.from_user.id
    u = get_user_data(uid)
    
    if message.text == "👤 Profil":
        text = (f"<b>👤 Profilingiz:</b>\n💰 Balans: {u['money']}$\n"
                f"🏆 Yutuq: {u['wins']} | ❌ Mag'lubiyat: {u['losses']}\n"
                f"🛡 Himoya: {u['shield']} ta | 📑 Soxta hujjat: {u['fake_id']} ta")
        await message.answer(text)
    
    elif message.text == "🛒 Do'kon":
        kb = InlineKeyboardMarkup().row(
            InlineKeyboardButton("🛡 Himoya (200$)", callback_data="buy_shield"),
            InlineKeyboardButton("📑 Soxta hujjat (250$)", callback_data="buy_fake_id")
        )
        await message.answer("🛒 Do'kon: Kerakli narsani tanlang:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'))
async def buy_process(callback: types.CallbackQuery):
    u = get_user_data(callback.from_user.id)
    item = callback.data.replace('buy_', '')
    price = 200 if item == 'shield' else 250
    
    if u['money'] >= price:
        u['money'] -= price
        u[item] += 1
        await callback.answer("✅ Sotib olindi!", show_alert=True)
    else:
        await callback.answer("❌ Mablag' yetarli emas!", show_alert=True)

# --- O'YIN JARAYONI ---

async def start_game_logic(chat_id):
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)
    
    # Rollar: Don, Doktor, Komissar va qolganlar Tinch aholi
    game['players'][uids[0]]['role'], game['players'][uids[0]]['role_name'] = 'don', "Don"
    game['players'][uids[1]]['role'], game['players'][uids[1]]['role_name'] = 'doctor', "Doktor"
    game['players'][uids[2]]['role'], game['players'][uids[2]]['role_name'] = 'commissar', "Komissar"
    for i in range(3, len(uids)):
        game['players'][uids[i]]['role'], game['players'][uids[i]]['role_name'] = 'citizen', "Tinch aholi"
    
    for uid in game['players']:
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{game['players'][uid]['role_name']}</b>")
        except: pass
    
    await bot.send_message(chat_id, "🎭 O'yin boshlandi!\n\n<b>Tiriklar:</b>\n" + get_players_list(chat_id), reply_markup=get_bot_btn())
    await start_night(chat_id)

async def start_night(chat_id):
    game = games[chat_id]
    # G'olibni tekshirish
    mafias = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] in ['don']]
    citizens = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] not in ['don']]
    
    winner_team = None
    if not mafias: winner_team = 'citizens'
    elif len(mafias) >= len(citizens): winner_team = 'mafia'
    
    if winner_team:
        res_text = "🏆 O'yin tugadi!\n\n<b>G'oliblar (Tiriklar):</b>\n"
        for uid, d in game['players'].items():
            u_data = get_user_data(uid)
            is_maf = d['role'] == 'don'
            if d['is_alive'] and ((winner_team == 'mafia' and is_maf) or (winner_team == 'citizens' and not is_maf)):
                u_data['money'] += 50
                u_data['wins'] += 1
                res_text += f"• {d['name']} (+50$)\n"
            else: u_data['losses'] += 1
        return await bot.send_message(chat_id, res_text, reply_markup=get_bot_btn())

    await bot.send_message(chat_id, "🌑 <b>Tun... (40s)</b>", reply_markup=get_bot_btn())
    game['night_actions'] = {}
    
    for uid, d in game['players'].items():
        if not d['is_alive'] or d['role'] == 'citizen': continue
        kb = InlineKeyboardMarkup()
        for tid, td in game['players'].items():
            if td['is_alive']:
                if d['role'] in ['don', 'commissar'] and tid == uid: continue
                kb.add(InlineKeyboardButton(td['name'], callback_data=f"act_{d['role']}_{tid}_{chat_id}"))
        kb.add(InlineKeyboardButton("⏭ O'tkazib yuborish", callback_data=f"act_{d['role']}_skip_{chat_id}"))
        
        if d['role'] == 'commissar':
            com_kb = InlineKeyboardMarkup().row(InlineKeyboardButton("🔍 Tekshirish", callback_data=f"com_check_{chat_id}"), InlineKeyboardButton("🔫 O'ldirish", callback_data=f"com_kill_{chat_id}"))
            await bot.send_message(uid, "Komissar, tanlang:", reply_markup=com_kb)
        else: await bot.send_message(uid, f"{d['role_name']} harakatingiz:", reply_markup=kb)

    await asyncio.sleep(40)
    await start_day(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith(('act_', 'com_', 'v_', 'jr_')))
async def game_callbacks(callback: types.CallbackQuery):
    data = callback.data.split('_')
    chat_id = int(data[-1])
    game = games[chat_id]
    uid = callback.from_user.id

    # Ovoz berish, Sud va Harakat mantiqlari...
    if data[0] == 'act':
        role, target = data[1], data[2]
        if target == 'skip':
            await bot.send_message(chat_id, f"💤 {role.capitalize()} bugun dam oldi.")
        elif role == 'commissar' and data[2] == 'check':
            target_id = int(data[3])
            t_data = get_user_data(target_id)
            r_name = game['players'][target_id]['role_name']
            if t_data['fake_id'] > 0 and game['players'][target_id]['role'] == 'don':
                r_name = "Tinch aholi"
                t_data['fake_id'] -= 1
            await callback.message.edit_text(f"🔍 Natija: {r_name}")
            return
        else:
            game['night_actions'][role if role != 'commissar' else 'commissar_kill'] = int(target)
        await callback.message.edit_text("Saqlandi.")

async def start_day(chat_id):
    game = games[chat_id]
    await bot.send_message(chat_id, "🌞 <b>Tong otdi!</b>")
    k_maf = game['night_actions'].get('don'); k_com = game['night_actions'].get('commissar_kill'); saved = game['night_actions'].get('doctor')
    
    for target in [k_maf, k_com]:
        if target and target != saved:
            u_t = get_user_data(target)
            if u_t['shield'] > 0:
                u_t['shield'] -= 1
                await bot.send_message(chat_id, f"🛡 {game['players'][target]['name']} himoya tufayli omon qoldi!")
            else:
                game['players'][target]['is_alive'] = False
                await bot.send_message(chat_id, f"💀 {game['players'][target]['name']} o'ldirildi.")
    
    await bot.send_message(chat_id, "<b>Tiriklar:</b>\n" + get_players_list(chat_id), reply_markup=get_bot_btn())
    await start_voting(chat_id)

async def start_voting(chat_id):
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish! (45s)</b>")
    # (Ovoz berish va 20 soniyalik Sud mantiqi yuqoridagi kabi davom etadi)

def get_players_list(chat_id):
    return "\n".join([f"• {d['name']}" for u, d in games[chat_id]['players'].items() if d['is_alive']])

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

import logging
import asyncio
import random
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.deep_linking import get_start_link

# 1. SOZLAMALAR
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

games = {}

# --- YORDAMCHI FUNKSIYALAR ---

def get_players_list_text(chat_id):
    game = games.get(chat_id)
    text = "<b>🎭 Tirik o'yinchilar:</b>\n"
    for uid, data in game['players'].items():
        if data['is_alive']:
            text += f"• <a href='tg://user?id={uid}'>{data['name']}</a>\n"
    return text

# --- ASOSIY KOMANDALAR ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    if args and args.startswith('join_'):
        group_id = int(args.replace('join_', ''))
        user_id = message.from_user.id
        if group_id not in games or games[group_id]['state'] != 'joining':
            return await message.answer("❌ O'yin yopiq.")
        
        if user_id not in games[group_id]['players']:
            games[group_id]['players'][user_id] = {'name': message.from_user.full_name, 'is_alive': True, 'role': None}
            await message.answer("✅ Qo'shildingiz!")
            
            kb = InlineKeyboardMarkup()
            link = await get_start_link(payload=f"join_{group_id}", encode=False)
            kb.add(InlineKeyboardButton("🎮 Qo'shilish", url=link))
            if len(games[group_id]['players']) >= 4:
                kb.add(InlineKeyboardButton("🚀 O'yinni boshlash", callback_data=f"startnow_{group_id}"))
            await bot.send_message(group_id, f"➕ {message.from_user.full_name} qo'shildi! ({len(games[group_id]['players'])} kishi)", reply_markup=kb)

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    if message.chat.type == 'private': return
    games[message.chat.id] = {'players': {}, 'state': 'joining', 'night_actions': {}, 'votes': {}}
    link = await get_start_link(payload=f"join_{message.chat.id}", encode=False)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🎮 Qo'shilish", url=link))
    await message.answer("📢 <b>Mafia boshlanmoqda!</b> Kamida 4 kishi kerak.", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('startnow_'))
async def start_now(callback: types.CallbackQuery):
    chat_id = int(callback.data.split('_')[1])
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)

    # 3-band: Don va Mafia tizimi
    game['players'][uids[0]]['role'] = 'don' # Birinchi doim Don
    game['players'][uids[1]]['role'] = 'doctor'
    game['players'][uids[2]]['role'] = 'commissar'
    
    # 5 kishidan oshsa oddiy Mafia qo'shiladi
    if len(uids) >= 5:
        game['players'][uids[3]]['role'] = 'mafia'
    
    for uid, data in game['players'].items():
        role = data['role'] if data['role'] else 'citizen'
        data['role_name'] = role.capitalize()
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{data['role_name']}</b>")
        except: pass
        
    await bot.send_message(chat_id, "🎭 O'yin boshlandi!\n" + get_players_list_text(chat_id))
    await start_night(chat_id)

# --- TUN BOSQICHI ---

async def start_night(chat_id):
    await bot.send_message(chat_id, "🌑 <b>Tun...</b>")
    game = games[chat_id]
    game['night_actions'] = {}
    
    for uid, data in game['players'].items():
        if not data['is_alive']: continue
        
        kb = InlineKeyboardMarkup()
        if data['role'] in ['don', 'mafia', 'doctor']:
            for tid, tdata in game['players'].items():
                if tdata['is_alive']:
                    kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_{data['role']}_{tid}_{chat_id}"))
            await bot.send_message(uid, "Vazifangizni bajaring:", reply_markup=kb)
            
        elif data['role'] == 'commissar':
            # 2-band: Komissar tanlovi (O'ldirish yoki Tekshirish)
            kb.add(InlineKeyboardButton("🔍 Tekshirish", callback_data=f"com_check_{chat_id}"))
            kb.add(InlineKeyboardButton("🔫 O'ldirish", callback_data=f"com_kill_{chat_id}"))
            await bot.send_message(uid, "Komissar, nima qilasiz?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith(('act_', 'com_')))
async def night_action_cb(callback: types.CallbackQuery):
    data = callback.data.split('_')
    chat_id = int(data[-1])
    role = data[1]
    
    if role == 'check' or role == 'kill':
        # Komissar tanlovi uchun odamlar ro'yxatini chiqarish
        kb = InlineKeyboardMarkup()
        for tid, tdata in games[chat_id]['players'].items():
            if tdata['is_alive']:
                kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_commissar_{role}_{tid}_{chat_id}"))
        await callback.message.edit_text("Kimga nisbatan?", reply_markup=kb)
        return

    # Harakatni yozib olish
    target_id = int(data[-2])
    real_role = data[1] # don, doctor, mafia yoki commissar
    games[chat_id]['night_actions'][real_role] = target_id
    
    # 2-band: Guruhga bildirishnomalar
    notif = {'don': "🕶 Don nishonni tanladi.", 'mafia': "🔫 Mafia harakatda.", 'doctor': "💊 Doktor yo'lga chiqdi.", 'commissar': "🔍 Komissar ishga tushdi."}
    await bot.send_message(chat_id, notif.get(real_role, "Maxfiy harakat..."))
    await callback.message.edit_text("Tanlov qabul qilindi.")
    
    # Simulyatsiya: Hamma bajarishini kutish (sodda)
    if len(games[chat_id]['night_actions']) >= 2: await start_day(chat_id)

# --- KUN VA OVOZ BERISH ---

async def start_day(chat_id):
    game = games[chat_id]
    await bot.send_message(chat_id, "🌞 <b>Tong otdi!</b>")
    
    # 1-band: Doktor qutqarishi
    killed = game['night_actions'].get('don') or game['night_actions'].get('mafia')
    saved = game['night_actions'].get('doctor')
    com_target = game['night_actions'].get('commissar') # Agar komissar o'ldirgan bo'lsa
    
    death_list = []
    if killed and killed != saved: death_list.append(killed)
    
    if death_list:
        for d_id in death_list:
            p = game['players'][d_id]
            p['is_alive'] = False
            await bot.send_message(chat_id, f"💀 <a href='tg://user?id={d_id}'>{p['name']}</a> o'ldirildi. U <b>{p['role_name']}</b> edi.")
    else:
        await bot.send_message(chat_id, "🛡 Doktor barchani qutqardi! Hech kim o'lmadi.")

    await bot.send_message(chat_id, get_players_list_text(chat_id))
    await asyncio.sleep(2)
    await start_voting(chat_id)

async def start_voting(chat_id):
    # 4-band: Ovoz berish jarayoni
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish!</b> Aybdorni aniqlang:")
    kb = InlineKeyboardMarkup()
    for uid, data in games[chat_id]['players'].items():
        if data['is_alive']:
            kb.add(InlineKeyboardButton(data['name'], callback_data=f"vote_{uid}_{chat_id}"))
    await bot.send_message(chat_id, "Odamni tanlang:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('vote_'))
async def vote_cb(callback: types.CallbackQuery):
    _, tid, chat_id = callback.data.split('_')
    chat_id = int(chat_id)
    voter = callback.from_user.full_name
    target = games[chat_id]['players'][int(tid)]['name']
    await bot.send_message(chat_id, f"🗳 <b>{voter}</b> --> {target}ga ovoz berdi!")
    await callback.answer()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

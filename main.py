import logging
import asyncio
import random
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.deep_linking import get_start_link

# 1. SOZLAMALAR
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not API_TOKEN:
    logging.error("XATOLIK: TELEGRAM_BOT_TOKEN topilmadi!")
    exit()

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

games = {}

# --- YORDAMCHI FUNKSIYALAR ---

def get_players_list_text(chat_id):
    game = games.get(chat_id)
    if not game: return "O'yin topilmadi."
    text = "<b>🎭 Tirik o'yinchilar ro'yxati:</b>\n"
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
            return await message.answer("❌ O'yin allaqachon boshlangan yoki mavjud emas.")
        
        if user_id not in games[group_id]['players']:
            games[group_id]['players'][user_id] = {
                'name': message.from_user.full_name,
                'is_alive': True,
                'role': None,
                'role_display': 'Tinch aholi'
            }
            await message.answer("✅ Siz o'yinga muvaffaqiyatli qo'shildingiz! Guruhga qayting.")
            
            # Guruhga xabar va "O'yinni boshlash" tugmasini yangilash
            kb = InlineKeyboardMarkup()
            link = await get_start_link(payload=f"join_{group_id}", encode=False)
            kb.add(InlineKeyboardButton("🎮 O'yinga qo'shilish", url=link))
            # Faqat 3 tadan ko'p odam bo'lsa "Boshlash" tugmasi chiqadi
            if len(games[group_id]['players']) >= 3:
                kb.add(InlineKeyboardButton("🚀 O'yinni boshlash", callback_data=f"startnow_{group_id}"))
            
            await bot.send_message(group_id, f"➕ <a href='tg://user?id={user_id}'>{message.from_user.full_name}</a> qo'shildi!\nHozirgi o'yinchilar: {len(games[group_id]['players'])} ta", reply_markup=kb)
        else:
            await message.answer("Siz allaqachon ro'yxatdasiz.")
    else:
        await message.answer("Mafia botga xush kelibsiz! Guruhda /new_game deb yozing.")

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    if message.chat.type == 'private': return
    
    chat_id = message.chat.id
    games[chat_id] = {'players': {}, 'state': 'joining', 'night_actions': {}, 'votes': {}}
    
    link = await get_start_link(payload=f"join_{chat_id}", encode=False)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎮 O'yinga qo'shilish", url=link))
    
    await message.answer(
        "📢 <b>Yangi Mafia o'yini!</b>\n\nQo'shilish uchun pastdagi tugmani bosing. "
        "Kamida 3 kishi yig'ilgach, admin o'yinni boshlashi mumkin.",
        reply_markup=kb
    )

# --- O'YINNI TUGMA ORQALI BOSHLASH ---

@dp.callback_query_handler(lambda c: c.data.startswith('startnow_'))
async def start_now_callback(callback: types.CallbackQuery):
    chat_id = int(callback.data.split('_')[1])
    
    if len(games[chat_id]['players']) < 3:
        return await callback.answer("O'yinni boshlash uchun kamida 3 kishi kerak!", show_alert=True)
    
    await callback.message.edit_text("🎮 O'yin boshlanmoqda...")
    await start_game_process(chat_id)

async def start_game_process(chat_id):
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)
    
    # Rollar
    game['players'][uids[0]]['role'] = 'mafia'; game['players'][uids[0]]['role_display'] = 'Mafia'
    game['players'][uids[1]]['role'] = 'doctor'; game['players'][uids[1]]['role_display'] = 'Shifokor'
    game['players'][uids[2]]['role'] = 'commissar'; game['players'][uids[2]]['role_display'] = 'Komissar'
    
    await bot.send_message(chat_id, "🎭 Rollar tarqatildi!\n\n" + get_players_list_text(chat_id))
    
    for uid, data in game['players'].items():
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{data['role_display']}</b>")
        except: pass
    await start_night(chat_id)

# --- TUN VA KUN MANTIQI (OLDINGIDEK) ---

async def start_night(chat_id):
    await bot.send_message(chat_id, "🌑 <b>Shahar uyquga ketdi...</b>")
    game = games[chat_id]
    game['night_actions'] = {}
    for uid, data in game['players'].items():
        if data['is_alive'] and data['role'] in ['mafia', 'doctor', 'commissar']:
            kb = InlineKeyboardMarkup()
            for t_id, t_data in game['players'].items():
                if t_data['is_alive']:
                    kb.add(InlineKeyboardButton(t_data['name'], callback_data=f"act_{data['role']}_{t_id}_{chat_id}"))
            await bot.send_message(uid, "Tungi vazifangiz:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('act_'))
async def night_action_cb(callback: types.CallbackQuery):
    _, role, target_id, chat_id = callback.data.split('_')
    chat_id = int(chat_id)
    msgs = {'mafia': "🔫 Mafia nishonni tanladi.", 'doctor': "💊 Shifokor yo'lga chiqdi.", 'commissar': "🔍 Komissar qidiruvda."}
    await bot.send_message(chat_id, msgs[role])
    games[chat_id]['night_actions'][role] = int(target_id)
    await callback.message.edit_text("Qabul qilindi.")
    if len(games[chat_id]['night_actions']) >= 1: await start_day(chat_id)

async def start_day(chat_id):
    game = games[chat_id]
    await bot.send_message(chat_id, "🌞 <b>Tong otdi!</b>")
    m_target = game['night_actions'].get('mafia')
    d_target = game['night_actions'].get('doctor')
    if m_target and m_target != d_target:
        p = game['players'][m_target]
        p['is_alive'] = False
        await bot.send_message(chat_id, f"💀 <a href='tg://user?id={m_target}'>{p['name']}</a> o'ldirildi. U <b>{p['role_display']}</b> edi.")
    else:
        await bot.send_message(chat_id, "🛡 Hech kim o'lmadi.")
    await bot.send_message(chat_id, get_players_list_text(chat_id))
    # Ovoz berish qismi...

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

import logging
import asyncio
import random
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.deep_linking import get_start_link

# --- SOZLAMALAR ---
API_TOKEN = 'SIZNING_BOT_TOKENINGIZ' 
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# O'yin holati (Ma'lumotlar bazasi o'rniga lug'at)
games = {}

# --- YORDAMCHI FUNKSIYALAR ---

def get_alive_players(chat_id):
    """Tirik o'yinchilar ro'yxatini va profil havolalarini shakllantiradi (1 va 5-band)"""
    game = games[chat_id]
    text = "<b>🎭 Tirik o'yinchilar:</b>\n"
    for uid, data in game['players'].items():
        if data['is_alive']:
            text += f"• <a href='tg://user?id={uid}'>{data['name']}</a>\n"
    return text

async def broadcast_to_group(chat_id, text):
    """Guruhga xabar yuborish"""
    await bot.send_message(chat_id, text)

# --- ASOSIY MANTIQ ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """6-band: Deep Linking orqali avto-start va guruhga qo'shilish"""
    args = message.get_args()
    if args and args.startswith('join_'):
        group_id = int(args.replace('join_', ''))
        user_id = message.from_user.id
        
        if group_id not in games or games[group_id]['state'] != 'joining':
            return await message.answer("Xatolik: O'yin allaqachon boshlangan yoki yopilgan.")
        
        if user_id not in games[group_id]['players']:
            games[group_id]['players'][user_id] = {
                'name': message.from_user.full_name,
                'is_alive': True,
                'role': None,
                'role_display': 'Tinch aholi'
            }
            await message.answer("✅ Siz o'yinga qo'shildingiz! Endi guruhga qaytib o'yinni kuting.")
            await bot.send_message(group_id, f"➕ <a href='tg://user?id={user_id}'>{message.from_user.full_name}</a> o'yinga qo'shildi!")
        else:
            await message.answer("Siz allaqachon ro'yxatdasiz.")
    else:
        await message.answer("Salom! Mafia o'yinini boshlash uchun guruhga qo'shing.")

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    """Yangi o'yin e'lon qilish"""
    if message.chat.type == 'private': return
    
    chat_id = message.chat.id
    games[chat_id] = {
        'players': {}, 
        'state': 'joining', 
        'night_actions': {}, 
        'votes': {}
    }
    
    link = await get_start_link(payload=f"join_{chat_id}", encode=False)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🎮 O'yinga qo'shilish", url=link))
    
    await message.answer(
        "📢 <b>Diqqat! Mafia o'yini boshlanmoqda!</b>\n\n"
        "Qatnashish uchun pastdagi tugmani bosing va botda 'Start'ni bosing.",
        reply_markup=kb
    )

@dp.message_handler(commands=['start_game'])
async def start_game(message: types.Message):
    """O'yinni boshlash va rollarni taqsimlash"""
    chat_id = message.chat.id
    if chat_id not in games or len(games[chat_id]['players']) < 3:
        return await message.answer("O'yinni boshlash uchun kamida 3 kishi kerak!")
    
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)
    
    # Sodda rollar taqsimoti
    game['players'][uids[0]]['role'] = 'mafia'; game['players'][uids[0]]['role_display'] = 'Mafia'
    game['players'][uids[1]]['role'] = 'doctor'; game['players'][uids[1]]['role_display'] = 'Shifokor'
    game['players'][uids[2]]['role'] = 'commissar'; game['players'][uids[2]]['role_display'] = 'Komissar'
    
    await message.answer("🎭 Rollar tarqatildi! O'yin boshlanadi.\n\n" + get_alive_players(chat_id))
    
    # Har biriga shaxsiy xabar
    for uid, data in game['players'].items():
        try:
            await bot.send_message(uid, f"Sizning rolingiz: <b>{data['role_display']}</b>")
        except: pass
        
    await start_night(chat_id)

async def start_night(chat_id):
    """Tun bosqichi"""
    await broadcast_to_group(chat_id, "🌑 <b>Shahar uyquga ketdi. Tun boshlandi...</b>")
    game = games[chat_id]
    game['night_actions'] = {}
    
    # Rollar uchun tugmalar (Shaxsiyda)
    for uid, data in game['players'].items():
        if data['is_alive'] and data['role'] in ['mafia', 'doctor', 'commissar']:
            kb = InlineKeyboardMarkup()
            for target_id, target_data in game['players'].items():
                if target_data['is_alive']:
                    kb.add(InlineKeyboardButton(target_data['name'], callback_data=f"act_{data['role']}_{target_id}_{chat_id}"))
            await bot.send_message(uid, "Tungi harakatni bajaring:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('act_'))
async def night_callback(callback: types.CallbackQuery):
    """2-band: Harakatlar haqida guruhga yozuv chiqishi"""
    _, role, target_id, chat_id = callback.data.split('_')
    chat_id = int(chat_id)
    
    # Guruhga bildirishnoma (2-band)
    notifications = {
        'mafia': "🔫 <b>Mafia</b> o'z o'ljasini nishonga oldi...",
        'doctor': "💊 <b>Shifokor</b> kimnidir qutqarishga shoshildi...",
        'commissar': "🔍 <b>Komissar</b> shubhali shaxsni tekshirmoqda..."
    }
    await bot.send_message(chat_id, notifications[role])
    
    games[chat_id]['night_actions'][role] = int(target_id)
    await callback.message.edit_text("Harakat qabul qilindi.")
    
    # Agar hamma harakat qilib bo'lsa, tongni boshlash (bu yerda soddalashtirilgan)
    if len(games[chat_id]['night_actions']) >= 1: # Kamida bitta harakat bo'lsa
        await start_day(chat_id)

async def start_day(chat_id):
    """Tong va 4-band: O'lim xabari"""
    await broadcast_to_group(chat_id, "🌞 <b>Tong otdi! Shahar uyg'ondi.</b>")
    game = games[chat_id]
    
    mafia_target = game['night_actions'].get('mafia')
    doctor_target = game['night_actions'].get('doctor')
    
    if mafia_target and mafia_target != doctor_target:
        # 4-band: O'lim xabari va rolni oshkor qilish
        player = game['players'][mafia_target]
        player['is_alive'] = False
        await broadcast_to_group(chat_id, 
            f"💀 <b>Mudxish xabar!</b>\n\n<a href='tg://user?id={mafia_target}'>{player['name']}</a> Mafia tomonidan o'ldirildi. "
            f"U aslida <b>{player['role_display']}</b> edi.")
    else:
        await broadcast_to_group(chat_id, "🛡 Bugun tunda hech kim zarar ko'rmadi.")
    
    await broadcast_to_group(chat_id, get_alive_players(chat_id))
    await start_voting(chat_id)

async def start_voting(chat_id):
    """3-band: Ovoz berish jarayoni"""
    await broadcast_to_group(chat_id, "🗳 <b>Muhokama vaqti: 60 soniya. Kimdan shubhalanasiz?</b>")
    await asyncio.sleep(5) # Demo uchun qisqa vaqt
    
    game = games[chat_id]
    kb = InlineKeyboardMarkup()
    for uid, data in game['players'].items():
        if data['is_alive']:
            kb.add(InlineKeyboardButton(data['name'], callback_data=f"vote_{uid}_{chat_id}"))
    await bot.send_message(chat_id, "Ovoz bering:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('vote_'))
async def vote_callback(callback: types.CallbackQuery):
    """3-band: Kim kimga ovoz berganini ko'rsatish"""
    _, target_id, chat_id = callback.data.split('_')
    chat_id = int(chat_id)
    voter_name = callback.from_user.full_name
    target_name = games[chat_id]['players'][int(target_id)]['name']
    
    await bot.send_message(chat_id, f"🗳 <b>{voter_name}</b> o'z ovozini {target_name}ga berdi!")
    await callback.answer("Ovozingiz olindi.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

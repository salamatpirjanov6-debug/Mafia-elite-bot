import logging
import asyncio
import random
import os  # Environment Variables bilan ishlash uchun
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.deep_linking import get_start_link

# 1. SOZLAMALAR
# Railway Variables qismidagi TELEGRAM_BOT_TOKEN nomli o'zgaruvchini o'qiydi
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Agarda token topilmasa xatolikni ko'rsatadi
if not API_TOKEN:
    logging.error("XATOLIK: TELEGRAM_BOT_TOKEN topilmadi! Railway Variables qismini tekshiring.")
    exit()

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# O'yin holatini saqlash
games = {}

# --- YORDAMCHI FUNKSIYALAR ---

def get_players_list_text(chat_id):
    """1 va 5-band: Tirik o'yinchilar ro'yxati va Profil linki"""
    game = games.get(chat_id)
    if not game: return "O'yin topilmadi."
    
    text = "<b>🎭 Tirik o'yinchilar ro'yxati:</b>\n"
    for uid, data in game['players'].items():
        if data['is_alive']:
            # tg://user?id= orqali profilga o'tish
            text += f"• <a href='tg://user?id={uid}'>{data['name']}</a>\n"
    return text

# --- ASOSIY KOMANDALAR ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """6-band: Deep Linking orqali o'yinga avto-start qo'shilish"""
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
            await message.answer("✅ Siz o'yinga muvaffaqiyatli qo'shildingiz! Endi guruhga qayting.")
            await bot.send_message(group_id, f"➕ <a href='tg://user?id={user_id}'>{message.from_user.full_name}</a> o'yinga qo'shildi!")
        else:
            await message.answer("Siz allaqachon ro'yxatdasiz.")
    else:
        await message.answer("Mafia botga xush kelibsiz! O'yinni guruhda /new_game orqali boshlang.")

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    """Yangi o'yin e'loni"""
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
        "📢 <b>Yangi Mafia o'yini boshlanmoqda!</b>\n\n"
        "Qatnashish uchun tugmani bosing va botda 'Start'ni bosing.",
        reply_markup=kb
    )

@dp.message_handler(commands=['start_game'])
async def start_game_logic(message: types.Message):
    """O'yinni boshlash va rollarni tarqatish (1-band)"""
    chat_id = message.chat.id
    if chat_id not in games or len(games[chat_id]['players']) < 3:
        return await message.answer("Kamida 3 kishi kerak!")
    
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)
    
    # Rollarni belgilash
    game['players'][uids[0]]['role'] = 'mafia'; game['players'][uids[0]]['role_display'] = 'Mafia'
    game['players'][uids[1]]['role'] = 'doctor'; game['players'][uids[1]]['role_display'] = 'Shifokor'
    game['players'][uids[2]]['role'] = 'commissar'; game['players'][uids[2]]['role_display'] = 'Komissar'
    
    await message.answer("🎭 Rollar tarqatildi! Tun boshlanmoqda.\n\n" + get_players_list_text(chat_id))
    
    # Shaxsiyga rolni yuborish
    for uid, data in game['players'].items():
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{data['role_display']}</b>")
        except: pass
    
    await start_night(chat_id)

# --- O'YIN JARAYONI ---

async def start_night(chat_id):
    """Tun bosqichi"""
    await bot.send_message(chat_id, "🌑 <b>Shahar uyquga ketdi. Tun boshlandi...</b>")
    game = games[chat_id]
    game['night_actions'] = {}
    
    for uid, data in game['players'].items():
        if data['is_alive'] and data['role'] in ['mafia', 'doctor', 'commissar']:
            kb = InlineKeyboardMarkup()
            for t_id, t_data in game['players'].items():
                if t_data['is_alive']:
                    kb.add(InlineKeyboardButton(t_data['name'], callback_data=f"act_{data['role']}_{t_id}_{chat_id}"))
            await bot.send_message(uid, "Tungi vazifangizni tanlang:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('act_'))
async def night_action_cb(callback: types.CallbackQuery):
    """2-band: Rol harakati haqida guruhga live bildirishnoma"""
    _, role, target_id, chat_id = callback.data.split('_')
    chat_id = int(chat_id)
    
    msgs = {
        'mafia': "🔫 <b>Mafia</b> o'ljasini nishonga oldi...",
        'doctor': "💊 <b>Shifokor</b> kimnidir davolashga ketdi...",
        'commissar': "🔍 <b>Komissar</b> yovuzlarni qidirishga ketdi..."
    }
    await bot.send_message(chat_id, msgs[role])
    
    games[chat_id]['night_actions'][role] = int(target_id)
    await callback.message.edit_text("Tanlov qabul qilindi.")
    
    # Hamma harakat qilganini tekshirish (sodda mantiq)
    if len(games[chat_id]['night_actions']) >= 1: 
        await asyncio.sleep(2) # Biroz kutish
        await start_day(chat_id)

async def start_day(chat_id):
    """Tong va 4-band: O'lim haqida batafsil xabar"""
    game = games[chat_id]
    await bot.send_message(chat_id, "🌞 <b>Tong otdi! Shahar uyg'ondi.</b>")
    
    m_target = game['night_actions'].get('mafia')
    d_target = game['night_actions'].get('doctor')
    
    if m_target and m_target != d_target:
        player = game['players'][m_target]
        player['is_alive'] = False
        # 4-band: O'lim sababi va rolni oshkor qilish
        await bot.send_message(chat_id, 
            f"💀 <b>Yomon xabar!</b>\n\n<a href='tg://user?id={m_target}'>{player['name']}</a> Mafia tomonidan o'ldirildi. "
            f"U <b>{player['role_display']}</b> edi.")
    else:
        await bot.send_message(chat_id, "🛡 Shaharda tinchlik. Hech kim o'lmadi.")
    
    await bot.send_message(chat_id, get_players_list_text(chat_id))
    await start_voting(chat_id)

async def start_voting(chat_id):
    """3-band: Ochiq ovoz berish"""
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish boshlandi!</b> Kimdan shubhalanasiz?")
    game = games[chat_id]
    kb = InlineKeyboardMarkup()
    for uid, data in game['players'].items():
        if data['is_alive']:
            kb.add(InlineKeyboardButton(data['name'], callback_data=f"vote_{uid}_{chat_id}"))
    await bot.send_message(chat_id, "Ovoz bering:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('vote_'))
async def vote_cb(callback: types.CallbackQuery):
    """3-band: Ovoz beruvchini ismini ko'rsatish"""
    _, target_id, chat_id = callback.data.split('_')
    chat_id = int(chat_id)
    voter = callback.from_user.full_name
    target = games[chat_id]['players'][int(target_id)]['name']
    
    await bot.send_message(chat_id, f"🗳 <b>{voter}</b> o'z ovozini {target}ga berdi!")
    await callback.answer("Ovozingiz olindi.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

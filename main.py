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

# 5-band: O'lganlar yozishini taqiqlash
@dp.message_handler(lambda m: not m.text.startswith('/'))
async def filter_messages(message: types.Message):
    chat_id = message.chat.id
    if chat_id in games:
        user_id = message.from_user.id
        if user_id not in games[chat_id]['players'] or not games[chat_id]['players'][user_id]['is_alive']:
            try:
                await message.delete()
            except:
                pass

# --- KOMANDALAR ---

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    if message.chat.type == 'private': return
    games[message.chat.id] = {
        'players': {}, 'state': 'joining', 'night_actions': {}, 
        'votes': {}, 'last_word_user': None
    }
    link = await get_start_link(payload=f"join_{message.chat.id}", encode=False)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🎮 Qo'shilish", url=link))
    await message.answer("📢 <b>Mafia boshlanmoqda!</b>\nKamida 4 kishi qo'shilishi kutilmoqda...", reply_markup=kb)

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    if args and args.startswith('join_'):
        group_id = int(args.replace('join_', ''))
        user_id = message.from_user.id
        if group_id not in games or games[group_id]['state'] != 'joining': return
        
        if user_id not in games[group_id]['players']:
            games[group_id]['players'][user_id] = {'name': message.from_user.full_name, 'is_alive': True, 'role': None}
            await message.answer("✅ Siz o'yinga qo'shildingiz!")
            
            kb = InlineKeyboardMarkup()
            link = await get_start_link(payload=f"join_{group_id}", encode=False)
            kb.add(InlineKeyboardButton("🎮 Qo'shilish", url=link))
            if len(games[group_id]['players']) >= 4:
                kb.add(InlineKeyboardButton("🚀 O'yinni boshlash", callback_data=f"startnow_{group_id}"))
            await bot.send_message(group_id, f"➕ {message.from_user.full_name} qo'shildi! ({len(games[group_id]['players'])} kishi)", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('startnow_'))
async def start_now(callback: types.CallbackQuery):
    chat_id = int(callback.data.split('_')[1])
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)

    # Rollar taqsimoti
    game['players'][uids[0]]['role'] = 'don'
    game['players'][uids[1]]['role'] = 'doctor'
    game['players'][uids[2]]['role'] = 'commissar'
    if len(uids) >= 5: game['players'][uids[3]]['role'] = 'mafia'
    
    for uid, data in game['players'].items():
        role = data.get('role') or 'citizen'
        data['role_name'] = role.capitalize()
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{data['role_name']}</b>")
        except: pass
        
    await bot.send_message(chat_id, "🎭 O'yin boshlandi!\n" + get_players_list_text(chat_id))
    await start_night(chat_id)

# --- 2-BAND: TUN VA 40 SONIYA ---

async def start_night(chat_id):
    await bot.send_message(chat_id, "🌑 <b>Tun... Hamma uyquga ketdi. (40 soniya)</b>")
    game = games[chat_id]
    game['night_actions'] = {}
    
    for uid, data in game['players'].items():
        if not data['is_alive']: continue
        kb = InlineKeyboardMarkup()
        if data['role'] in ['don', 'mafia', 'doctor']:
            for tid, tdata in game['players'].items():
                if tdata['is_alive']:
                    kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_{data['role']}_{tid}_{chat_id}"))
            await bot.send_message(uid, "Tungi vazifangiz:", reply_markup=kb)
        elif data['role'] == 'commissar':
            kb.add(InlineKeyboardButton("🔍 Tekshirish", callback_data=f"com_check_{chat_id}"))
            kb.add(InlineKeyboardButton("🔫 O'ldirish", callback_data=f"com_kill_{chat_id}"))
            await bot.send_message(uid, "Komissar, tanlang:", reply_markup=kb)

    await asyncio.sleep(40) # 40 soniya kutish
    await start_day(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith(('act_', 'com_')))
async def night_action_cb(callback: types.CallbackQuery):
    # (Tungi harakatlar mantiqi avvalgidek saqlangan...)
    data = callback.data.split('_')
    chat_id = int(data[-1])
    role = data[1]
    if role in ['check', 'kill']:
        kb = InlineKeyboardMarkup()
        for tid, tdata in games[chat_id]['players'].items():
            if tdata['is_alive']:
                kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_commissar_{role}_{tid}_{chat_id}"))
        await callback.message.edit_text("Kimga?", reply_markup=kb)
        return
    
    target_id = int(data[-2])
    real_role = data[1]
    games[chat_id]['night_actions'][real_role] = target_id
    await callback.message.edit_text("Harakat saqlandi.")

# --- 4-BAND: SO'NGGI SO'Z ---

async def start_day(chat_id):
    game = games[chat_id]
    await bot.send_message(chat_id, "🌞 <b>Tong otdi!</b>")
    
    killed = game['night_actions'].get('don') or game['night_actions'].get('mafia')
    saved = game['night_actions'].get('doctor')
    
    # 1-band: Faqat nishon va doktor tanlovi bir xil bo'lsa qutiladi
    if killed and killed != saved:
        p = game['players'][killed]
        p['is_alive'] = False
        await bot.send_message(chat_id, f"💀 <a href='tg://user?id={killed}'>{p['name']}</a> o'ldirildi. U <b>{p['role_name']}</b> edi.")
        
        # 4-band: So'nggi so'z uchun imkon berish
        await bot.send_message(killed, "Siz o'ldirildingiz. So'nggi so'zingizni yozing (15 soniya):")
        game['last_word_user'] = killed
        await asyncio.sleep(15) 
    else:
        await bot.send_message(chat_id, "🛡 Bugun tunda hech kim o'lmadi.")

    await bot.send_message(chat_id, get_players_list_text(chat_id))
    await start_voting(chat_id)

@dp.message_handler(lambda m: games.get(m.chat.id) and games[m.chat.id]['last_word_user'] == m.from_user.id)
async def last_word_handler(message: types.Message):
    chat_id = message.chat.id
    await bot.send_message(chat_id, f"📢 <b>O'lgan odamning so'nggi so'zi:</b>\n\n<i>{message.text}</i>")
    games[chat_id]['last_word_user'] = None

# --- 3 VA 6-BANDLAR: OVOZ BERISH VA SUD ---

async def start_voting(chat_id):
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish boshlandi! (45 soniya)</b>\nShaxsiyda tugmalar paydo bo'ldi.")
    game = games[chat_id]
    game['votes'] = {}

    for uid, data in game['players'].items():
        if data['is_alive']:
            kb = InlineKeyboardMarkup()
            for tid, tdata in game['players'].items():
                # 3-band: O'ziga o'zi ovoz bera olmaydi
                if tdata['is_alive'] and tid != uid:
                    kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"v_{tid}_{chat_id}"))
            try: await bot.send_message(uid, "Kimga ovoz berasiz?", reply_markup=kb)
            except: pass

    await asyncio.sleep(45)
    await process_voting_results(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith('v_'))
async def vote_handler(callback: types.CallbackQuery):
    _, tid, chat_id = callback.data.split('_')
    chat_id = int(chat_id)
    game = games[chat_id]
    game['votes'][callback.from_user.id] = int(tid)
    await callback.message.edit_text("Ovozingiz qabul qilindi.")

async def process_voting_results(chat_id):
    game = games[chat_id]
    if not game['votes']:
        return await bot.send_message(chat_id, "Hech kim ovoz bermadi.")
    
    # Eng ko'p ovoz olgan ishtirokchini aniqlash
    counts = {}
    for v in game['votes'].values(): counts[v] = counts.get(v, 0) + 1
    suspect_id = max(counts, key=counts.get)
    
    # 6-band: Like/Dislike Sud
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("👍 Like", callback_data=f"jury_l_{suspect_id}_{chat_id}"),
        InlineKeyboardButton("👎 Dislike", callback_data=f"jury_d_{suspect_id}_{chat_id}")
    )
    game['jury'] = {'l': 0, 'd': 0}
    await bot.send_message(chat_id, f"⚖️ <b>Sud:</b> <a href='tg://user?id={suspect_id}'>{game['players'][suspect_id]['name']}</a> osilsinmi?", reply_markup=kb)
    await asyncio.sleep(20)
    
    if game['jury']['l'] > game['jury']['d']:
        game['players'][suspect_id]['is_alive'] = False
        await bot.send_message(chat_id, "💀 Aholi qarori bilan u osildi.")
    else:
        await bot.send_message(chat_id, "🕊 Aholi kelisha olmadi, u omon qoldi.")
    
    await start_night(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith('jury_'))
async def jury_handler(callback: types.CallbackQuery):
    _, vote, _, chat_id = callback.data.split('_')
    games[int(chat_id)]['jury'][vote] += 1
    await callback.answer("Qabul qilindi")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

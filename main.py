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
user_db = {} # {user_id: {data}}
games = {}   # {chat_id: {game_data}}
bot_info = {} # Bot usernamesini saqlash uchun

# --- YORDAMCHI FUNKSIYALAR ---

def get_user_data(uid):
    if uid not in user_db:
        user_db[uid] = {'money': 100, 'wins': 0, 'losses': 0, 'total': 0, 'shield': 0, 'fake_id': 0}
    return user_db[uid]

def get_mention(uid, name):
    return f"<a href='tg://user?id={uid}'>{name}</a>"

async def get_bot_btn(chat_id=None):
    if not bot_info.get('username'):
        me = await bot.get_me()
        bot_info['username'] = me.username
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🤖 Botga o'tish", url=f"https://t.me/{bot_info['username']}"))
    
    if chat_id and chat_id in games:
        link = games[chat_id].get('invite_link')
        if link:
            kb.add(InlineKeyboardButton("⬅️ Guruhga qaytish", url=link))
    return kb

def get_reg_text(chat_id):
    game = games[chat_id]
    text = f"📢 <b>Mafia o'yini boshlanmoqda!</b>\n"
    text += f"<i>Ro'yxatdan o'tish uchun quyidagi tugmani bosing.</i>\n\n"
    text += f"⏰ Vaqt: <b>{game['timer']} soniya</b> qoldi.\n"
    text += f"👥 Ro'yxat: <b>{len(game['players'])} kishi</b>\n\n"
    for i, (uid, data) in enumerate(game['players'].items(), 1):
        text += f"{i}. {get_mention(uid, data['name'])}\n"
    return text

# --- BUYRUQLAR (Guruhda) ---

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    if message.chat.type == 'private':
        return await message.answer("Ushbu buyruq faqat guruhlarda ishlaydi!")
    
    chat_id = message.chat.id
    
    # Guruh linkini generatsiya qilish
    try:
        if message.chat.username:
            invite_link = f"https://t.me/{message.chat.username}"
        else:
            invite_link = await message.chat.export_invite_link()
    except:
        invite_link = None

    games[chat_id] = {
        'players': {}, 'state': 'joining', 'timer': 45, 'reg_msg_id': None,
        'night_actions': {}, 'votes': {}, 'jury': {'l': [], 'd': []},
        'invite_link': invite_link
    }
    
    link = await get_start_link(payload=f"join_{chat_id}", encode=False)
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🎮 Qo'shilish", url=link),
        InlineKeyboardButton("🚀 Boshlash", callback_data=f"startnow_{chat_id}")
    )
    
    msg = await message.answer(get_reg_text(chat_id), reply_markup=kb)
    games[chat_id]['reg_msg_id'] = msg.message_id
    
    # Avtomatik taymer sikli
    while games[chat_id]['timer'] > 0 and games[chat_id]['state'] == 'joining':
        await asyncio.sleep(5)
        games[chat_id]['timer'] -= 5
        try:
            await bot.edit_message_text(get_reg_text(chat_id), chat_id, msg.message_id, reply_markup=kb)
        except: pass
    
    if games[chat_id]['state'] == 'joining':
        if len(games[chat_id]['players']) >= 4:
            await start_game_logic(chat_id)
        else:
            await message.answer("⚠️ O'yin bekor qilindi. O'yinchilar soni kam (kamida 4 kishi kerak).")

@dp.message_handler(commands=['time_uzaytirish'])
async def extend_time(message: types.Message):
    cid = message.chat.id
    if cid in games and games[cid]['state'] == 'joining':
        games[cid]['timer'] += 10
        await message.answer("➕ Ro'yxatga 10 soniya qo'shildi!")

@dp.message_handler(commands=['quit'])
async def quit_game(message: types.Message):
    cid = message.chat.id
    uid = message.from_user.id
    if cid in games and uid in games[cid]['players']:
        del games[cid]['players'][uid]
        await message.answer(f"❌ {get_mention(uid, message.from_user.full_name)} o'yinni tark etdi.")

# --- BOT SHAXSIYI (Start va Menyular) ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    get_user_data(uid)
    args = message.get_args()
    
    if args and args.startswith('join_'):
        cid = int(args.split('_')[1])
        if cid in games and games[cid]['state'] == 'joining':
            games[cid]['players'][uid] = {'name': message.from_user.full_name, 'is_alive': True, 'role': None}
            kb = await get_bot_btn(cid)
            await message.answer("✅ Siz o'yinga muvaffaqiyatli qo'shildingiz!", reply_markup=kb)
            return

    main_kb = ReplyKeyboardMarkup(resize_keyboard=True).row("👤 Profil", "🛒 Do'kon").row("📜 Qoidalar")
    await message.answer("Salom! Mafia botining shaxsiy paneliga xush kelibsiz.", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "👤 Profil")
async def profile_view(message: types.Message):
    if message.chat.type != 'private': return
    u = get_user_data(message.from_user.id)
    text = (f"<b>👤 Sizning Profilingiz:</b>\n\n"
            f"💰 Mablag': {u['money']}$\n"
            f"🏆 G'alabalar: {u['wins']}\n"
            f"❌ Mag'lubiyatlar: {u['losses']}\n"
            f"🛡 Himoya: {u['shield']} ta\n"
            f"📑 Soxta hujjat: {u['fake_id']} ta")
    await message.answer(text)

@dp.message_handler(lambda m: m.text == "🛒 Do'kon")
async def shop_view(message: types.Message):
    if message.chat.type != 'private': return
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🛡 Himoya (200$)", callback_data="buy_shield"),
        InlineKeyboardButton("📑 Soxta hujjat (250$)", callback_data="buy_fakeid")
    )
    await message.answer("🛒 <b>Mafia Do'koni:</b>\n\n🛡 <b>Himoya</b> - Tunda o'limdan saqlaydi.\n📑 <b>Soxta hujjat</b> - Komissar tekshirganda 'Tinch aholi' bo'lib ko'rinishingizni ta'minlaydi.", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'))
async def process_purchase(callback: types.CallbackQuery):
    u = get_user_data(callback.from_user.id)
    item = callback.data.split('_')[1]
    price = 200 if item == 'shield' else 250
    
    if u['money'] >= price:
        u['money'] -= price
        if item == 'shield': u['shield'] += 1
        else: u['fake_id'] += 1
        await callback.answer("✅ Buyum sotib olindi!", show_alert=True)
        await profile_view(callback.message)
    else:
        await callback.answer("❌ Pul yetarli emas!", show_alert=True)

# --- O'YIN JARAYONI MANTIG'I ---

@dp.callback_query_handler(lambda c: c.data.startswith('startnow_'))
async def manual_start(callback: types.CallbackQuery):
    cid = int(callback.data.split('_')[1])
    if len(games[cid]['players']) >= 4:
        await start_game_logic(cid)
    else:
        await callback.answer("O'yinchilar yetarli emas (kamida 4 ta)!", show_alert=True)

async def start_game_logic(chat_id):
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)
    
    # Rollarni taqsimlash
    game['players'][uids[0]]['role'], game['players'][uids[0]]['role_name'] = 'don', "Don"
    game['players'][uids[1]]['role'], game['players'][uids[1]]['role_name'] = 'doctor', "Doktor"
    game['players'][uids[2]]['role'], game['players'][uids[2]]['role_name'] = 'commissar', "Komissar"
    for i in range(3, len(uids)):
        game['players'][uids[i]]['role'], game['players'][uids[i]]['role_name'] = 'citizen', "Tinch aholi"
    
    for uid in game['players']:
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{game['players'][uid]['role_name']}</b>")
        except: pass
        
    kb = await get_bot_btn(chat_id)
    await bot.send_message(chat_id, "🎭 O'yin boshlandi! Rollar shaxsiyga yuborildi.\n\n" + get_alive_list(chat_id), reply_markup=kb)
    await start_night(chat_id)

async def check_winner(chat_id):
    game = games[chat_id]
    mafias = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] == 'don']
    citizens = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] != 'don']
    
    if not mafias or len(mafias) >= len(citizens):
        win_team = 'citizens' if not mafias else 'mafia'
        text = f"🏆 <b>{'Tinch aholi' if win_team == 'citizens' else 'Mafia'} jamoasi g'alaba qozondi!</b>\n\n<b>Mukofot olganlar (+50$):</b>\n"
        for uid, d in game['players'].items():
            u_d = get_user_data(uid)
            is_maf = (d['role'] == 'don')
            if d['is_alive'] and ((win_team == 'mafia' and is_maf) or (win_team == 'citizens' and not is_maf)):
                u_d['money'] += 50
                u_d['wins'] += 1
                text += f"• {get_mention(uid, d['name'])}\n"
            else:
                u_d['losses'] += 1
        
        kb = await get_bot_btn(chat_id)
        await bot.send_message(chat_id, text, reply_markup=kb)
        del games[chat_id]
        return True
    return False

async def start_night(chat_id):
    if await check_winner(chat_id): return
    game = games[chat_id]
    game['night_actions'] = {}
    kb = await get_bot_btn(chat_id)
    await bot.send_message(chat_id, "🌑 <b>Tun tushdi... Mafia va maxsus rollar uyg'onadi. (40s)</b>", reply_markup=kb)
    
    for uid, d in game['players'].items():
        if not d['is_alive'] or d['role'] == 'citizen': continue
        
        target_kb = InlineKeyboardMarkup()
        for tid, td in game['players'].items():
            if td['is_alive']:
                if d['role'] in ['don', 'commissar'] and tid == uid: continue
                target_kb.add(InlineKeyboardButton(td['name'], callback_data=f"act_{d['role']}_{tid}_{chat_id}"))
        target_kb.add(InlineKeyboardButton("⏭ O'tkazib yuborish", callback_data=f"act_{d['role']}_skip_{chat_id}"))
        
        if d['role'] == 'commissar':
            com_menu = InlineKeyboardMarkup().row(
                InlineKeyboardButton("🔍 Tekshirish", callback_data=f"com_check_{chat_id}"),
                InlineKeyboardButton("🔫 O'ldirish", callback_data=f"com_kill_{chat_id}")
            )
            await bot.send_message(uid, "Komissar, tunda nima qilmoqchisiz?", reply_markup=com_menu)
        else:
            await bot.send_message(uid, f"Sizning harakatingiz ({d['role_name']}):", reply_markup=target_kb)

    await asyncio.sleep(40)
    await start_day(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith(('act_', 'com_', 'v_', 'jr_')))
async def handle_game_logic(callback: types.CallbackQuery):
    data = callback.data.split('_')
    mode = data[0]
    chat_id = int(data[-1])
    game = games.get(chat_id)
    if not game: return
    
    uid = callback.from_user.id
    
    if mode == 'com':
        action = data[1]
        kb = InlineKeyboardMarkup()
        for tid, td in game['players'].items():
            if td['is_alive'] and tid != uid:
                kb.add(InlineKeyboardButton(td['name'], callback_data=f"act_commissar_{action}_{tid}_{chat_id}"))
        await callback.message.edit_text(f"Komissar: Nishonni tanlang ({action}):", reply_markup=kb)

    elif mode == 'act':
        role, target = data[1], data[2]
        if target == 'skip':
            await bot.send_message(chat_id, f"💤 {role.capitalize()} tunda harakat qilmadi.")
        elif role == 'commissar' and data[2] == 'check':
            tid = int(data[3])
            t_user = get_user_data(tid)
            role_res = game['players'][tid]['role_name']
            if t_user['fake_id'] > 0 and game['players'][tid]['role'] == 'don':
                role_res = "Tinch aholi"
                t_user['fake_id'] -= 1
            await callback.message.edit_text(f"🔍 Natija: {game['players'][tid]['name']} - {role_res}")
        else:
            action_key = 'don' if role == 'don' else ('doctor' if role == 'doctor' else 'commissar_kill')
            game['night_actions'][action_key] = int(target)
            await callback.message.edit_text("Harakat qabul qilindi.")

async def start_day(chat_id):
    if chat_id not in games: return
    game = games[chat_id]
    kb = await get_bot_btn(chat_id)
    await bot.send_message(chat_id, "🌞 <b>Tong otdi!</b>", reply_markup=kb)
    
    k_maf = game['night_actions'].get('don')
    k_com = game['night_actions'].get('commissar_kill')
    saved = game['night_actions'].get('doctor')
    
    for target_id in set([k_maf, k_com]):
        if target_id and target_id != saved:
            u_t = get_user_data(target_id)
            if u_t['shield'] > 0:
                u_t['shield'] -= 1
                await bot.send_message(chat_id, f"🛡 {get_mention(target_id, game['players'][target_id]['name'])}ga hujum bo'ldi, lekin himoyasi saqlab qoldi!")
            else:
                game['players'][target_id]['is_alive'] = False
                await bot.send_message(chat_id, f"💀 {get_mention(target_id, game['players'][target_id]['name'])} o'ldirildi. U {game['players'][target_id]['role_name']} edi.")
    
    await bot.send_message(chat_id, get_alive_list(chat_id), reply_markup=kb)
    await start_voting(chat_id)

async def start_voting(chat_id):
    if await check_winner(chat_id): return
    game = games[chat_id]
    game['votes'] = {}
    kb = await get_bot_btn(chat_id)
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish vaqti (45s)! Kimdan shubhalanasiz?</b>", reply_markup=kb)
    
    for uid, d in game['players'].items():
        if d['is_alive']:
            v_kb = InlineKeyboardMarkup()
            for tid, td in game['players'].items():
                if td['is_alive'] and tid != uid:
                    v_kb.add(InlineKeyboardButton(td['name'], callback_data=f"v_{tid}_{chat_id}"))
            try: await bot.send_message(uid, "Ovoz bering:", reply_markup=v_kb)
            except: pass
            
    await asyncio.sleep(45)
    
    if not game['votes']:
        await bot.send_message(chat_id, "Hech kim ovoz bermadi. Sud o'tkazilmaydi.")
        await start_night(chat_id)
    else:
        v_list = list(game['votes'].values())
        suspect_id = max(set(v_list), key=v_list.count)
        game['jury'] = {'l': [], 'd': []}
        
        await bot.send_message(chat_id, f"⚖️ <b>Sud boshlandi!</b>\nO'yinchi: {get_mention(suspect_id, game['players'][suspect_id]['name'])}\n\nU osilsinmi? (20s)", 
                               reply_markup=get_jury_kb(suspect_id, chat_id, 0, 0))
        await asyncio.sleep(20)
        
        if len(game['jury']['l']) > len(game['jury']['d']):
            game['players'][suspect_id]['is_alive'] = False
            await bot.send_message(chat_id, f"💀 {game['players'][suspect_id]['name']} osildi.")
        else:
            await bot.send_message(chat_id, "🕊 Aholi uni kechirishga qaror qildi.")
        await start_night(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith('v_'))
async def handle_vote(callback: types.CallbackQuery):
    _, tid, cid = callback.data.split('_')
    cid = int(cid)
    games[cid]['votes'][callback.from_user.id] = int(tid)
    await bot.send_message(cid, f"🗳 {callback.from_user.full_name} ovoz berdi.")
    await callback.message.edit_text("Ovozingiz qabul qilindi.")

def get_jury_kb(sid, cid, l, d):
    return InlineKeyboardMarkup().row(
        InlineKeyboardButton(f"👍 Ha ({l})", callback_data=f"jr_l_{sid}_{cid}"),
        InlineKeyboardButton(f"👎 Yo'q ({d})", callback_data=f"jr_d_{sid}_{cid}")
    )

@dp.callback_query_handler(lambda c: c.data.startswith('jr_'))
async def handle_jury(callback: types.CallbackQuery):
    _, vote, sid, cid = callback.data.split('_')
    cid = int(cid); sid = int(sid); uid = callback.from_user.id
    game = games[cid]
    
    if uid not in game['players'] or not game['players'][uid]['is_alive'] or uid == sid:
        return await callback.answer("Siz ovoz bera olmaysiz!")
    if uid in game['jury']['l'] or uid in game['jury']['d']:
        return await callback.answer("Siz allaqachon ovoz berdingiz!")
    
    game['jury'][vote].append(uid)
    await callback.message.edit_reply_markup(reply_markup=get_jury_kb(sid, cid, len(game['jury']['l']), len(game['jury']['d'])))

def get_alive_list(chat_id):
    return "👥 <b>Hozirgi tirik o'yinchilar:</b>\n" + "\n".join([f"• {get_mention(u, d['name'])}" for u, d in games[chat_id]['players'].items() if d['is_alive']])

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

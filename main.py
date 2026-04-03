import logging
import asyncio
import random
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.deep_linking import get_start_link

# 1. SOZLAMALAR
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Ma'lumotlar bazasi (Sodda variant)
user_db = {} # {user_id: {'money': 0, 'wins': 0, 'losses': 0, 'total': 0, 'shield': 0, 'fake_id': 0}}
games = {}

# --- YORDAMCHI FUNKSIYALAR ---

def get_user_data(uid):
    if uid not in user_db:
        user_db[uid] = {'money': 100, 'wins': 0, 'losses': 0, 'total': 0, 'shield': 0, 'fake_id': 0}
    return user_db[uid]

def get_mention(uid, name):
    return f"<a href='tg://user?id={uid}'>{name}</a>"

def get_bot_btn():
    return InlineKeyboardMarkup().add(InlineKeyboardButton("🤖 Botga o'tish", url=f"https://t.me/{(bot._id if hasattr(bot, '_id') else 'bot_username')}"))

def check_winner(chat_id):
    game = games[chat_id]
    mafias = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] in ['don', 'mafia']]
    citizens = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] not in ['don', 'mafia']]
    
    winner_team = None
    if not mafias: winner_team = 'citizens'
    elif len(mafias) >= len(citizens): winner_team = 'mafia'
    
    if winner_team:
        text = "🏆 <b>O'yin yakunlandi!</b>\n\n"
        winners, others = [], []
        for uid, data in game['players'].items():
            u_data = get_user_data(uid)
            u_data['total'] += 1
            is_maf = data['role'] in ['don', 'mafia']
            
            # Faqat tirik qolgan g'oliblar 50$ oladi
            if data['is_alive'] and ((winner_team == 'mafia' and is_maf) or (winner_team == 'citizens' and not is_maf)):
                u_data['money'] += 50
                u_data['wins'] += 1
                winners.append(f"• {get_mention(uid, data['name'])} (+50$)")
            else:
                u_data['losses'] += 1
                others.append(f"• {get_mention(uid, data['name'])} ({data['role_name']})")
        
        text += "<b>🥇 G'oliblar (Tiriklar):</b>\n" + ("\n".join(winners) if winners else "Hech kim")
        text += "\n\n<b>👥 Boshqalar:</b>\n" + "\n".join(others)
        return text
    return None

# --- BOT MENYULARI ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    get_user_data(uid)
    
    args = message.get_args()
    if args and args.startswith('join_'):
        group_id = int(args.replace('join_', ''))
        if group_id in games and games[group_id]['state'] == 'joining':
            if uid not in games[group_id]['players']:
                games[group_id]['players'][uid] = {'name': message.from_user.full_name, 'is_alive': True, 'role': None}
                kb = InlineKeyboardMarkup()
                if games[group_id].get('group_link'):
                    kb.add(InlineKeyboardButton("⬅️ Guruhga qaytish", url=games[group_id]['group_link']))
                await message.answer("✅ O'yinga qo'shildingiz!", reply_markup=kb)
                await bot.send_message(group_id, f"➕ {get_mention(uid, message.from_user.full_name)} qo'shildi!", reply_markup=get_bot_btn())
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True).row("👤 Profil", "🛒 Do'kon").row("📜 Qoidalar")
    await message.answer("Mafia botiga xush kelibsiz!", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "👤 Profil")
async def profile_view(message: types.Message):
    u = get_user_data(message.from_user.id)
    text = (f"<b>👤 Profil: {message.from_user.full_name}</b>\n"
            f"💰 Balans: {u['money']}$\n"
            f"🏆 G'alaba: {u['wins']} | ❌ Mag'lubiyat: {u['losses']}\n"
            f"🛡 Himoya: {u['shield']} ta | 📑 Soxta hujjat: {u['fake_id']} ta")
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🛒 Do'kon", callback_data="open_shop"))
    await message.answer(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "open_shop")
async def shop_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🛡 Himoya (200$)", callback_data="buy_shield"),
        InlineKeyboardButton("📑 Soxta hujjat (250$)", callback_data="buy_fakeid")
    )
    await callback.message.edit_text("🛒 <b>Do'kon:</b>\n🛡 Himoya: O'limdan saqlaydi.\n📑 Soxta hujjat: Komissarni aldaydi.", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def buy_item(callback: types.CallbackQuery):
    u = get_user_data(callback.from_user.id)
    item = callback.data.split("_")[1]
    
    if item == "shield":
        if u['money'] >= 200:
            u['money'] -= 200
            u['shield'] += 1
            await callback.answer("🛡 Himoya sotib olindi!", show_alert=True)
        else:
            await callback.answer("❌ Mablag' yetarli emas!", show_alert=True)
    elif item == "fakeid":
        if u['money'] >= 250:
            u['money'] -= 250
            u['fake_id'] += 1
            await callback.answer("📑 Soxta hujjat sotib olindi!", show_alert=True)
        else:
            await callback.answer("❌ Mablag' yetarli emas!", show_alert=True)
    await profile_view(callback.message)

# --- O'YIN JARAYONI ---

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    if message.chat.type == 'private': return
    games[message.chat.id] = {
        'players': {}, 'state': 'joining', 'night_actions': {}, 
        'votes': {}, 'jury': {'l': [], 'd': []},
        'group_link': f"https://t.me/{message.chat.username}" if message.chat.username else None
    }
    link = await get_start_link(payload=f"join_{message.chat.id}", encode=False)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🤖 Botga o'tish", url=link))
    await message.answer("📢 <b>Mafia boshlanmoqda!</b>", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('startnow_'))
async def start_now(callback: types.CallbackQuery):
    chat_id = int(callback.data.split('_')[1])
    game = games[chat_id]; game['state'] = 'playing'
    uids = list(game['players'].keys()); random.shuffle(uids)
    
    # Rollar taqsimoti
    roles = [('don', "Don"), ('doctor', "Doktor"), ('commissar', "Komissar")]
    for i in range(len(uids)):
        if i < len(roles):
            game['players'][uids[i]]['role'], game['players'][uids[i]]['role_name'] = roles[i]
        else:
            game['players'][uids[i]]['role'], game['players'][uids[i]]['role_name'] = 'citizen', "Tinch aholi"
    
    for uid in game['players']:
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{game['players'][uid]['role_name']}</b>")
        except: pass
        
    await bot.send_message(chat_id, "🎭 O'yin boshlandi!\n" + get_players_list_text(chat_id), reply_markup=get_bot_btn())
    await start_night(chat_id)

async def start_night(chat_id):
    res = check_winner(chat_id)
    if res: return await bot.send_message(chat_id, res, reply_markup=get_bot_btn())
    await bot.send_message(chat_id, "🌑 <b>Tun... (40s)</b>", reply_markup=get_bot_btn())
    game = games[chat_id]; game['night_actions'] = {}
    
    for uid, data in game['players'].items():
        if not data['is_alive']: continue
        if data['role'] in ['don', 'doctor', 'commissar']:
            kb = InlineKeyboardMarkup()
            for tid, tdata in game['players'].items():
                if tdata['is_alive']:
                    if data['role'] in ['don', 'commissar'] and tid == uid: continue
                    kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_{data['role']}_{tid}_{chat_id}"))
            kb.add(InlineKeyboardButton("⏭ O'tkazib yuborish", callback_data=f"act_{data['role']}_skip_{chat_id}"))
            
            if data['role'] == 'commissar':
                kb_com = InlineKeyboardMarkup().row(InlineKeyboardButton("🔍 Tekshirish", callback_data=f"com_check_{chat_id}"), InlineKeyboardButton("🔫 O'ldirish", callback_data=f"com_kill_{chat_id}"))
                await bot.send_message(uid, "Komissar, tanlang:", reply_markup=kb_com)
            else: await bot.send_message(uid, f"{data['role_name']} vazifangiz:", reply_markup=kb)
    await asyncio.sleep(40); await start_day(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith(('act_', 'com_')))
async def night_action_cb(callback: types.CallbackQuery):
    data = callback.data.split('_'); chat_id = int(data[-1]); mode = data[1]
    if mode in ['check', 'kill']:
        kb = InlineKeyboardMarkup()
        for tid, tdata in games[chat_id]['players'].items():
            if tdata['is_alive'] and tid != callback.from_user.id:
                kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_commissar_{mode}_{tid}_{chat_id}"))
        kb.add(InlineKeyboardButton("⏭ O'tkazib yuborish", callback_data=f"act_commissar_skip_{chat_id}"))
        await callback.message.edit_text("Nishonni tanlang:", reply_markup=kb); return
    
    role, target = data[1], data[2]
    if target == 'skip':
        skips = {'don': "🕶 Don tunda harakat qilmadi.", 'doctor': "💊 Doktor bugun dam oladi.", 'commissar': "🔍 Komissar tunda dam oldi."}
        await bot.send_message(chat_id, skips.get(role, "O'tkazib yuborildi.")); await callback.message.edit_text("O'tkazib yuborildi."); return

    target_id = int(target)
    if role == 'commissar' and data[2] == 'check':
        u_target = get_user_data(target_id)
        role_res = games[chat_id]['players'][target_id]['role_name']
        if u_target['fake_id'] > 0 and games[chat_id]['players'][target_id]['role'] == 'don':
            role_res = "Tinch aholi"
            u_target['fake_id'] -= 1
        await callback.message.edit_text(f"🔍 Natija: <b>{games[chat_id]['players'][target_id]['name']}</b> — <b>{role_res}</b>")
    else:
        games[chat_id]['night_actions'][role if role != 'commissar' else 'commissar_kill'] = target_id
        await callback.message.edit_text("Saqlandi.")

async def start_day(chat_id):
    game = games[chat_id]; await bot.send_message(chat_id, "🌞 <b>Tong otdi!</b>", reply_markup=get_bot_btn())
    k_maf = game['night_actions'].get('don'); k_com = game['night_actions'].get('commissar_kill'); saved = game['night_actions'].get('doctor')
    
    for d_id in [k_maf, k_com]:
        if d_id and d_id != saved:
            u_data = get_user_data(d_id)
            if u_data['shield'] > 0:
                u_data['shield'] -= 1
                await bot.send_message(chat_id, f"🛡 {get_mention(d_id, game['players'][d_id]['name'])}ga hujum bo'ldi, lekin himoya uni saqlab qoldi!")
            else:
                game['players'][d_id]['is_alive'] = False
                await bot.send_message(chat_id, f"💀 {get_mention(d_id, game['players'][d_id]['name'])} o'ldirildi. U <b>{game['players'][d_id]['role_name']}</b> edi.")
    
    await bot.send_message(chat_id, get_players_list_text(chat_id), reply_markup=get_bot_btn()); await start_voting(chat_id)

async def start_voting(chat_id):
    res = check_winner(chat_id)
    if res: return await bot.send_message(chat_id, res, reply_markup=get_bot_btn())
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish! (45s)</b>", reply_markup=get_bot_btn())
    game = games[chat_id]; game['votes'] = {}
    for uid, data in game['players'].items():
        if data['is_alive']:
            kb = InlineKeyboardMarkup()
            for tid, tdata in game['players'].items():
                if tdata['is_alive'] and tid != uid:
                    kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"v_{tid}_{chat_id}"))
            try: await bot.send_message(uid, "Ovoz bering:", reply_markup=kb)
            except: pass
    await asyncio.sleep(45); await process_voting_results(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith('v_'))
async def vote_handler(callback: types.CallbackQuery):
    _, tid, chat_id = callback.data.split('_'); chat_id = int(chat_id)
    await bot.send_message(chat_id, f"🗳 {get_mention(callback.from_user.id, callback.from_user.full_name)} --> {get_mention(tid, games[chat_id]['players'][int(tid)]['name'])}ga ovoz berdi!")
    games[chat_id]['votes'][callback.from_user.id] = int(tid)
    await callback.message.edit_text("Ovoz olindi.")

async def process_voting_results(chat_id):
    game = games[chat_id]
    if not game['votes']: return await start_night(chat_id)
    counts = {}
    for v in game['votes'].values(): counts[v] = counts.get(v, 0) + 1
    suspect_id = max(counts, key=counts.get)
    game['jury'] = {'l': [], 'd': []}
    await bot.send_message(chat_id, f"⚖️ <b>Sud:</b> {get_mention(suspect_id, game['players'][suspect_id]['name'])} osilsinmi? (20s)", reply_markup=jury_kb(suspect_id, chat_id, 0, 0))
    await asyncio.sleep(20)
    
    if len(game['jury']['l']) > len(game['jury']['d']):
        game['players'][suspect_id]['is_alive'] = False
        await bot.send_message(chat_id, f"💀 {game['players'][suspect_id]['name']} osildi.", reply_markup=get_bot_btn())
    else: await bot.send_message(chat_id, "🕊 Kechirildi.", reply_markup=get_bot_btn())
    await start_night(chat_id)

def jury_kb(sid, cid, l_cnt, d_cnt):
    return InlineKeyboardMarkup().row(InlineKeyboardButton(f"👍 {l_cnt}", callback_data=f"jr_l_{sid}_{cid}"), InlineKeyboardButton(f"👎 {d_cnt}", callback_data=f"jr_d_{sid}_{cid}"))

@dp.callback_query_handler(lambda c: c.data.startswith('jr_'))
async def jury_callback(callback: types.CallbackQuery):
    _, vote, sid, cid = callback.data.split('_'); cid = int(cid); sid = int(sid); game = games[cid]; uid = callback.from_user.id
    if uid not in game['players'] or not game['players'][uid]['is_alive'] or uid == sid or uid in game['jury']['l'] or uid in game['jury']['d']:
        return await callback.answer("Ruxsat yo'q!")
    game['jury'][vote].append(uid)
    await callback.message.edit_reply_markup(reply_markup=jury_kb(sid, cid, len(game['jury']['l']), len(game['jury']['d'])))

def get_players_list_text(chat_id):
    game = games.get(chat_id)
    text = "<b>🎭 Tirik o'yinchilar:</b>\n"
    for uid, data in game['players'].items():
        if data['is_alive']: text += f"• {get_mention(uid, data['name'])}\n"
    return text

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

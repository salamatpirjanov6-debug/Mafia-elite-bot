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

def get_mention(uid, name):
    return f"<a href='tg://user?id={uid}'>{name}</a>"

def get_players_list_text(chat_id):
    game = games.get(chat_id)
    text = "<b>🎭 Tirik o'yinchilar:</b>\n"
    for uid, data in game['players'].items():
        if data['is_alive']:
            text += f"• {get_mention(uid, data['name'])}\n"
    return text

def check_winner(chat_id):
    """3-band: G'oliblar va mag'lublar ro'yxati bilan o'yinni yakunlash"""
    game = games[chat_id]
    mafias = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] in ['don', 'mafia']]
    citizens = [u for u, d in game['players'].items() if d['is_alive'] and d['role'] not in ['don', 'mafia']]
    
    winner_team = None
    if not mafias: winner_team = 'citizens'
    elif len(mafias) >= len(citizens): winner_team = 'mafia'
    
    if winner_team:
        text = "🏆 <b>O'yin yakunlandi!</b>\n\n"
        winners = []
        others = []
        for uid, data in game['players'].items():
            is_mafia = data['role'] in ['don', 'mafia']
            if (winner_team == 'mafia' and is_mafia) or (winner_team == 'citizens' and not is_mafia):
                winners.append(f"• {get_mention(uid, data['name'])} ({data['role_name']})")
            else:
                others.append(f"• {get_mention(uid, data['name'])} ({data['role_name']})")
        
        text += "<b>🥇 G'oliblar:</b>\n" + "\n".join(winners)
        text += "\n\n<b>👥 Qolgan o'yinchilar:</b>\n" + "\n".join(others)
        return text
    return None

# --- O'YIN BOSHLASH ---

@dp.message_handler(commands=['new_game'])
async def new_game(message: types.Message):
    if message.chat.type == 'private': return
    games[message.chat.id] = {
        'players': {}, 'state': 'joining', 'night_actions': {}, 
        'votes': {}, 'last_word_user': None, 'jury': {'l': [], 'd': []}
    }
    # 4-band: Botga o'tish tugmasi
    link = await get_start_link(payload=f"join_{message.chat.id}", encode=False)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🤖 Botga o'tish va qo'shilish", url=link))
    await message.answer("📢 <b>Mafia boshlanmoqda!</b>\nO'yinda qatnashish uchun botga o'ting.", reply_markup=kb)

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    if args and args.startswith('join_'):
        group_id = int(args.replace('join_', ''))
        user_id = message.from_user.id
        if group_id not in games or games[group_id]['state'] != 'joining': return
        if user_id not in games[group_id]['players']:
            games[group_id]['players'][user_id] = {'name': message.from_user.full_name, 'is_alive': True, 'role': None}
            await message.answer("✅ Siz o'yinga qo'shildingiz! Guruhga qayting.")
            kb = InlineKeyboardMarkup()
            link = await get_start_link(payload=f"join_{group_id}", encode=False)
            kb.add(InlineKeyboardButton("🎮 Ro'yxatga qo'shilish", url=link))
            if len(games[group_id]['players']) >= 4:
                kb.add(InlineKeyboardButton("🚀 O'yinni boshlash", callback_data=f"startnow_{group_id}"))
            await bot.send_message(group_id, f"➕ {get_mention(user_id, message.from_user.full_name)} qo'shildi!", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('startnow_'))
async def start_now(callback: types.CallbackQuery):
    chat_id = int(callback.data.split('_')[1])
    game = games[chat_id]
    game['state'] = 'playing'
    uids = list(game['players'].keys())
    random.shuffle(uids)

    # Rollar taqsimoti
    game['players'][uids[0]]['role'] = 'don'; game['players'][uids[0]]['role_name'] = "Don"
    game['players'][uids[1]]['role'] = 'doctor'; game['players'][uids[1]]['role_name'] = "Doktor"
    game['players'][uids[2]]['role'] = 'commissar'; game['players'][uids[2]]['role_name'] = "Komissar"
    for i in range(3, len(uids)):
        if i == 3 and len(uids) >= 5:
            game['players'][uids[i]]['role'] = 'mafia'; game['players'][uids[i]]['role_name'] = "Mafia"
        else:
            game['players'][uids[i]]['role'] = 'citizen'; game['players'][uids[i]]['role_name'] = "Tinch aholi"
    
    for uid, data in game['players'].items():
        try: await bot.send_message(uid, f"Sizning rolingiz: <b>{data['role_name']}</b>")
        except: pass
        
    await bot.send_message(chat_id, "🎭 O'yin boshlandi!\n" + get_players_list_text(chat_id))
    await start_night(chat_id)

# --- TUN BOSQICHI ---

async def start_night(chat_id):
    res = check_winner(chat_id)
    if res: return await bot.send_message(chat_id, res)

    await bot.send_message(chat_id, "🌑 <b>Tun... (40 soniya)</b>")
    game = games[chat_id]
    game['night_actions'] = {}
    
    for uid, data in game['players'].items():
        if not data['is_alive']: continue
        kb = InlineKeyboardMarkup()
        if data['role'] in ['don', 'mafia', 'doctor', 'commissar']:
            for tid, tdata in game['players'].items():
                if not tdata['is_alive']: continue
                # 2-band: Don va Komissar o'zini tanlay olmaydi (Doktor mumkin)
                if data['role'] in ['don', 'commissar', 'mafia'] and tid == uid: continue
                kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_{data['role']}_{tid}_{chat_id}"))
            
            # 1-band: O'tkazib yuborish tugmasi
            kb.add(InlineKeyboardButton("⏭ O'tkazib yuborish", callback_data=f"act_{data['role']}_skip_{chat_id}"))
            
            if data['role'] == 'commissar':
                kb_com = InlineKeyboardMarkup().row(
                    InlineKeyboardButton("🔍 Tekshirish", callback_data=f"com_check_{chat_id}"),
                    InlineKeyboardButton("🔫 O'ldirish", callback_data=f"com_kill_{chat_id}")
                )
                await bot.send_message(uid, "Komissar, nima qilasiz?", reply_markup=kb_com)
            else:
                await bot.send_message(uid, f"{data['role_name']} vazifangizni tanlang:", reply_markup=kb)

    await asyncio.sleep(40)
    await start_day(chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith(('act_', 'com_')))
async def night_action_cb(callback: types.CallbackQuery):
    data = callback.data.split('_')
    chat_id = int(data[-1])
    mode = data[1]
    
    if mode in ['check', 'kill']:
        kb = InlineKeyboardMarkup()
        for tid, tdata in games[chat_id]['players'].items():
            if tdata['is_alive'] and tid != callback.from_user.id:
                kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"act_commissar_{mode}_{tid}_{chat_id}"))
        kb.add(InlineKeyboardButton("⏭ O'tkazib yuborish", callback_data=f"act_commissar_skip_{chat_id}"))
        await callback.message.edit_text("Nishonni tanlang:", reply_markup=kb)
        return
    
    role = data[1]
    target = data[2]
    
    # 1-band: O'tkazib yuborish mantiqi
    if target == 'skip':
        skip_msg = {
            'don': "🕶 Don bugun hech kimni bezovta qilmadi.",
            'mafia': "🔫 Mafia bugun dam olishga qaror qildi.",
            'doctor': "💊 Doktor bugun hech kimni davolamaydi.",
            'commissar': "🔍 Komissar bugun dam oladi."
        }
        await bot.send_message(chat_id, skip_msg.get(role, "Harakat o'tkazib yuborildi."))
        await callback.message.edit_text("Siz harakatni o'tkazib yubordingiz.")
        return

    target_id = int(target)
    if role == 'commissar' and data[2] == 'check':
        target_role = games[chat_id]['players'][target_id]['role_name']
        await callback.message.edit_text(f"🔍 Natija: <b>{games[chat_id]['players'][target_id]['name']}</b> — <b>{target_role}</b>")
    else:
        games[chat_id]['night_actions'][role] = target_id
        await callback.message.edit_text("Tanlov qabul qilindi.")

    notifs = {'don': "🕶 Don nishon tanladi.", 'mafia': "🔫 Mafia nishon tanladi.", 'doctor': "💊 Doktor davolash uchun ketdi.", 'commissar': "🔍 Komissar harakatda."}
    if role in notifs: await bot.send_message(chat_id, notifs[role])

# --- TONG VA SUD ---

async def start_day(chat_id):
    game = games[chat_id]
    await bot.send_message(chat_id, "🌞 <b>Tong otdi!</b>")
    
    killed_mafia = game['night_actions'].get('don') or game['night_actions'].get('mafia')
    killed_com = game['night_actions'].get('commissar') if 'commissar' in game['night_actions'] else None
    saved = game['night_actions'].get('doctor')
    
    death_ids = []
    if killed_mafia and killed_mafia != saved: death_ids.append(killed_mafia)
    if killed_com: death_ids.append(killed_com)
    
    if death_ids:
        for d_id in list(set(death_ids)):
            p = game['players'][d_id]
            p['is_alive'] = False
            await bot.send_message(chat_id, f"💀 {get_mention(d_id, p['name'])} o'ldirildi. U <b>{p['role_name']}</b> edi.")
    else:
        await bot.send_message(chat_id, "🛡 Tunda hech kim o'lmadi.")

    await bot.send_message(chat_id, get_players_list_text(chat_id))
    await start_voting(chat_id)

async def start_voting(chat_id):
    res = check_winner(chat_id)
    if res: return await bot.send_message(chat_id, res)
    await bot.send_message(chat_id, "🗳 <b>Ovoz berish! (45s)</b>")
    game = games[chat_id]; game['votes'] = {}
    for uid, data in game['players'].items():
        if data['is_alive']:
            kb = InlineKeyboardMarkup()
            for tid, tdata in game['players'].items():
                if tdata['is_alive'] and tid != uid:
                    kb.add(InlineKeyboardButton(tdata['name'], callback_data=f"v_{tid}_{chat_id}"))
            try: await bot.send_message(uid, "Kimga ovoz berasiz?", reply_markup=kb)
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
    await bot.send_message(chat_id, f"⚖️ <b>Sud:</b> {get_mention(suspect_id, game['players'][suspect_id]['name'])} osilsinmi?", reply_markup=jury_kb(suspect_id, chat_id, 0, 0))

def jury_kb(sid, cid, l_cnt, d_cnt):
    return InlineKeyboardMarkup().row(InlineKeyboardButton(f"👍 {l_cnt}", callback_data=f"jr_l_{sid}_{cid}"), InlineKeyboardButton(f"👎 {d_cnt}", callback_data=f"jr_d_{sid}_{cid}"))

@dp.callback_query_handler(lambda c: c.data.startswith('jr_'))
async def jury_callback(callback: types.CallbackQuery):
    _, vote, sid, cid = callback.data.split('_'); cid = int(cid); sid = int(sid); game = games[cid]
    if callback.from_user.id == sid or callback.from_user.id in game['jury']['l'] or callback.from_user.id in game['jury']['d']: return await callback.answer("Ruxsat yo'q!")
    game['jury'][vote].append(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=jury_kb(sid, cid, len(game['jury']['l']), len(game['jury']['d'])))

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

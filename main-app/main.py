import discord  # Импорт библиотеки для работы с Discord API
from discord.ext import commands  # Импорт расширения для команд бота
import json  # Импорт модуля для работы с JSON
import logging  # Импорт модуля логирования
import os  # Импорт модуля для работы с операционной системой
import sqlite3  # Импорт модуля для работы с SQLite базой данных
from datetime import datetime, timedelta  # Импорт классов для работы с датой и временем
from dotenv import load_dotenv  # Импорт функции для загрузки переменных окружения из файла .env
import asyncio

# Загрузка переменных окружения из файла .env (убедитесь, что файл .env добавлен в .gitignore)
load_dotenv()

# Получение токена бота из переменных окружения
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN не найден. Убедитесь, что он задан в переменных окружения или в файле .env")

# Настройка логирования: все логи записываются в файл 'bot.json'
logging.basicConfig(filename='../bot.json', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Загрузка настроек из файла config.json (без токена)
config_file_path = "../config.json"
with open(config_file_path, "r") as config_file:
    config = json.load(config_file)

# Присвоение значений из файла конфигурации
FINE_CHANNEL_ID = config["FINE_CHANNEL_ID"]
NOTIFY_CHANNEL_ID = config["NOTIFY_CHANNEL_ID"]
LOG_CHANNEL_ID = config["LOG_CHANNEL_ID"]
ROLE_ID = config["ROLE_ID"]
CONTENT_MAKER_ROLE_ID = config["CONTENT_MAKER_ROLE_ID"]
FINANCIER_ROLE_ID = config["FINANCIER_ROLE_ID"]
FINE_ROLE_ID = config["FINE_ROLE_ID"]
# Для пересылки сообщений по мапе будем использовать данные из config["role_channel_map"]
# Убираем жестко заданный channel_role_map

# Настройка намерений (intents) для получения необходимых событий от Discord
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

# Создание экземпляра бота с префиксом "!" и заданными намерениями
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")
DB_NAME = "../bot.db"  # Имя файла базы данных

# Функция для загрузки сообщений из файла messages.json
def load_messages():
    with open("../messages.json", "r", encoding="utf-8") as f:
        return json.load(f)

messages = load_messages()

# Функции для работы с config.json (динамическое обновление мапы)
def load_config_file():
    with open(config_file_path, "r") as config_file:
        return json.load(config_file)

def save_config_file(new_config):
    with open(config_file_path, "w") as config_file:
        json.dump(new_config, config_file, indent=4)

# Инициализация базы данных с использованием контекстного менеджера
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        c = conn.cursor()
        # Таблица баланса
        c.execute("""
            CREATE TABLE IF NOT EXISTS balances (
                member_id TEXT PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                nickname TEXT
            )
        """)
        # Таблица транзакций
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                member_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                note TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица штрафов
        c.execute("""
            CREATE TABLE IF NOT EXISTS fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT,
                is_closed INTEGER DEFAULT 0
            )
        """)
        # Таблица сборов
        c.execute("""
            CREATE TABLE IF NOT EXISTS parties (
                party_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id TEXT NOT NULL,
                info TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица участников сборов
        c.execute("""
            CREATE TABLE IF NOT EXISTS party_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                party_id INTEGER NOT NULL,
                member_id TEXT NOT NULL,
                FOREIGN KEY(party_id) REFERENCES parties(party_id) ON DELETE CASCADE
            )
        """)
        conn.commit()

init_db()  # Инициализация базы данных при запуске

# Функция для проверки, имеет ли участник сервера заданную роль
async def has_role(member, role_id):
    role = discord.utils.get(member.guild.roles, id=role_id)
    return role in member.roles if role else False

@bot.event
async def on_ready():
    logging.info(f"Бот {bot.user} запущен!")
    print(f"Бот {bot.user} запущен!")
    print("Зарегистрированные команды:", [cmd.name for cmd in bot.commands])

# ==============================
# Команды для управления мапой (роль -> каналы)
# ==============================
@bot.command(name="add_channel_role")
async def add_channel_role(ctx, role: discord.Role, channel: discord.TextChannel):
    # Только администратор может менять настройки
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ У тебя нет прав для изменения настроек.", delete_after=5)
        return

    cfg = load_config_file()
    if "role_channel_map" not in cfg:
        cfg["role_channel_map"] = {}

    role_id = str(role.id)
    channel_id = str(channel.id)

    if role_id not in cfg["role_channel_map"]:
        cfg["role_channel_map"][role_id] = []

    if channel_id in cfg["role_channel_map"][role_id]:
        await ctx.send(f"⚠️ Канал {channel.mention} уже привязан к роли {role.mention}.", delete_after=5)
        return

    cfg["role_channel_map"][role_id].append(channel_id)
    save_config_file(cfg)
    await ctx.send(f"✅ Канал {channel.mention} привязан к роли {role.mention}.")

@bot.command(name="remove_channel_role")
async def remove_channel_role(ctx, role: discord.Role, channel: discord.TextChannel):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ У тебя нет прав для изменения настроек мапы.", delete_after=5)
        return

    cfg = load_config_file()
    role_id = str(role.id)
    channel_id = str(channel.id)

    if "role_channel_map" not in cfg or role_id not in cfg["role_channel_map"]:
        await ctx.send(f"⚠️ Роль {role.mention} не имеет привязанных каналов.", delete_after=5)
        return

    if channel_id not in cfg["role_channel_map"][role_id]:
        await ctx.send(f"⚠️ Канал {channel.mention} не привязан к роли {role.mention}.", delete_after=5)
        return

    cfg["role_channel_map"][role_id].remove(channel_id)
    save_config_file(cfg)
    await ctx.send(f"✅ Канал {channel.mention} отвязан от роли {role.mention}.")

@bot.command(name="list_channel_roles")
async def list_channel_roles(ctx):
    cfg = load_config_file()
    mapping = cfg.get("role_channel_map", {})
    if not mapping:
        await ctx.send("ℹ️ Мапа ролей и каналов пуста.")
        return

    msg = "Список привязок:\n"
    for role_id, channels in mapping.items():
        role_obj = ctx.guild.get_role(int(role_id))
        role_name = role_obj.name if role_obj else f"ID:{role_id}"
        channel_mentions = []
        for ch_id in channels:
            channel_obj = ctx.guild.get_channel(int(ch_id))
            if channel_obj:
                channel_mentions.append(channel_obj.mention)
            else:
                channel_mentions.append(f"ID:{ch_id}")
        msg += f"**{role_name}**: {', '.join(channel_mentions)}\n"
    await ctx.send(msg)

# ==============================
# Функционал пересылки сообщений из назначенных каналов в ЛС
# ==============================
@bot.event
async def on_message(message):
    # Игнорируем сообщения от бота и других ботов
    if message.author.bot:
        return

    cfg = load_config_file()
    role_channel_map = cfg.get("role_channel_map", {})

    # Для предотвращения дублирования, будем хранить ID участников, которым уже отправили сообщение
    sent_members = set()

    # Перебираем каждую роль и проверяем, назначен ли канал к этой роли
    for role_id_str, channel_ids in role_channel_map.items():
        if str(message.channel.id) in channel_ids:
            role_obj = message.guild.get_role(int(role_id_str))
            if not role_obj:
                continue  # если роль удалена, пропускаем
            # Получаем всех участников с этой ролью
            for member in message.guild.members:
                if member.bot:
                    continue
                if role_obj in member.roles and member.id not in sent_members:
                    try:
                        embed = discord.Embed(
                            title=f"Новое сообщение из #{message.channel.name}",
                            description=message.content or "*Нет текста*",
                            color=discord.Color.blue()
                        )
                        embed.set_footer(text=f"Автор: {message.author.display_name}")
                        await member.send(embed=embed)
                        sent_members.add(member.id)
                        await asyncio.sleep(1)  # ограничиваем частоту отправки
                    except discord.Forbidden:
                        logging.warning(f"Не удалось отправить DM пользователю {member.name}")
                    except Exception as e:
                        logging.error(f"Ошибка отправки DM пользователю {member.name}: {e}")

    await bot.process_commands(message)

# ==============================
# Класс для управления балансом пользователей
# ==============================
class BalanceManager:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name

    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def get_balance(self, member_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT balance FROM balances WHERE member_id = ?", (str(member_id),))
            row = c.fetchone()
            return row["balance"] if row else 0

    def deposit(self, member_id, amount, nickname="", by=None, note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        with self.get_connection() as conn:
            c = conn.cursor()
            current = self.get_balance(member_id)
            new_balance = current + amount
            c.execute("INSERT OR REPLACE INTO balances (member_id, balance, nickname) VALUES (?, ?, ?)",
                      (str(member_id), new_balance, nickname))
            c.execute("INSERT INTO transactions (type, member_id, amount, note) VALUES (?, ?, ?, ?)",
                      ("DEPOSIT", str(member_id), amount, f"by {by}: {note}"))
            conn.commit()

    def withdraw(self, member_id, amount, nickname="", by=None, note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        current = self.get_balance(member_id)
        new_balance = current - amount  # не проверяем на отрицательный результат
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE balances SET balance = ?, nickname = ? WHERE member_id = ?",
                    (new_balance, nickname, str(member_id)))
            c.execute("INSERT INTO transactions (type, member_id, amount, note) VALUES (?, ?, ?, ?)",
                    ("WITHDRAW", str(member_id), -amount, f"by {by}: {note}"))
            conn.commit()


    def transfer(self, from_member, to_member, amount, from_nickname="", to_nickname="", note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
    # убираем проверку остатка:
    # if self.get_balance(from_member) < amount:
    #     raise ValueError("Недостаточно средств для перевода")
        self.withdraw(from_member, amount, nickname=from_nickname, by=from_member, note=f"Transfer to {to_member}. {note}")
        self.deposit(to_member, amount, nickname=to_nickname, by=from_member, note=f"Transfer from {from_member}. {note}")



    def top_balances(self, top_n=40):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT member_id, balance, nickname FROM balances ORDER BY balance DESC LIMIT ?", (top_n,))
            rows = c.fetchall()
            return [(row["member_id"], row["balance"], row["nickname"]) for row in rows]

    def get_history(self, member_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT type, amount, note, timestamp FROM transactions WHERE member_id = ? ORDER BY timestamp DESC LIMIT 10", (str(member_id),))
            rows = c.fetchall()
            return [(row["type"], row["amount"], row["note"], row["timestamp"]) for row in rows]

balance_manager = BalanceManager()

# ==============================
# Команды для управления балансом (balance)
# ==============================
@bot.group(invoke_without_command=True)
async def balance(ctx):
    current_balance = balance_manager.get_balance(ctx.author.id)
    await ctx.send(messages["balance_show"].format(user_mention=ctx.author.mention, balance=current_balance))

@balance.command(name="deposit")
async def balance_deposit(ctx, member: discord.Member, amount: int):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send("У вас нет прав для пополнения баланса.")
        return
    try:
        balance_manager.deposit(member.id, amount, nickname=member.display_name, by=ctx.author.id, note="Deposit command")
        await ctx.send(messages["balance_deposit_success"].format(member_mention=member.mention, amount=amount))
    except Exception as e:
        await ctx.send(f"Ошибка: {str(e)}")

@balance.command(name="withdraw")
async def balance_withdraw(ctx, member: discord.Member, amount: int):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send("У вас нет прав для снятия средств.")
        return
    try:
        balance_manager.withdraw(member.id, amount, nickname=member.display_name, by=ctx.author.id, note="Withdraw command")
        await ctx.send(messages["balance_withdraw_success"].format(member_mention=member.mention, amount=amount))
    except Exception as e:
        await ctx.send(f"Ошибка: {str(e)}")

@balance.command(name="transfer")
async def balance_transfer(ctx, member: discord.Member, amount: int):
    try:
        balance_manager.transfer(ctx.author.id, member.id, amount, 
                                 from_nickname=ctx.author.display_name, to_nickname=member.display_name,
                                 note="Transfer command")
        await ctx.send(messages["balance_transfer_success"].format(sender_mention=ctx.author.mention, recipient_mention=member.mention, amount=amount))
    except Exception as e:
        await ctx.send(f"Ошибка: {str(e)}")

@balance.command(name="top")
async def balance_top(ctx):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send(messages.get("balance_top_no_permission", "У вас нет прав для просмотра топа баланса."))
        return
    top_list = balance_manager.top_balances()
    msg = "Топ участников по балансу:\n"
    for member_id, bal, nickname in top_list:
        name = nickname if nickname else str(member_id)
        msg += f"{name}: {bal} серебра\n"
    await ctx.send(msg)

@balance.command(name="history")
async def balance_history(ctx, member: discord.Member = None):
    target = member if member else ctx.author
    history = balance_manager.get_history(target.id)
    if not history:
        await ctx.send(messages.get("balance_history_empty", "История транзакций пуста."))
        return
    history_lines = "\n".join([f"{t} {amt} ({note}) - {timestamp}" for t, amt, note, timestamp in history])
    await ctx.send(messages["balance_history"].format(user_mention=target.mention, history=history_lines))

# ==============================
# Функции и команды для управления сборами (Party)
# ==============================
def create_party(creator_id, info):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("INSERT INTO parties (creator_id, info) VALUES (?, ?)", (str(creator_id), info))
        party_id = c.lastrowid
        c.execute("INSERT INTO party_members (party_id, member_id) VALUES (?, ?)", (party_id, str(creator_id)))
        conn.commit()
    return party_id

def delete_party(party_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM parties WHERE party_id = ?", (party_id,))
        c.execute("DELETE FROM party_members WHERE party_id = ?", (party_id,))
        conn.commit()
    return True

def add_party_member(party_id, member_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO party_members (party_id, member_id) VALUES (?, ?)", (party_id, str(member_id)))
        conn.commit()

def remove_party_member(party_id, member_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM party_members WHERE party_id = ? AND member_id = ?", (party_id, str(member_id)))
        conn.commit()

def get_active_parties():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT party_id, creator_id, info, created_at FROM parties")
        rows = c.fetchall()
        return [(row["party_id"], row["creator_id"], row["info"], row["created_at"]) for row in rows]

@bot.group(invoke_without_command=True)
async def party(ctx):
    parties = get_active_parties()
    if parties:
        msg = messages.get("party_active_header", "Активные сборы:\n")
        for p_id, creator_id, info, _ in parties:
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM party_members WHERE party_id = ?", (p_id,))
                count = c.fetchone()[0]
            msg += messages["party_line"].format(party_id=p_id, info=info, count=count)
        await ctx.send(msg)
    else:
        await ctx.send(messages.get("party_no_active", "Нет активных сборов."))

@party.command(name="create")
async def party_create(ctx, *, info: str):
    if not await has_role(ctx.author, CONTENT_MAKER_ROLE_ID):
        await ctx.send("У вас нет прав для создания сбора.")
        return
    party_id = create_party(ctx.author.id, info)
    await ctx.send(messages["party_create_success"].format(party_id=party_id, info=info))

@party.command(name="delete")
async def party_delete(ctx, party_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT creator_id FROM parties WHERE party_id = ?", (party_id,))
        row = c.fetchone()
    if not row:
        await ctx.send(messages["party_not_found"])
        return
    creator_id = int(row[0])
    if ctx.author.id != creator_id and not await has_role(ctx.author, CONTENT_MAKER_ROLE_ID):
        await ctx.send(messages["party_no_permission_delete"])
        return
    if delete_party(party_id):
        await ctx.send(messages["party_delete_success"].format(party_id=party_id))
    else:
        await ctx.send("Ошибка при удалении сбора.")

@party.command(name="join")
async def party_join(ctx, party_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT party_id FROM parties WHERE party_id = ?", (party_id,))
        row = c.fetchone()
    if not row:
        await ctx.send(messages["party_not_found"])
        return
    add_party_member(party_id, ctx.author.id)
    await ctx.send(messages["party_join_success"].format(user_mention=ctx.author.mention, party_id=party_id))

@party.command(name="leave")
async def party_leave(ctx, party_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT party_id FROM parties WHERE party_id = ?", (party_id,))
        row = c.fetchone()
    if not row:
        await ctx.send(messages["party_not_found"])
        return
    remove_party_member(party_id, ctx.author.id)
    await ctx.send(messages["party_leave_success"].format(user_mention=ctx.author.mention, party_id=party_id))

@party.command(name="notify")
async def party_notify(ctx, party_id: int, *, message_text: str):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT member_id FROM party_members WHERE party_id = ?", (party_id,))
        members = c.fetchall()
    if not members:
        await ctx.send(messages["party_notify_no_members"])
        return
    for (member_id,) in members:
        if int(member_id) == ctx.author.id:
            continue
        member = ctx.guild.get_member(int(member_id))
        if member:
            try:
                await member.send(f"Уведомление по сбору ID {party_id}: {message_text}")
            except discord.Forbidden:
                logging.warning(f"Не удалось отправить уведомление {member.name}.")
    await ctx.send(messages["party_notify_success"])

# ==============================
# Команды для управления штрафами
# ==============================
@bot.command(name="fine")
async def issue_fine(ctx, user: discord.Member, amount: int, *, reason: str = "Без причины"):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send(messages["fine_no_permission"])
        return

    try:
        # Снимаем средства, даже если баланс уходит в минус (withdraw уже позволяет)
        balance_manager.withdraw(user.id, amount, nickname=user.display_name, by=ctx.author.id, note=f"Fine: {reason}")
    except Exception as e:
        await ctx.send(messages["fine_invalid_amount"].format(error_message=str(e)))
        return

    # Логируем штраф в базу
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO fines (user_id, amount, reason) VALUES (?, ?, ?)", (str(user.id), amount, reason))
        fine_id = c.lastrowid
        conn.commit()

    # Создаём embed-уведомление
    embed = discord.Embed(
        title="🚫 **Новый штраф!** 🚫",
        color=discord.Color.red()
    )
    embed.add_field(name="**Нарушитель:**", value=user.mention, inline=False)
    embed.add_field(name="**Размер штрафа:**", value=f"{amount} серебра", inline=False)
    embed.add_field(name="**Причина:**", value=reason, inline=False)
    embed.add_field(name="**Выдал штраф:**", value=ctx.author.mention, inline=False)
    embed.add_field(name="**Номер штрафа:**", value=fine_id, inline=False)

    fine_channel = ctx.guild.get_channel(FINE_CHANNEL_ID)
    if fine_channel:
        await fine_channel.send(embed=embed)

    fine_role = discord.utils.get(ctx.guild.roles, id=FINE_ROLE_ID)
    if fine_role and fine_role not in user.roles:
        await user.add_roles(fine_role)

    # Пробуем отправить сообщение в личку нарушителю
    try:
        await user.send(embed=embed)
        status_msg = messages["fine_sent_to_dm"].format(user_mention=user.mention)
    except discord.Forbidden:
        status_msg = messages["fine_failed_to_dm"].format(user_mention=user.mention)

    log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"✅ Штраф для {user.mention} отправлен в {fine_channel.mention}!")
        await log_channel.send(status_msg)

    logging.info(f"Штраф выдан: {user} | Сумма: {amount} | Причина: {reason} | Выдал: {ctx.author}")

@bot.command(name="close_fine")
async def close_fine(ctx, fine_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, is_closed FROM fines WHERE id = ?", (fine_id,))
        result = c.fetchone()
        
        if result is None:
            await ctx.send(f"❗ Штраф с номером `{fine_id}` не найден.")
            return
        
        user_id, is_closed = result  # Теперь user_id точно определён
        
        if is_closed == 1:
            await ctx.send(f"❗ Штраф с номером `{fine_id}` уже закрыт.")
            return
        
        c.execute("UPDATE fines SET is_closed = 1 WHERE id = ?", (fine_id,))
        conn.commit()

    # Получаем объект пользователя
    user = ctx.guild.get_member(int(user_id))
    if user is None:
        await ctx.send(f"❗ Пользователь с ID `{user_id}` не найден на сервере.")
        return
    
    # Получаем роль штрафника
    fine_role = discord.utils.get(ctx.guild.roles, id=FINE_ROLE_ID)
    if fine_role is None:
        await ctx.send(f"❗ Роль штрафника (ID `{FINE_ROLE_ID}`) не найдена. Проверь настройки.")
        return

    # Проверяем, есть ли у пользователя эта роль
    if fine_role not in user.roles:
        await ctx.send(f"⚠️ У {user.mention} нет роли штрафника, снимать нечего.")
        return

    # Пробуем снять роль и ловим ошибки
    try:
        await user.remove_roles(fine_role)
        await ctx.send(f"✅ Роль штрафника снята с {user.mention}.")
    except discord.Forbidden:
        await ctx.send(f"❌ У меня нет прав снимать роль {fine_role.mention}. Проверь права бота!")
    except Exception as e:
        await ctx.send(f"❌ Ошибка при снятии роли: {e}")


# ==============================
# Команда для обновления сообщений (update_message)
# ==============================
@bot.command(name="update_message")
async def update_message_command(ctx, key: str, *, new_message: str):
    if not await has_role(ctx.author, ROLE_ID):
        await ctx.send(messages["update_message_no_permission"])
        return
    current = load_messages()
    current[key] = new_message
    with open("messages.json", "w", encoding="utf-8") as f:
        json.dump(current, f, indent=4, ensure_ascii=False)
    await ctx.send(messages["update_message_success"].format(key=key))

@bot.command(name="m")
async def send_message(ctx, members: commands.Greedy[discord.Member], roles: commands.Greedy[discord.Role], *, message_text: str):
    """Отправляет личное сообщение указанным пользователям и участникам упомянутых ролей."""
    recipients = set(members)  # Используем set, чтобы избежать дублирования

    # Добавляем всех участников, у которых есть упомянутые роли
    for role in roles:
        recipients.update(role.members)

    if not recipients:
        await ctx.send("⚠️ Использование: `!send_message @пользователь1 @роль1 ... сообщение`")
        return

    sent_count = 0

    for member in recipients:
        if member.bot:
            continue  # Пропускаем ботов

        try:
            await member.send(f"📩 **Сообщение от {ctx.author.display_name}:**\n{message_text}")
            sent_count += 1
        except discord.Forbidden:
            await ctx.send(f"⚠️ Не удалось отправить сообщение {member.mention}. Возможно, у него закрыты ЛС.")

    if sent_count:
        await ctx.send(f"✅ Сообщение успешно отправлено {sent_count} пользователям.")
    else:
        await ctx.send("⚠️ Не удалось отправить сообщение ни одному пользователю.")

    try:
        await asyncio.sleep(2)
        await ctx.message.delete()  # Удаляет команду через 2 секунды
    except discord.Forbidden:
        pass



@bot.listen("on_message")
async def delete_command_messages(message):
    if message.author.bot:
        return  # Игнорируем сообщения ботов

    ctx = await bot.get_context(message)
    if ctx.valid:
        try:
            await asyncio.sleep(3)
            await message.delete()  # Удаляем сообщение пользователя с командой
        except discord.Forbidden:
            pass  # Игнорируем, если нет прав на удаление



@bot.command(name="help")
async def help_command(ctx):
    help_message = (
        "**Справка по командам бота:**\n\n"
        "**Настройка каналов и ролей:**\n"
        "`!add_channel_role [роль] [канал]` - Привязать канал к роли (только администратор).\n"
        "`!remove_channel_role [роль] [канал]` - Отвязать канал от роли (только администратор).\n"
        "`!list_channel_roles` - Список привязок ролей и каналов.\n\n"
        "**Баланс:**\n"
        "`!balance` - Показать баланс.\n"
        "`!balance deposit [пользователь] [сумма]` - Пополнить баланс (только финансист).\n"
        "`!balance withdraw [пользователь] [сумма]` - Снять средства (только финансист).\n"
        "`!balance transfer [пользователь] [сумма]` - Перевод средств между участниками.\n"
        "`!balance top` - Топ участников по балансу (только финансист).\n"
        "`!balance history [пользователь]` - История транзакций.\n\n"
        "**Сборы:**\n"
        "`!party` - Показать активные сборы.\n"
        "`!party create [информация]` - Создать сбор (только контент-мейкер).\n"
        "`!party delete [ID сбора]` - Удалить сбор.\n"
        "`!party join [ID сбора]` - Присоединиться к сбору.\n"
        "`!party leave [ID сбора]` - Покинуть сбор.\n"
        "`!party notify [ID сбора] [сообщение]` - Уведомить участников сбора.\n\n"
        "**Штрафы:**\n"
        "`!fine [пользователь] [сумма] [причина]` - Выдать штраф (только финансист).\n"
        "`!close_fine [номер штрафа]` - Закрыть штраф и снять роль штрафника.\n\n"
        "**Обновление сообщений:**\n"
        "`!update_message [ключ] [новое сообщение]` - Обновить сообщение (только с определённой ролью).\n"
        "`!send_message [пользователь1] [пользователь2] ... [сообщение]` - Отправить сообщение в ЛС.\n"
        "`!help` - Показать это сообщение."
    )
    await ctx.send(help_message)


# Запуск бота с использованием токена из переменных окружения
bot.run(TOKEN)

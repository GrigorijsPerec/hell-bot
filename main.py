import discord  # Импорт библиотеки для работы с Discord API
from discord.ext import commands  # Импорт расширения для команд бота
import json  # Импорт модуля для работы с JSON
import logging  # Импорт модуля логирования
import os  # Импорт модуля для работы с операционной системой
import sqlite3  # Импорт модуля для работы с SQLite базой данных
from datetime import datetime, timedelta  # Импорт классов для работы с датой и временем
from dotenv import load_dotenv  # Импорт функции для загрузки переменных окружения из файла .env

# Загрузка переменных окружения из файла .env (убедитесь, что файл .env добавлен в .gitignore)
load_dotenv()

# Получение токена бота из переменных окружения
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN не найден. Убедитесь, что он задан в переменных окружения или в файле .env")

# Настройка логирования: все логи записываются в файл 'bot.txt'
logging.basicConfig(filename='bot.txt', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Загрузка остальных настроек из файла config.json (без токена)
config_file_path = "config.json"
default_config = {
    "FINE_CHANNEL_ID": 0,
    "NOTIFY_CHANNEL_ID": 0,
    "LOG_CHANNEL_ID": 0,
    "ROLE_ID": 0,
    "CONTENT_MAKER_ROLE_ID": 0,
    "FINANCIER_ROLE_ID": 0
}

# Если config.json отсутствует, создаём его с настройками по умолчанию
if not os.path.exists(config_file_path):
    with open(config_file_path, "w") as config_file:
        json.dump(default_config, config_file, indent=4)
        print("Файл config.json создан. Заполните его перед запуском бота!")

with open(config_file_path, "r") as config_file:
    config = json.load(config_file)

# Присвоение значений из файла конфигурации
FINE_CHANNEL_ID = config["FINE_CHANNEL_ID"]
NOTIFY_CHANNEL_ID = config["NOTIFY_CHANNEL_ID"]
LOG_CHANNEL_ID = config["LOG_CHANNEL_ID"]
ROLE_ID = config["ROLE_ID"]
CONTENT_MAKER_ROLE_ID = config["CONTENT_MAKER_ROLE_ID"]
FINANCIER_ROLE_ID = config["FINANCIER_ROLE_ID"]

# Настройка намерений (intents) для получения необходимых событий от Discord
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

# Создание экземпляра бота с префиксом "!" и заданными намерениями
bot = commands.Bot(command_prefix="!", intents=intents)

DB_NAME = "bot.db"  # Имя файла базы данных

# Функция для загрузки сообщений из файла messages.json
def load_messages():
    with open("messages.json", "r", encoding="utf-8") as f:
        return json.load(f)

messages = load_messages()

# Инициализация базы данных (используем параметризованные запросы для защиты от SQL-инъекций)
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS balances (
                member_id TEXT PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                nickname TEXT DEFAULT ''
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                member_id TEXT,
                amount INTEGER,
                note TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS parties (
                party_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id TEXT,
                info TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS party_members (
                party_id INTEGER,
                member_id TEXT,
                PRIMARY KEY (party_id, member_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id TEXT,
                check_in_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                amount INTEGER,
                reason TEXT,
                is_closed INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

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
# Класс для управления балансом пользователей
# ==============================
class BalanceManager:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def get_balance(self, member_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT balance FROM balances WHERE member_id = ?", (str(member_id),))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 0

    def deposit(self, member_id, amount, nickname="", by=None, note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        conn = self.get_connection()
        c = conn.cursor()
        current = self.get_balance(member_id)
        new_balance = current + amount
        c.execute("INSERT OR REPLACE INTO balances (member_id, balance, nickname) VALUES (?, ?, ?)",
                  (str(member_id), new_balance, nickname))
        c.execute("INSERT INTO transactions (type, member_id, amount, note) VALUES (?, ?, ?, ?)",
                  ("DEPOSIT", str(member_id), amount, f"by {by}: {note}"))
        conn.commit()
        conn.close()

    def withdraw(self, member_id, amount, nickname="", by=None, note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        current = self.get_balance(member_id)
        if current < amount:
            raise ValueError("Недостаточно средств")
        new_balance = current - amount
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE balances SET balance = ?, nickname = ? WHERE member_id = ?", (new_balance, nickname, str(member_id)))
        c.execute("INSERT INTO transactions (type, member_id, amount, note) VALUES (?, ?, ?, ?)",
                  ("WITHDRAW", str(member_id), -amount, f"by {by}: {note}"))
        conn.commit()
        conn.close()

    def transfer(self, from_member, to_member, amount, from_nickname="", to_nickname="", note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        if self.get_balance(from_member) < amount:
            raise ValueError("Недостаточно средств для перевода")
        self.withdraw(from_member, amount, nickname=from_nickname, by=from_member, note=f"Transfer to {to_member}. {note}")
        self.deposit(to_member, amount, nickname=to_nickname, by=from_member, note=f"Transfer from {from_member}. {note}")

    def top_balances(self, top_n=40):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT member_id, balance, nickname FROM balances ORDER BY balance DESC LIMIT ?", (top_n,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_history(self, member_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT type, amount, note, timestamp FROM transactions WHERE member_id = ? ORDER BY timestamp DESC LIMIT 10", (str(member_id),))
        rows = c.fetchall()
        conn.close()
        return rows

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
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO parties (creator_id, info) VALUES (?, ?)", (str(creator_id), info))
    party_id = c.lastrowid
    c.execute("INSERT INTO party_members (party_id, member_id) VALUES (?, ?)", (party_id, str(creator_id)))
    conn.commit()
    conn.close()
    return party_id

def delete_party(party_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM parties WHERE party_id = ?", (party_id,))
    c.execute("DELETE FROM party_members WHERE party_id = ?", (party_id,))
    conn.commit()
    conn.close()
    return True

def add_party_member(party_id, member_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO party_members (party_id, member_id) VALUES (?, ?)", (party_id, str(member_id)))
    conn.commit()
    conn.close()

def remove_party_member(party_id, member_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM party_members WHERE party_id = ? AND member_id = ?", (party_id, str(member_id)))
    conn.commit()
    conn.close()

def get_active_parties():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT party_id, creator_id, info, created_at FROM parties")
    rows = c.fetchall()
    conn.close()
    return rows

@bot.group(invoke_without_command=True)
async def party(ctx):
    parties = get_active_parties()
    if parties:
        msg = messages.get("party_active_header", "Активные сборы:\n")
        for p_id, creator_id, info, _ in parties:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM party_members WHERE party_id = ?", (p_id,))
            count = c.fetchone()[0]
            conn.close()
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
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT creator_id FROM parties WHERE party_id = ?", (party_id,))
    row = c.fetchone()
    conn.close()
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
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT party_id FROM parties WHERE party_id = ?", (party_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await ctx.send(messages["party_not_found"])
        return
    add_party_member(party_id, ctx.author.id)
    await ctx.send(messages["party_join_success"].format(user_mention=ctx.author.mention, party_id=party_id))

@party.command(name="leave")
async def party_leave(ctx, party_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT party_id FROM parties WHERE party_id = ?", (party_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await ctx.send(messages["party_not_found"])
        return
    remove_party_member(party_id, ctx.author.id)
    await ctx.send(messages["party_leave_success"].format(user_mention=ctx.author.mention, party_id=party_id))

@party.command(name="notify")
async def party_notify(ctx, party_id: int, *, message_text: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT member_id FROM party_members WHERE party_id = ?", (party_id,))
    members = c.fetchall()
    conn.close()
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

    if amount <= 0:
        await ctx.send(messages["fine_error"])
        return

    try:
        balance_manager.withdraw(user.id, amount, nickname=user.display_name, by=ctx.author.id, note=f"Fine: {reason}")
    except Exception as e:
        await ctx.send(messages["fine_invalid_amount"].format(error_message=str(e)))
        return

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO fines (user_id, amount, reason) VALUES (?, ?, ?)", (str(user.id), amount, reason))
    fine_id = c.lastrowid
    conn.commit()
    conn.close()

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
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT is_closed FROM fines WHERE id = ?", (fine_id,))
    result = c.fetchone()
    if result is None:
        await ctx.send(f"❗ Штраф с номером `{fine_id}` не найден.")
        conn.close()
        return
    if result[0] == 1:
        await ctx.send(f"❗ Штраф с номером `{fine_id}` уже закрыт.")
        conn.close()
        return
    c.execute("UPDATE fines SET is_closed = 1 WHERE id = ?", (fine_id,))
    conn.commit()
    conn.close()
    await ctx.send(f"✅ Штраф с номером `{fine_id}` успешно закрыт!")

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

# Запуск бота с использованием токена из переменных окружения
bot.run(TOKEN)

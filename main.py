import discord
from discord.ext import commands
import json
import logging
import os
import sqlite3
from datetime import datetime

# Настройка логирования
logging.basicConfig(filename='bot.txt', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Проверка наличия файла конфигурации
config_file_path = "config.json"
default_config = {
    "TOKEN": "YOUR_BOT_TOKEN",
    "FINE_CHANNEL_ID": 0,
    "NOTIFY_CHANNEL_ID": 0,
    "LOG_CHANNEL_ID": 0,
    "ROLE_ID": 0,
    "CONTENT_MAKER_ROLE_ID": 0,
    "FINANCIER_ROLE_ID": 0
}

if not os.path.exists(config_file_path):
    with open(config_file_path, "w") as config_file:
        json.dump(default_config, config_file, indent=4)
        print("Файл config.json создан. Заполните его перед запуском бота!")

with open(config_file_path, "r") as config_file:
    config = json.load(config_file)

TOKEN = config["TOKEN"]
FINE_CHANNEL_ID = config["FINE_CHANNEL_ID"]
NOTIFY_CHANNEL_ID = config["NOTIFY_CHANNEL_ID"]
LOG_CHANNEL_ID = config["LOG_CHANNEL_ID"]
ROLE_ID = config["ROLE_ID"]
CONTENT_MAKER_ROLE_ID = config["CONTENT_MAKER_ROLE_ID"]
FINANCIER_ROLE_ID = config["FINANCIER_ROLE_ID"]

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_NAME = "bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Таблица для балансов пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS balances (
                member_id TEXT PRIMARY KEY,
                balance INTEGER DEFAULT 0)''')
    # Таблица для истории транзакций
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                member_id TEXT,
                amount INTEGER,
                note TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # Таблица для сборов (party)
    c.execute('''CREATE TABLE IF NOT EXISTS parties (
                party_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id TEXT,
                info TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # Таблица участников сборов
    c.execute('''CREATE TABLE IF NOT EXISTS party_members (
                party_id INTEGER,
                member_id TEXT,
                PRIMARY KEY (party_id, member_id))''')
    conn.commit()
    conn.close()

init_db()

# Вспомогательная функция для проверки роли
async def has_role(member, role_id):
    role = discord.utils.get(member.guild.roles, id=role_id)
    return role in member.roles if role else False

@bot.event
async def on_ready():
    logging.info(f"Бот {bot.user} запущен!")
    print(f"Бот {bot.user} запущен!")
    print("Зарегистрированные команды:", [cmd.name for cmd in bot.commands])


# ==============================
# Система управления балансом с SQLite3
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

    def deposit(self, member_id, amount, by=None, note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        conn = self.get_connection()
        c = conn.cursor()
        current = self.get_balance(member_id)
        new_balance = current + amount
        c.execute("INSERT OR REPLACE INTO balances (member_id, balance) VALUES (?, ?)", (str(member_id), new_balance))
        c.execute("INSERT INTO transactions (type, member_id, amount, note) VALUES (?, ?, ?, ?)", 
                  ("DEPOSIT", str(member_id), amount, f"by {by}: {note}"))
        conn.commit()
        conn.close()

    def withdraw(self, member_id, amount, by=None, note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        current = self.get_balance(member_id)
        if current < amount:
            raise ValueError("Недостаточно средств")
        new_balance = current - amount
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE balances SET balance = ? WHERE member_id = ?", (new_balance, str(member_id)))
        c.execute("INSERT INTO transactions (type, member_id, amount, note) VALUES (?, ?, ?, ?)", 
                  ("WITHDRAW", str(member_id), -amount, f"by {by}: {note}"))
        conn.commit()
        conn.close()

    def transfer(self, from_member, to_member, amount, note=""):
        if amount < 0:
            raise ValueError("Сумма должна быть положительной")
        if self.get_balance(from_member) < amount:
            raise ValueError("Недостаточно средств для перевода")
        self.withdraw(from_member, amount, by=from_member, note=f"Transfer to {to_member}. {note}")
        self.deposit(to_member, amount, by=from_member, note=f"Transfer from {from_member}. {note}")

    def top_balances(self, top_n=40):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT member_id, balance FROM balances ORDER BY balance DESC LIMIT ?", (top_n,))
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

# Групповые команды для баланса
@bot.group(invoke_without_command=True)
async def balance(ctx):
    bal = balance_manager.get_balance(ctx.author.id)
    await ctx.send(f"{ctx.author.mention}, ваш баланс: {bal} голды.")

@balance.command(name="deposit")
async def balance_deposit(ctx, member: discord.Member, amount: int):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send("У вас нет прав для пополнения баланса.")
        return
    try:
        balance_manager.deposit(member.id, amount, by=ctx.author.id, note="Deposit command")
        await ctx.send(f"Баланс {member.mention} пополнен на {amount} голды.")
    except Exception as e:
        await ctx.send(f"Ошибка: {e}")

@balance.command(name="withdraw")
async def balance_withdraw(ctx, member: discord.Member, amount: int):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send("У вас нет прав для снятия средств.")
        return
    try:
        balance_manager.withdraw(member.id, amount, by=ctx.author.id, note="Withdraw command")
        await ctx.send(f"С баланса {member.mention} снято {amount} голды.")
    except Exception as e:
        await ctx.send(f"Ошибка: {e}")

@balance.command(name="transfer")
async def balance_transfer(ctx, member: discord.Member, amount: int):
    try:
        balance_manager.transfer(ctx.author.id, member.id, amount, note="Transfer command")
        await ctx.send(f"{ctx.author.mention} перевёл {amount} голды {member.mention}.")
    except Exception as e:
        await ctx.send(f"Ошибка: {e}")

@balance.command(name="top")
async def balance_top(ctx):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send("У вас нет прав для просмотра топа баланса.")
        return
    top_list = balance_manager.top_balances()
    msg = "Топ участников по балансу:\n"
    for member_id, bal in top_list:
        member = ctx.guild.get_member(int(member_id))
        name = member.display_name if member else str(member_id)
        msg += f"{name}: {bal} голды\n"
    await ctx.send(msg)

@balance.command(name="history")
async def balance_history(ctx, member: discord.Member = None):
    
    target_id = member.id if member else ctx.author.id
    history = balance_manager.get_history(target_id)
    if not history:
        await ctx.send("История транзакций пуста.")
    else:
        history_msg = "\n".join([f"{t} {amt} ({note}) - {ts}" for t, amt, note, ts in history])
        await ctx.send(f"История транзакций для <@{target_id}>:\n{history_msg}")

# ==============================
# Система управления сборами (Party) с SQLite3
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

# Команды для управления сборами (party)
@bot.group(invoke_without_command=True)
async def party(ctx):
    """Базовая команда для работы со сборами."""
    parties = get_active_parties()
    if parties:
        msg = "Активные сборы:\n"
        for p_id, creator_id, info, created_at in parties:
            # Подсчитаем участников сбора
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM party_members WHERE party_id = ?", (p_id,))
            count = c.fetchone()[0]
            conn.close()
            msg += f"ID: {p_id} | Инфо: {info} | Участников: {count}\n"
        await ctx.send(msg)
    else:
        await ctx.send("Нет активных сборов.")

@party.command(name="create")
async def party_create(ctx, *, info: str):
    if not await has_role(ctx.author, CONTENT_MAKER_ROLE_ID):
        await ctx.send("У вас нет прав для создания сбора.")
        return
    party_id = create_party(ctx.author.id, info)
    await ctx.send(f"Создан новый сбор с ID {party_id}:\nИнфо: {info}")

@party.command(name="delete")
async def party_delete(ctx, party_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT creator_id FROM parties WHERE party_id = ?", (party_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await ctx.send("Сбор не найден.")
        return
    creator_id = int(row[0])
    if ctx.author.id != creator_id and not await has_role(ctx.author, CONTENT_MAKER_ROLE_ID):
        await ctx.send("У вас нет прав для удаления этого сбора.")
        return
    if delete_party(party_id):
        await ctx.send(f"Сбор с ID {party_id} удалён.")
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
        await ctx.send("Сбор не найден.")
        return
    add_party_member(party_id, ctx.author.id)
    await ctx.send(f"{ctx.author.mention} присоединился к сбору ID {party_id}.")

@party.command(name="leave")
async def party_leave(ctx, party_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT party_id FROM parties WHERE party_id = ?", (party_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await ctx.send("Сбор не найден.")
        return
    remove_party_member(party_id, ctx.author.id)
    await ctx.send(f"{ctx.author.mention} покинул сбор ID {party_id}.")

@party.command(name="notify")
async def party_notify(ctx, party_id: int, *, message: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT member_id FROM party_members WHERE party_id = ?", (party_id,))
    members = c.fetchall()
    conn.close()
    if not members:
        await ctx.send("Сбор не найден или в сборе нет участников.")
        return
    for (member_id,) in members:
        if int(member_id) == ctx.author.id:
            continue
        member = ctx.guild.get_member(int(member_id))
        if member:
            try:
                await member.send(f"Уведомление по сбору ID {party_id}: {message}")
            except discord.Forbidden:
                logging.warning(f"Не удалось отправить уведомление {member.name}.")
    await ctx.send("Уведомления отправлены участникам сбора.")

@bot.command(name="fine")
async def issue_fine(ctx, user: discord.Member, amount: int, *, reason: str = "Без причины"):
    # Проверка роли финансиста
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send("❌ У вас нет прав для выдачи штрафов.")
        return

    if amount <= 0:
        await ctx.send("❌ Размер штрафа должен быть положительным числом.")
        return

    # Списание средств с баланса
    try:
        balance_manager.withdraw(user.id, amount, by=ctx.author.id, note=f"Fine: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Ошибка при снятии средств: {e}")
        return

    # Формируем embed для уведомлений
    embed = discord.Embed(
        title="🚫 **Новый штраф!** 🚫",
        color=discord.Color.red()
    )
    embed.add_field(name="**Нарушитель:**", value=user.mention, inline=False)
    embed.add_field(name="**Размер штрафа:**", value=f"{amount} голды", inline=False)
    embed.add_field(name="**Причина:**", value=reason, inline=False)
    embed.add_field(name="**Выдал штраф:**", value=ctx.author.mention, inline=False)

    # Отправляем embed в канал штрафов
    fine_channel = ctx.guild.get_channel(FINE_CHANNEL_ID)
    if fine_channel:
        await fine_channel.send(embed=embed)

    # Пытаемся отправить embed в ЛС нарушителю
    try:
        await user.send(embed=embed)
        status_msg = f"📩 Штраф также отправлен в личные сообщения {user.mention}!"
    except discord.Forbidden:
        status_msg = f"⚠️ Не удалось отправить сообщение в ЛС {user.mention}. Возможно, у него закрыты ЛС."

    # Логируем действия в лог-канал
    log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"✅ Штраф для {user.mention} отправлен в {fine_channel.mention}!")
        await log_channel.send(status_msg)

    # Логируем в файл
    logging.info(f"Штраф выдан: {user} | Сумма: {amount} | Причина: {reason} | Выдал: {ctx.author}")



# ==============================
# Дополнительные команды посещаемости (заглушки)
# ==============================
@bot.group(invoke_without_command=True)
async def attendance(ctx):
    await ctx.send("Используйте команды: attendance top, attendance my, attendance member")

@attendance.command(name="top")
async def attendance_top(ctx):
    await ctx.send("Топ участников по посещаемости за 7 дней (функционал в разработке)")

@attendance.command(name="my")
async def attendance_my(ctx):
    await ctx.send(f"{ctx.author.mention}, ваша посещаемость за 7 дней: 80% (функционал в разработке)")

@attendance.command(name="member")
async def attendance_member(ctx, member: discord.Member):
    await ctx.send(f"Посещаемость {member.mention} за 7 дней: 75% (функционал в разработке)")

bot.run(TOKEN)

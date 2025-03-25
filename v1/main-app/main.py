import discord  # Импорт библиотеки для работы с Discord API
from discord.ext import commands  # Импорт расширения для команд бота
import json  # Импорт модуля для работы с JSON
import logging  # Импорт модуля логирования
import os  # Импорт модуля для работы с операционной системой
import sqlite3  # Импорт модуля для работы с SQLite базой данных
from datetime import datetime, timedelta  # Импорт классов для работы с датой и временем
from dotenv import load_dotenv  # Импорт функции для загрузки переменных окружения из файла .env
import asyncio
from discord.ui import View, Button, Modal, TextInput
import secrets
import aiohttp
from aiogram import Bot as TelegramBot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command

# Загрузка переменных окружения из файла .env (убедитесь, что файл .env добавлен в .gitignore)
load_dotenv()

# Получение токенов из переменных окружения
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN не найден в переменных окружения")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден в переменных окружения")

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
DM_LOG_CHANNEL_ID = config["DM_LOG_CHANNEL_ID"]
LOG_ALL_CHANNEL_ID = config["LOG_ALL_CHANNEL_ID"]  # ID канала, куда отправляются все логи

# Инициализация Telegram бота
telegram_bot = TelegramBot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

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

# Регистрируем хендлеры Telegram
@dp.message(Command('start'))
async def handle_start(message: types.Message):
    """Обработчик команды /start"""
    try:
        await message.answer(
            "👋 Привет! Я бот Hell Branch.\n\n"
            "Чтобы получать уведомления здесь, привяжите свой Discord аккаунт "
            "с помощью команды `/link КОД`, где КОД - это код, который вы получили в Discord."
            "Например: `/link abc123`\n\n"

            "Переходите в наш телеграм канал: https://t.me/+ActeXmEZK9U4OWUy\n\n"
            "После привязки вы будете получать уведомления в обоих мессенджерах!",  
            
        )
        logging.info(f"Telegram: Обработана команда /start от пользователя {message.from_user.id}")
    except Exception as e:
        logging.error(f"Ошибка в handle_start: {e}")

@dp.message(Command('link'))
async def handle_link(message: types.Message):
    """Обработчик команды /link для привязки аккаунтов"""
    try:
        # Получаем код из сообщения
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Используйте: `/link КОД`\n"
                "Например: `/link abc123`"
            )
            return
            
        code = parts[1].lower()
        
        # Проверяем код и создаём связь
        if await verify_link_code(code, message.from_user.id, message.from_user.username):
            await message.answer(
                "✅ Аккаунты успешно связаны!\n"
                "Теперь вы будете получать уведомления в Telegram."
            )
            logging.info(f"Telegram: Успешная привязка аккаунта для пользователя {message.from_user.id}")
        else:
            await message.answer(
                "❌ Неверный или устаревший код.\n"
                "Запросите новый код в Discord с помощью команды `!link_telegram`"
            )
            
    except Exception as e:
        logging.error(f"Ошибка в handle_link: {e}")
        await message.answer("❌ Произошла ошибка при обработке команды.")

@dp.message(Command('help'))
async def handle_help(message: types.Message):
    """Обработчик команды /help"""
    try:
        await message.answer(
            "🔍 Доступные команды:\n\n"
            "/start - Начать работу с ботом\n"
            "/link КОД - Привязать Discord аккаунт\n"
            "/help - Показать это сообщение"
        )
    except Exception as e:
        logging.error(f"Ошибка в handle_help: {e}")

# Запускаем Telegram бота
async def start_telegram_bot():
    """Запускает Telegram бота"""
    try:
        # Удаляем старые вебхуки
        await telegram_bot.delete_webhook(drop_pending_updates=True)
        # Запускаем поллинг
        await dp.start_polling(telegram_bot)
    except Exception as e:
        logging.error(f"Ошибка запуска Telegram бота: {e}")

# --- Модальные окна для управления балансом ---

class DepositModal(Modal, title="Пополнить баланс"):
    member = TextInput(label="Участник (ID или упоминание)")
    amount = TextInput(label="Сумма пополнения")

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        try:
            member_obj = interaction.guild.get_member(int(self.member.value))
            amount_value = int(self.amount.value)
            await bot.get_command("balance deposit").callback(ctx, member_obj, amount_value)
            await interaction.response.send_message(f"✅ Баланс {member_obj.display_name} пополнен на {amount_value} серебра.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Ошибка: неверные данные.", ephemeral=True)


class WithdrawModal(Modal, title="Снять баланс"):
    member = TextInput(label="Участник (ID или упоминание)")
    amount = TextInput(label="Сумма снятия")

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        try:
            member_obj = interaction.guild.get_member(int(self.member.value))
            amount_value = int(self.amount.value)
            await bot.get_command("balance withdraw").callback(ctx, member_obj, amount_value)
            await interaction.response.send_message(f"💳 Снято {amount_value} серебра у {member_obj.display_name}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Ошибка: неверные данные.", ephemeral=True)


class TransferModal(Modal, title="Перевод средств"):
    recipient = TextInput(label="Получатель (ID или упоминание)")
    amount = TextInput(label="Сумма перевода")

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        try:
            recipient_obj = interaction.guild.get_member(int(self.recipient.value))
            amount_value = int(self.amount.value)
            await bot.get_command("balance transfer").callback(ctx, recipient_obj, amount_value)
            await interaction.response.send_message(f"🔄 {amount_value} серебра переведено {recipient_obj.display_name}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Ошибка: неверные данные.", ephemeral=True)


import re

class HistoryModal(Modal, title="История баланса"):
    member = TextInput(label="ID или @упоминание (необязательно)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)

        member_text = self.member.value.strip()
        member_obj = None

        if not member_text:  # Если поле пустое, берем пользователя, который нажал кнопку
            member_obj = interaction.user
        else:
            # Проверяем, введён ли ID
            if member_text.isdigit():
                member_obj = interaction.guild.get_member(int(member_text))
            # Проверяем, введено ли @упоминание
            else:
                mention_match = re.match(r"<@!?(\d+)>", member_text)
                if mention_match:
                    member_id = int(mention_match.group(1))
                    member_obj = interaction.guild.get_member(member_id)

        if not member_obj:
            await interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)
            return

        await bot.get_command("balance history").callback(ctx, member_obj)
        await interaction.response.send_message("📜 История транзакций отправлена.", ephemeral=True)

# --- Модальные окна для штрафов ---

class FineModal(Modal, title="Выдать штраф"):
    member = TextInput(label="Участник (ID или упоминание)")
    amount = TextInput(label="Сумма штрафа")
    reason = TextInput(label="Причина")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Проверяем, введён ли ID
            member_text = self.member.value.strip()
            member_obj = None
            
            if member_text.isdigit():
                member_obj = interaction.guild.get_member(int(member_text))
            else:
                # Проверяем, введено ли @упоминание
                mention_match = re.match(r"<@!?(\d+)>", member_text)
                if mention_match:
                    member_id = int(mention_match.group(1))
                    member_obj = interaction.guild.get_member(member_id)

            if not member_obj:
                await interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)
                return

            amount_value = int(self.amount.value)
            
            # Проверяем роль финансиста
            if not await has_role(interaction.user, FINANCIER_ROLE_ID):
                await interaction.response.send_message("❌ У вас нет прав для выдачи штрафа.", ephemeral=True)
                return

            # Логируем штраф в базу
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("INSERT INTO fines (user_id, amount, reason) VALUES (?, ?, ?)", 
                         (str(member_obj.id), amount_value, self.reason.value))
                fine_id = c.lastrowid
                conn.commit()

            # Синхронизируем баланс
            sync_fines_with_balance(member_obj.id)

            # Создаём embed-уведомление
            embed = discord.Embed(
                title="🚫 **Новый штраф!** 🚫",
                color=discord.Color.red()
            )
            embed.add_field(name="**Нарушитель:**", value=member_obj.mention, inline=False)
            embed.add_field(name="**Размер штрафа:**", value=f"{amount_value} серебра", inline=False)
            embed.add_field(name="**Причина:**", value=self.reason.value, inline=False)
            embed.add_field(name="**Выдал штраф:**", value=interaction.user.mention, inline=False)
            embed.add_field(name="**Номер штрафа:**", value=fine_id, inline=False)

            # Отправляем в канал штрафов
            fine_channel = interaction.guild.get_channel(FINE_CHANNEL_ID)
            if fine_channel:
                await fine_channel.send(embed=embed)

            # Добавляем роль штрафника
            fine_role = discord.utils.get(interaction.guild.roles, id=FINE_ROLE_ID)
            if fine_role and fine_role not in member_obj.roles:
                await member_obj.add_roles(fine_role)

            # Пробуем отправить в ЛС
            try:
                await member_obj.send(embed=embed)
                status_msg = messages["fine_sent_to_dm"].format(user_mention=member_obj.mention)
            except discord.Forbidden:
                status_msg = messages["fine_failed_to_dm"].format(user_mention=member_obj.mention)

            # Логируем
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"✅ Штраф для {member_obj.mention} отправлен в {fine_channel.mention}!")
                await log_channel.send(status_msg)

            await interaction.response.send_message("✅ Штраф успешно выдан.", ephemeral=True)
            logging.info(f"Штраф выдан: {member_obj} | Сумма: {amount_value} | Причина: {self.reason.value} | Выдал: {interaction.user}")

        except ValueError as e:
            await interaction.response.send_message(f"❌ Ошибка: неверное значение. {str(e)}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)


class CloseFineModal(Modal, title="Закрыть штраф"):
    fine_id = TextInput(label="ID штрафа")

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        try:
            fine_id_int = int(self.fine_id.value)
            await bot.get_command("close_fine").callback(ctx, fine_id_int)
            await interaction.response.send_message("✅ Штраф закрыт.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Ошибка: неверные данные.", ephemeral=True)


# --- Модальные окна для управления канал-ролью ---

class AddChannelRoleModal(Modal, title="Добавить канал-роль"):
    channel_id = TextInput(label="ID канала")
    role_id = TextInput(label="ID роли")

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        try:
            await bot.get_command("add_channel_role").callback(ctx, int(self.role_id.value), int(self.channel_id.value))
            await interaction.response.send_message("✅ Канал-роль добавлена.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Ошибка: неверные данные.", ephemeral=True)


class RemoveChannelRoleModal(Modal, title="Удалить канал-роль"):
    channel_id = TextInput(label="ID канала")

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        try:
            await bot.get_command("remove_channel_role").callback(ctx, int(self.channel_id.value))
            await interaction.response.send_message("✅ Канал-роль удалена.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Ошибка: неверные данные.", ephemeral=True)


class UpdateMessageModal(Modal, title="Обновить сообщение"):
    key = TextInput(label="Ключ сообщения")
    new_message = TextInput(label="Новое сообщение", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        await bot.get_command("update_message").callback(ctx, self.key.value, self.new_message.value)
        await interaction.response.send_message("✅ Сообщение обновлено.", ephemeral=True)


class SendMessageModal(Modal, title="Отправить ЛС"):
    member_id = TextInput(label="ID или @упоминание")
    text = TextInput(label="Сообщение", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = await bot.get_context(interaction.message)
        member_text = self.member_id.value.strip()
        member_obj = None

        # Проверяем, введён ли ID
        if member_text.isdigit():
            member_obj = interaction.guild.get_member(int(member_text))
        # Проверяем, введено ли @упоминание
        else:
            mention_match = re.match(r"<@!?(\d+)>", member_text)
            if mention_match:
                member_id = int(mention_match.group(1))
                member_obj = interaction.guild.get_member(member_id)

        if not member_obj:
            await interaction.response.send_message("❌ Ошибка: Пользователь не найден.", ephemeral=True)
            return

        # Пробуем отправить сообщение в ЛС
        try:
            await member_obj.send(f"📩 **Сообщение от {interaction.user.display_name}:**\n{self.text.value}")
            await interaction.response.send_message("✅ Сообщение успешно отправлено.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"⚠️ {member_obj.mention} закрыл ЛС, отправка невозможна.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при отправке: {str(e)}", ephemeral=True)

# --- Панель управления (UI-кнопки) ---

class BalanceView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 Мой баланс", style=discord.ButtonStyle.primary)
    async def my_balance_button(self, interaction: discord.Interaction, button: Button):
        user = interaction.user
        current_balance = balance_manager.get_balance(user.id)
        response = f"💰 {user.mention}, ваш баланс: {current_balance} серебра."
        await interaction.response.send_message(response, ephemeral=True)

    @discord.ui.button(label="🏆 Топ баланса", style=discord.ButtonStyle.secondary)
    async def balance_top_button(self, interaction: discord.Interaction, button: Button):
        top_list = balance_manager.top_balances()
        msg = "🏆 Топ участников по балансу:\n\n"
        for i, (member_id, bal, nickname) in enumerate(top_list[:40], 1):
            name = nickname if nickname else str(member_id)
            msg += f"{i}. {name}: {bal} серебра\n"
        await interaction.response.send_message(msg, ephemeral=True)

class TelegramView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔗 Привязать Telegram", style=discord.ButtonStyle.success)
    async def link_telegram_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        ctx = await bot.get_context(interaction.message)
        ctx.author = interaction.user
        await bot.get_command("link_telegram").callback(ctx)
        await interaction.followup.send("✅ Инструкции отправлены вам в личные сообщения!", ephemeral=True)

@bot.command(name="telegram_panel")
async def create_telegram_panel(ctx):
    """Создает панель управления Telegram с кнопками"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ У вас нет прав для создания панели управления.")
        return

    embed = discord.Embed(
        title="🔗 Панель управления Telegram",
        description="Нажмите на кнопку ниже, чтобы получить инструкции по привязке Telegram аккаунта.\n\n"
                   "После привязки вы будете получать уведомления в обоих мессенджерах!\n\n"
                   "VK - https://vk.com/hell_branch\n"
                   "YouTube - https://youtube.com/@6beastofnonation9?si=ezsIKf5WWHzyBB13\n"
                   "Twitch - https://www.twitch.tv/hell_branch\n"
                   "Instagram - https://www.instagram.com/_hell_branch_?igsh=cWQzZXo0ODBhYWRs",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed, view=TelegramView())

@bot.command(name="balance_panel")
async def create_balance_panel(ctx):
    """Создает панель управления балансом с кнопками"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ У вас нет прав для создания панели управления.")
        return

    embed = discord.Embed(
        title="💰 Панель управления балансом",
        description="Нажмите на кнопки ниже, чтобы:\n\n"
                   "💰 **Мой баланс** - посмотреть свой текущий баланс\n"
                   "🏆 **Топ баланса** - посмотреть топ участников по балансу",
        color=discord.Color.gold()
    )
    
    await ctx.send(embed=embed, view=BalanceView())
    await ctx.message.delete()



class CommandControlPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def log_button_action(self, interaction, message):
        """Функция для логирования действий кнопок"""
        log_channel = bot.get_channel(LOG_ALL_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"📌 **Кнопка нажата:** {message}")

    @discord.ui.button(label="💰 Баланс", style=discord.ButtonStyle.primary)
    async def balance_button(self, interaction: discord.Interaction, button: Button):
        user = interaction.user
        current_balance = balance_manager.get_balance(user.id)
        response = f"💰 {user.mention}, ваш баланс: {current_balance} серебра."
        await interaction.response.send_message(response, ephemeral=True)
        await self.log_button_action(interaction, response)

    @discord.ui.button(label="💸 Пополнить баланс", style=discord.ButtonStyle.success)
    async def deposit_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DepositModal())
        await self.log_button_action(interaction, "Открыто модальное окно пополнения баланса.")

    @discord.ui.button(label="💳 Снять баланс", style=discord.ButtonStyle.danger)
    async def withdraw_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WithdrawModal())
        await self.log_button_action(interaction, "Открыто модальное окно снятия баланса.")

    @discord.ui.button(label="🔄 Перевести", style=discord.ButtonStyle.primary)
    async def transfer_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TransferModal())
        await self.log_button_action(interaction, "Открыто модальное окно перевода средств.")

    @discord.ui.button(label="🕒 История баланса", style=discord.ButtonStyle.secondary)
    async def history_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(HistoryModal())
        await self.log_button_action(interaction, "Открыто модальное окно истории баланса.")

    @discord.ui.button(label="⚖️ Штраф", style=discord.ButtonStyle.danger)
    async def fine_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FineModal())
        await self.log_button_action(interaction, "Открыто модальное окно выдачи штрафа.")

    @discord.ui.button(label="✅ Закрыть штраф", style=discord.ButtonStyle.success)
    async def close_fine_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CloseFineModal())
        await self.log_button_action(interaction, "Открыто модальное окно закрытия штрафа.")
    @discord.ui.button(label="🗑️ Очистить канал", style=discord.ButtonStyle.danger)
    async def clear_channel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        ctx = await bot.get_context(interaction.message)
        channel = ctx.channel
        try:
            pinned_messages = await channel.pins()
            pinned_ids = [msg.id for msg in pinned_messages]
            deleted = await channel.purge(check=lambda m: m.id not in pinned_ids)
            await interaction.followup.send(f"🗑️ Удалено {len(deleted)} сообщений (кроме закреплённых).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка при очистке канала: {str(e)}", ephemeral=True)


# --- Команда для вызова панели управления ---
@bot.command()
@commands.has_permissions(administrator=True)
async def панель(ctx):
    embed = discord.Embed(
        title="🎛️ Панель управления ботом",
        description="Выбери нужную команду с помощью кнопок.",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed, view=CommandControlPanel())


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
        # Таблица для хранения связей Discord-Telegram
        c.execute("""
            CREATE TABLE IF NOT EXISTS telegram_links (
                discord_id TEXT PRIMARY KEY,
                telegram_id TEXT NOT NULL,
                telegram_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица для временных кодов привязки
        c.execute("""
            CREATE TABLE IF NOT EXISTS telegram_link_codes (
                code TEXT PRIMARY KEY,
                discord_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

async def log_bot_response(ctx, message):
    """Отправляет сообщение в лог-канал"""
    log_channel = bot.get_channel(LOG_ALL_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"📝 **Ответ бота:** {message}")


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
@bot.event
async def on_message(message):
    # Игнорируем сообщения от ботов
    if message.author.bot:
        return

    # ✅ 1. ЛС сообщения — отправляем в канал логов
    if isinstance(message.channel, discord.DMChannel):
        guild = bot.guilds[0]  # или выбери правильную гильдию
        log_channel = guild.get_channel(DM_LOG_CHANNEL_ID)

        if log_channel:
            embed = discord.Embed(
                title="📩 Новое ЛС боту",
                description=message.content or "*Нет текста*",
                color=discord.Color.purple(),
                timestamp=message.created_at
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url if message.author.avatar else None)

            if message.attachments:
                attachments_list = "\n".join([att.url for att in message.attachments])
                embed.add_field(name="Вложения", value=attachments_list, inline=False)

            await log_channel.send(embed=embed)

    # ✅ 2. Обычная логика пересылки сообщений с каналов в ЛС, которую ты уже сделал (из role_channel_map)
    cfg = load_config_file()
    role_channel_map = cfg.get("role_channel_map", {})
    sent_members = set()

    for role_id_str, channel_ids in role_channel_map.items():
        if str(message.channel.id) in channel_ids:
            role_obj = message.guild.get_role(int(role_id_str))
            if not role_obj:
                continue
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
                        await asyncio.sleep(1)
                    except discord.Forbidden:
                        logging.warning(f"Не удалось отправить DM пользователю {member.name}")
                    except Exception as e:
                        logging.error(f"Ошибка отправки DM пользователю {member.name}: {e}")

    # ✅ Запускаем обработку команд
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



    def top_balances(self, top_n=100):
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
    try:
        balance_manager.deposit(member.id, amount, nickname=member.display_name, by=ctx.author.id, note="Deposit command")
        response = f"💰 Баланс {member.mention} пополнен на {amount} серебра."
        await ctx.send(response)
        await log_bot_response(ctx, response)
    except Exception as e:
        error_message = f"❌ Ошибка: {str(e)}"
        await ctx.send(error_message)
        await log_bot_response(ctx, error_message)


@balance.command(name="withdraw")
async def balance_withdraw(ctx, member: discord.Member, amount: int):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        response = "❌ У вас нет прав для снятия средств."
        await ctx.send(response)
        await log_bot_response(ctx, response)
        return
    try:
        balance_manager.withdraw(member.id, amount, nickname=member.display_name, by=ctx.author.id, note="Withdraw command")
        response = f"💳 Снято {amount} серебра у {member.mention}."
        await ctx.send(response)
        await log_bot_response(ctx, response)
    except Exception as e:
        error_message = f"❌ Ошибка: {str(e)}"
        await ctx.send(error_message)
        await log_bot_response(ctx, error_message)


@balance.command(name="transfer")
async def balance_transfer(ctx, member: discord.Member, amount: int):
    try:
        balance_manager.transfer(ctx.author.id, member.id, amount, 
                                 from_nickname=ctx.author.display_name, to_nickname=member.display_name,
                                 note="Transfer command")
        response = f"🔄 {amount} серебра переведено {member.mention}."
        await ctx.send(response)
        await log_bot_response(ctx, response)
    except Exception as e:
        error_message = f"❌ Ошибка: {str(e)}"
        await ctx.send(error_message)
        await log_bot_response(ctx, error_message)

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
def sync_fines_with_balance(user_id):
    """Синхронизирует баланс пользователя с его активными штрафами"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Получаем сумму активных штрафов
        c.execute("SELECT COALESCE(SUM(amount), 0) FROM fines WHERE user_id = ? AND is_closed = 0", (str(user_id),))
        total_fines = c.fetchone()[0]
        
        # Обновляем баланс пользователя
        c.execute("INSERT OR REPLACE INTO balances (member_id, balance) VALUES (?, -?)", (str(user_id), total_fines))
        conn.commit()

@bot.command(name="fine")
async def issue_fine(ctx, user: discord.Member, amount: int, *, reason: str = "Без причины"):
    if not await has_role(ctx.author, FINANCIER_ROLE_ID):
        await ctx.send(messages["fine_no_permission"])
        return

    try:
        # Логируем штраф в базу
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO fines (user_id, amount, reason) VALUES (?, ?, ?)", 
                     (str(user.id), amount, reason))
            fine_id = c.lastrowid
            conn.commit()

        # Синхронизируем баланс
        sync_fines_with_balance(user.id)

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

        # Отправляем в канал штрафов
        fine_channel = ctx.guild.get_channel(FINE_CHANNEL_ID)
        if fine_channel:
            await fine_channel.send(embed=embed)

        # Добавляем роль штрафника
        fine_role = discord.utils.get(ctx.guild.roles, id=FINE_ROLE_ID)
        if fine_role and fine_role not in user.roles:
            await user.add_roles(fine_role)

        # Отправляем уведомление пользователю
        await send_notification(user.id, None, embed=embed)

        # Логируем
        log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"✅ Штраф для {user.mention} отправлен в {fine_channel.mention}!")

        await ctx.send("✅ Штраф успешно выдан.", ephemeral=True)
        logging.info(f"Штраф выдан: {user} | Сумма: {amount} | Причина: {reason} | Выдал: {ctx.author}")

    except Exception as e:
        await ctx.send(f"❌ Ошибка при выдаче штрафа: {str(e)}")

@bot.command(name="close_fine")
async def close_fine(ctx, fine_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, is_closed FROM fines WHERE id = ?", (fine_id,))
        result = c.fetchone()
        
        if result is None:
            await ctx.send(f"❗ Штраф с номером `{fine_id}` не найден.")
            return
        
        user_id, is_closed = result
        
        if is_closed == 1:
            await ctx.send(f"❗ Штраф с номером `{fine_id}` уже закрыт.")
            return
        
        c.execute("UPDATE fines SET is_closed = 1 WHERE id = ?", (fine_id,))
        conn.commit()

    # Синхронизируем баланс после закрытия штрафа
    sync_fines_with_balance(user_id)

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
        await ctx.send("⚠️ Использование: `!m @пользователь1 @роль1 ... сообщение`")
        return

    sent_count = 0
    failed_count = 0

    for member in recipients:
        if member.bot:
            continue  # Пропускаем ботов

        try:
            await send_notification(
                member.id,
                f"📩 **Сообщение от {ctx.author.display_name}:**\n{message_text}"
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logging.error(f"Ошибка отправки сообщения {member.name}: {e}")

    response = []
    if sent_count:
        response.append(f"✅ Сообщение отправлено {sent_count} пользователям.")
    if failed_count:
        response.append(f"❌ Не удалось отправить сообщение {failed_count} пользователям.")
    
    await ctx.send("\n".join(response))

    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name="link_telegram")
async def link_telegram_cmd(ctx):
    """Генерирует код для привязки Telegram"""
    try:
        code = await generate_link_code(ctx.author.id)
        
        embed = discord.Embed(
            title="🔗 Привязка Telegram",
            description=(
                "Чтобы получать уведомления в Telegram, выполните следующие шаги:\n\n"
                "1. Добавьте бота @HellBranch_bot\n"
                "2. Отправьте ему команду:\n"
                f"```\n/link {code}\n```\n"
                "⚠️ Код действителен 5 минут"
            ),
            color=discord.Color.blue()
        )            
    except Exception as e:
        logging.error(f"Ошибка в команде link_telegram: {e}")
        await ctx.send("❌ Произошла ошибка при генерации кода.", ephemeral=True)

@bot.command(name="help")
async def help_command(ctx):
    help_message = (
        "**Справка по командам бота:**\n\n"
        "**Панели управления:**\n"
        "`!панель` - Открыть основную панель управления ботом (только администратор).\n"
        "`!balance_panel` - Создать панель управления балансом с кнопками (только администратор).\n\n"
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
        "`!balance history [пользователь]` - История транзакций.\n"
        "`!update_balances` - Массовое обновление балансов (только администратор).\n\n"
        "**Сборы:**\n"
        "`!party` - Показать активные сборы.\n"
        "`!party create [информация]` - Создать сбор (только контент-мейкер).\n"
        "`!party delete [ID сбора]` - Удалить сбор.\n"
        "`!party join [ID сбора]` - Присоединиться к сбору.\n"
        "`!party leave [ID сбора]` - Покинуть сбор.\n"
        "`!party notify [ID сбора] [сообщение]` - Уведомить участников сбора.\n\n"
        "**Штрафы:**\n"
        "`!fine [пользователь] [сумма] [причина]` - Выдать штраф (только финансист).\n"
        "`!close_fine [номер штрафа]` - Закрыть штраф и снять роль штрафника (только финансист).\n\n"
        "**Сообщения:**\n"
        "`!update_message [ключ] [новое сообщение]` - Обновить сообщение (только с определённой ролью).\n"
        "`!m [пользователь1] [пользователь2] ... [сообщение]` - Отправить сообщение в ЛС.\n"
        "`!help` - Показать это сообщение."
    )
    await ctx.send(help_message)

@bot.command(name="get_user_id")
async def get_user_id(ctx, username: str):
    """Временная команда для получения ID пользователя по его нику в Discord"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ У вас нет прав для использования этой команды.")
        return
        
    members = ctx.guild.members
    found = False
    for member in members:
        if username.lower() in member.name.lower() or (member.nick and username.lower() in member.nick.lower()):
            await ctx.send(f"Найден пользователь: {member.name}#{member.discriminator} (ID: {member.id})")
            found = True
    
    if not found:
        await ctx.send(f"❌ Пользователь с ником '{username}' не найден.")

@bot.command(name="update_balances")
@commands.has_permissions(administrator=True)
async def update_balances(ctx, *, data: str):
    """Обновляет балансы пользователей из списка"""
    try:
        # Разбиваем данные по строкам или точкам с запятой
        lines = [line.strip() for line in data.replace(';', '\n').split('\n')]
        updated = 0
        errors = []

        for line in lines:
            try:
                # Пропускаем пустые строки
                if not line.strip():
                    continue
                
                # Парсим строку
                if ':' not in line:
                    errors.append(f"Неверный формат строки (нет ':'): {line}")
                    continue

                # Разделяем на имя и сумму
                name_part, amount_str = line.split(':', 1)
                
                # Очищаем сумму от пробелов и получаем число
                amount = int(amount_str.strip().replace(' ', ''))
                
                # Получаем имя пользователя
                username = name_part.split('|')[0].strip().strip('@')
                
                # Ищем пользователя
                member = None
                for guild_member in ctx.guild.members:
                    if username.lower() in guild_member.name.lower() or (guild_member.nick and username.lower() in guild_member.nick.lower()):
                        member = guild_member
                        break
                    # Проверяем ID пользователя
                    if username.isdigit() and str(guild_member.id) == username:
                        member = guild_member
                        break

                if member:
                    # Устанавливаем новый баланс (сначала обнуляем, потом добавляем)
                    balance_manager.withdraw(member.id, balance_manager.get_balance(member.id), nickname=member.display_name, by=ctx.author.id, note="Balance reset")
                    balance_manager.deposit(member.id, amount, nickname=member.display_name, by=ctx.author.id, note="Balance update")
                    updated += 1
                else:
                    errors.append(f"Пользователь не найден: {username}")

            except ValueError as e:
                errors.append(f"Ошибка в строке '{line}': {str(e)}")
            except Exception as e:
                errors.append(f"Непредвиденная ошибка в строке '{line}': {str(e)}")

        # Отправляем отчет
        report = f"✅ Обновлено балансов: {updated}\n"
        if errors:
            report += "\n❌ Ошибки:\n" + "\n".join(errors)
        
        await ctx.send(report)

    except Exception as e:
        await ctx.send(f"❌ Ошибка при обработке данных: {str(e)}")

# Функции для работы с Telegram связями
async def get_telegram_id(discord_id: str) -> str | None:
    """Получает Telegram ID по Discord ID"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_id FROM telegram_links WHERE discord_id = ?", (str(discord_id),))
        result = c.fetchone()
        return result[0] if result else None

async def link_accounts(discord_id: str, telegram_id: int, telegram_username: str) -> bool:
    """Связывает аккаунты Discord и Telegram"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO telegram_links 
            (discord_id, telegram_id, telegram_username) 
            VALUES (?, ?, ?)
        """, (str(discord_id), str(telegram_id), telegram_username))
        conn.commit()
    return True

async def generate_link_code(discord_id: str) -> str:
    """Генерирует временный код для привязки Telegram"""
    code = secrets.token_hex(3)  # 6 символов
    
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Удаляем старые коды для этого пользователя
        c.execute("DELETE FROM telegram_link_codes WHERE discord_id = ?", (str(discord_id),))
        # Добавляем новый код
        c.execute(
            "INSERT INTO telegram_link_codes (code, discord_id) VALUES (?, ?)",
            (code, str(discord_id))
        )
        conn.commit()
    
    return code

async def verify_link_code(code: str, telegram_id: int, telegram_username: str) -> bool:
    """Проверяет код и создаёт связь Discord-Telegram"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        # Проверяем код и получаем discord_id
        c.execute("""
        SELECT discord_id FROM telegram_link_codes 
        WHERE code = ? AND created_at > datetime('now', '-5 minutes')
        """, (code,))
        result = c.fetchone()
        
        if not result:
            return False
            
        discord_id = result[0]
        
        # Удаляем использованный код
        c.execute("DELETE FROM telegram_link_codes WHERE code = ?", (code,))
        
        # Обновляем или создаём связь
        c.execute("""
        INSERT OR REPLACE INTO telegram_links 
        (discord_id, telegram_id, telegram_username) 
        VALUES (?, ?, ?)
        """, (discord_id, str(telegram_id), telegram_username))
        
        conn.commit()
        
    return True

# Функция для отправки уведомлений
async def send_notification(discord_id: str, text: str | None = None, embed: discord.Embed | None = None) -> None:
    """Отправляет уведомление пользователю в Discord и Telegram (если привязан)"""
    try:
        # Получаем пользователя Discord
        user = bot.get_user(int(discord_id))
        if not user:
            return
            
        # Отправляем в Discord
        try:
            if text:
                await user.send(text)
            if embed:
                await user.send(embed=embed)
        except discord.Forbidden:
            pass  # Пользователь закрыл ЛС
            
        # Проверяем привязку Telegram
        telegram_id = await get_telegram_id(discord_id)
        if not telegram_id:
            return
            
        # Формируем текст для Telegram
        telegram_text = text or ""
        if embed:
            if telegram_text:
                telegram_text += "\n\n"
            telegram_text += f"**{embed.title}**\n\n" if embed.title else ""
            telegram_text += embed.description or ""
            for field in embed.fields:
                telegram_text += f"\n\n{field.name}\n{field.value}"
                
        # Отправляем в Telegram
        if telegram_text:
            try:
                await telegram_bot.send_message(
                    chat_id=telegram_id,
                    text=telegram_text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Ошибка отправки в Telegram {telegram_id}: {e}")
                
    except Exception as e:
        logging.error(f"Ошибка в send_notification: {e}")

# Добавляем запуск Telegram бота в основной цикл
async def main():
    """Основная функция запуска ботов"""
    try:
        # Запускаем оба бота параллельно
        discord_task = asyncio.create_task(bot.start(DISCORD_TOKEN))
        telegram_task = asyncio.create_task(start_telegram_bot())
        
        # Ждем завершения обоих ботов
        await asyncio.gather(discord_task, telegram_task)
    except KeyboardInterrupt:
        # Корректное завершение при Ctrl+C
        logging.info("Получен сигнал завершения работы")
    except Exception as e:
        logging.error(f"Ошибка в main: {e}")
    finally:
        # Закрываем сессии
        if not telegram_bot.session.closed:
            await telegram_bot.session.close()
        await bot.close()

# Запускаем ботов
if __name__ == "__main__":
    asyncio.run(main())

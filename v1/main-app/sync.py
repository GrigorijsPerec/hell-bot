import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import schedule
import time

# === НАСТРОЙКИ ===
DB_NAME = '../bot.db'
SPREADSHEET_NAME = 'hell'  # Название Google Sheets
CREDENTIALS_FILE = '../root-monolith-453308-b0-a09a185173f2.json'  # JSON файл из Google Cloud

# === НАСТРОЙКА ДОСТУПА К GOOGLE SHEETS ===
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)

# === ОТКРЫВАЕМ ТАБЛИЦУ ===
spreadsheet = client.open(SPREADSHEET_NAME)

# === ПОДКЛЮЧАЕМСЯ К БАЗЕ ДАННЫХ ===
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# === ФУНКЦИЯ ДЛЯ ОБНОВЛЕНИЯ ЛИСТОВ ===
def sync_table(sheet_name, query, headers):
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="20")

    try:
        cursor.execute(query)  # Используем глобальный курсор
        records = cursor.fetchall()

        if not records:
            print(f"⚠️ Нет данных для '{sheet_name}'")

        data = [headers] + [list(map(str, row)) for row in records]

        worksheet.clear()
        worksheet.update('A1', data)
        print(f"[{datetime.now()}] ✅ Таблица '{sheet_name}' синхронизирована!")

    except Exception as e:
        print(f"❌ Ошибка при синхронизации '{sheet_name}': {e}")


# === СИНХРОНИЗАЦИЯ ТАБЛИЦ ===
def job():
    print(1)
    print(f"[{datetime.now()}] 🔄 Запуск синхронизации...")
    sync_table(
        sheet_name='Balances',
        query='SELECT member_id, balance, nickname FROM balances',
        headers=['member_id', 'balance', 'nickname']
    )
    sync_table(
        sheet_name='Transactions',
        query='SELECT id, type, member_id, amount, note, timestamp FROM transactions',
        headers=['id', 'type', 'member_id', 'amount', 'note', 'timestamp']
    )
    sync_table(
        sheet_name='Parties',
        query='SELECT party_id, creator_id, info, created_at FROM parties',
        headers=['party_id', 'creator_id', 'info', 'created_at']
    )
    sync_table(
        sheet_name='Party Members',
        query='SELECT party_id, member_id FROM party_members',
        headers=['party_id', 'member_id']
    )
    sync_table(
        sheet_name='Attendance',
        query='SELECT id, member_id, check_in_date FROM attendance',
        headers=['id', 'member_id', 'check_in_date']
    )
    sync_table(
        sheet_name='fines',
        query='SELECT id, user_id, amount, reason, is_closed, timestamp FROM fines',
        headers=['id', 'id', 'AMOUNT', 'REASON', 'IS_CLOSED', 'timestamp']
    )
    print(f"[{datetime.now()}] ✅ Синхронизация завершена!")

# Запуск каждые 5 минут
#schedule.every(5).minutes.do(job)
job()
print("🔄 Запущен скрипт синхронизации (обновление каждые 5 минут)...")
print(f"[{datetime.now()}] ✅ Синхронизация завершена!")
while True:
    schedule.run_pending()
    time.sleep(1)

# === ЗАКРЫВАЕМ ПОДКЛЮЧЕНИЯ ===




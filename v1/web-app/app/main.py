from flask import Flask, render_template, request, redirect, url_for, flash
import json
import os
import sqlite3

app = Flask(__name__)
import os
app.secret_key = os.getenv('APP_SECRET_KEY')

CONFIG_FILE_PATH = "../../config.json"
MESSAGES_FILE_PATH = "../../messages.json"
DB_NAME = "../../bot.db"    
LOG_FILE = "../../bot.json"


def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r', encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE_PATH, 'w', encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def load_messages():
    if os.path.exists(MESSAGES_FILE_PATH):
        with open(MESSAGES_FILE_PATH, 'r', encoding="utf-8") as f:
            return json.load(f)
    return {}


@app.route('/')
def dashboard():
    # Получаем некоторые статистические данные из базы данных
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM transactions")
    transactions_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM balances")
    balances_count = c.fetchone()[0]
    conn.close()
    return render_template("index.html",
                           transactions_count=transactions_count,
                           balances_count=balances_count)


@app.route('/config', methods=['GET', 'POST'])
def config_page():
    config = load_config()
    if request.method == 'POST':
        try:
            config['FINE_CHANNEL_ID'] = int(request.form.get('FINE_CHANNEL_ID', 0))
            config['NOTIFY_CHANNEL_ID'] = int(request.form.get('NOTIFY_CHANNEL_ID', 0))
            config['LOG_CHANNEL_ID'] = int(request.form.get('LOG_CHANNEL_ID', 0))
            config['ROLE_ID'] = int(request.form.get('ROLE_ID', 0))
            config['CONTENT_MAKER_ROLE_ID'] = int(request.form.get('CONTENT_MAKER_ROLE_ID', 0))
            config['FINANCIER_ROLE_ID'] = int(request.form.get('FINANCIER_ROLE_ID', 0))
            save_config(config)
            flash("Конфигурация обновлена", "success")
        except Exception as e:
            flash(f"Ошибка обновления: {e}", "danger")
        return redirect(url_for('config_page'))
    return render_template("config.html", config=config)


@app.route('/messages', methods=['GET', 'POST'])
def messages_page():
    messages = load_messages()
    if request.method == 'POST':
        # Обновляем каждое сообщение, если оно передано из формы
        for key in messages.keys():
            if key in request.form:
                messages[key] = request.form.get(key)
        with open(MESSAGES_FILE_PATH, 'w', encoding="utf-8") as f:
            json.dump(messages, f, indent=4, ensure_ascii=False)
        flash("Сообщения обновлены", "success")
        return redirect(url_for('messages_page'))
    return render_template("messages.html", messages=messages)


@app.route('/logs')
def logs():
    logs = ""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding="utf-8", errors="replace") as f:
            logs = f.read()

    return render_template("logs.html", logs=logs)

@app.route('/bot_console', methods=['GET', 'POST'])
def bot_console():
    output = ""
    if request.method == 'POST':
        command = request.form.get('command')
        # Здесь можно реализовать отправку команды в бот через API или,
        # если бот и веб-приложение работают в одном процессе – вызвать функцию напрямую.
        # Пример: output = bot.execute_console_command(command)
        output = f"Команда '{command}' отправлена боту"  # Заглушка
        flash("Команда отправлена!", "success")
        return redirect(url_for('bot_console'))
    return render_template("bot_console.html", output=output)


if __name__ == '__main__':
    app.run(debug=True)

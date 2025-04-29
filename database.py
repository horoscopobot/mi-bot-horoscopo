import sqlite3

DB_FILE = 'users.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            signo TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def set_user_sign(user_id, signo):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('REPLACE INTO users (user_id, signo) VALUES (?, ?)', (user_id, signo))
    conn.commit()
    conn.close()

def get_user_sign(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT signo FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, signo FROM users')
    result = cursor.fetchall()
    conn.close()
    return result

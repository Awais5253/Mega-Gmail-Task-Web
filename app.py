import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'mega_gmail_task_secret_key'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Users Table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(100) NOT NULL,
            whatsapp VARCHAR(20) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            balance NUMERIC DEFAULT 0,
            status VARCHAR(20) DEFAULT 'Approved',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

# Database Initialize
try:
    init_db()
except Exception as e:
    print("Database init error:", e)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        whatsapp = request.form['whatsapp']
        password = request.form['password']
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (full_name, whatsapp, password) VALUES (%s, %s, %s)",
                        (full_name, whatsapp, password))
            conn.commit()
            cur.close()
            conn.close()
            flash("Registration Successful! Please Login.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            flash("WhatsApp Number already registered!", "danger")
            return render_template('register.html')
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        whatsapp = request.form['whatsapp']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, full_name, password FROM users WHERE whatsapp = %s", (whatsapp,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and user[2] == password:
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            return "<h1>Login Successful! (Home Page Coming Soon)</h1>"
        else:
            flash("Invalid WhatsApp Number or Password!", "danger")
            
    return render_template('login.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

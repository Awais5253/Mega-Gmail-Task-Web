import os
import random
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'mega_gmail_task_secret_key'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def cleanup_old_records():
    """Function to automatically delete tasks and withdrawal history older than 30 days"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE created_at < NOW() - INTERVAL '30 days';")
        cur.execute("DELETE FROM withdrawals WHERE created_at < NOW() - INTERVAL '30 days';")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Cleanup error:", e)

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
    
    # Tasks Table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            gid VARCHAR(20) NOT NULL,
            name VARCHAR(100) NOT NULL,
            dob_year VARCHAR(10) NOT NULL,
            email VARCHAR(150) NOT NULL,
            password VARCHAR(100) NOT NULL,
            price NUMERIC DEFAULT 30,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # Withdrawals Table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            method VARCHAR(20) NOT NULL,
            account_number VARCHAR(20) NOT NULL,
            amount NUMERIC NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print("Database init error:", e)

# Helper function to generate random task data
def generate_random_task(user_id):
    first_names = ["Gregory", "Jason", "Christopher", "Daniel", "Matthew", "Andrew", "Joshua", "David", "James", "Robert"]
    last_names = ["Pruitt", "Waters", "Long", "Miller", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris"]
    
    first = random.choice(first_names)
    last = random.choice(last_names)
    full_name = f"{first} {last}"
    
    dob_year = str(random.randint(1993, 2004))
    rand_num = random.randint(1000000, 9999999)
    email = f"{first.lower()}{last.lower()}{rand_num}@gmail.com"
    password = "aass1122"
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tasks")
    total_count = cur.fetchone()[0] + 1
    gid = f"G{total_count}"
    
    cur.execute("DELETE FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
    
    cur.execute('''
        INSERT INTO tasks (user_id, gid, name, dob_year, email, password, price, status)
        VALUES (%s, %s, %s, %s, %s, %s, 30, 'active')
    ''', (user_id, gid, full_name, dob_year, email, password))
    
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('home'))
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
            return redirect(url_for('home'))
        else:
            flash("Invalid WhatsApp Number or Password!", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cleanup_old_records()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT full_name, balance, status FROM users WHERE id = %s", (session['user_id'],))
    user_info = cur.fetchone()
    
    cur.execute("""
        SELECT gid, email, status 
        FROM tasks 
        WHERE user_id = %s AND status != 'active' 
        ORDER BY (CASE WHEN status = 'pending' THEN 1 ELSE 2 END), id DESC 
        LIMIT 6
    """, (session['user_id'],))
    
    activity_rows = cur.fetchall()
    
    recent_activities = []
    for row in activity_rows:
        recent_activities.append({
            'gid': row[0],
            'email': row[1],
            'status': row[2]
        })
        
    cur.close()
    conn.close()
    
    return render_template('home.html', user=user_info, recent_activities=recent_activities)

@app.route('/account-history')
def account_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cleanup_old_records()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT gid, email, status, price 
        FROM tasks 
        WHERE user_id = %s AND status != 'active' 
        ORDER BY (CASE WHEN status = 'pending' THEN 1 ELSE 2 END), id DESC
    """, (session['user_id'],))
    
    activity_rows = cur.fetchall()
    history = []
    for row in activity_rows:
        history.append({
            'gid': row[0],
            'email': row[1],
            'status': row[2],
            'price': row[3]
        })
        
    cur.close()
    conn.close()
    return render_template('account_history.html', history=history)

@app.route('/withdraw-history')
def withdraw_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cleanup_old_records()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT method, account_number, amount, status,
               COALESCE(TO_CHAR(created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
        FROM withdrawals 
        WHERE user_id = %s 
        ORDER BY id DESC
    """, (session['user_id'],))
    
    withdrawals = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('withdraw_history.html', withdrawals=withdrawals)

@app.route('/tasks', methods=['GET', 'POST'])
def tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM tasks 
        WHERE user_id = %s AND status = 'active' 
        AND created_at < NOW() - INTERVAL '1 hour'
    """, (user_id,))
    conn.commit()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'start_new':
            generate_random_task(user_id)
            return redirect(url_for('tasks'))
            
        elif action == 'done':
            cur.execute("UPDATE tasks SET status = 'pending' WHERE user_id = %s AND status = 'active'", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('home'))
            
        elif action == 'cancel':
            cur.execute("DELETE FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('tasks'))

    cur.execute("SELECT gid, name, dob_year, email, password, price FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
    active_row = cur.fetchone()
    cur.close()
    conn.close()
    
    active_task = None
    if active_row:
        active_task = {
            'gid': active_row[0],
            'name': active_row[1],
            'dob_year': active_row[2],
            'email': active_row[3],
            'password': active_row[4],
            'price': active_row[5]
        }
        
    return render_template('tasks.html', active_task=active_task)

@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cleanup_old_records()
    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        method = request.form.get('method')
        account_number = request.form.get('account_number', '').strip()
        try:
            amount = float(request.form.get('amount', 0))
        except ValueError:
            amount = 0
            
        cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
        user_balance = float(cur.fetchone()[0])
        
        if method not in ['JazzCash', 'EasyPaisa']:
            flash("Please select JazzCash or EasyPaisa!", "danger")
        elif not account_number.isdigit() or len(account_number) != 11:
            flash("Account number must be exactly 11 digits!", "danger")
        elif amount < 30:
            flash("Minimum withdrawal amount is PKR 30!", "danger")
        elif amount > user_balance:
            flash("Insufficient balance!", "danger")
        else:
            cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (amount, user_id))
            cur.execute("""
                INSERT INTO withdrawals (user_id, method, account_number, amount, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (user_id, method, account_number, amount))
            conn.commit()
            flash("Withdrawal request submitted successfully!", "success")
            cur.close()
            conn.close()
            return redirect(url_for('wallet'))

    cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
    balance = cur.fetchone()[0]
    
    cur.execute("""
        SELECT method, account_number, amount, status,
               COALESCE(TO_CHAR(created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
        FROM withdrawals 
        WHERE user_id = %s 
        ORDER BY id DESC LIMIT 6
    """, (user_id,))
    withdrawals = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template('wallet.html', balance=balance, withdrawals=withdrawals)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    cleanup_old_records()
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        task_id = request.form.get('task_id')
        withdraw_id = request.form.get('withdraw_id')
        action = request.form.get('action')
        
        if task_id:
            if action == 'approve':
                cur.execute("SELECT user_id, price, status FROM tasks WHERE id = %s", (task_id,))
                row = cur.fetchone()
                if row and row[2] == 'pending':
                    u_id, price = row[0], row[1]
                    cur.execute("UPDATE tasks SET status = 'Approved', created_at = CURRENT_TIMESTAMP WHERE id = %s", (task_id,))
                    cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (price, u_id))
                    conn.commit()
            elif action == 'not_exist':
                cur.execute("UPDATE tasks SET status = 'Not Exist', created_at = CURRENT_TIMESTAMP WHERE id = %s", (task_id,))
                conn.commit()
            elif action == 'reject':
                cur.execute("UPDATE tasks SET status = 'Rejected', created_at = CURRENT_TIMESTAMP WHERE id = %s", (task_id,))
                conn.commit()
                
        elif withdraw_id:
            if action == 'approve_withdraw':
                cur.execute("UPDATE withdrawals SET status = 'Approved', created_at = CURRENT_TIMESTAMP WHERE id = %s", (withdraw_id,))
                conn.commit()
            elif action == 'reject_withdraw':
                cur.execute("SELECT user_id, amount, status FROM withdrawals WHERE id = %s", (withdraw_id,))
                w_row = cur.fetchone()
                if w_row and w_row[2] == 'pending':
                    u_id, w_amount = w_row[0], w_row[1]
                    cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (w_amount, u_id))
                    cur.execute("UPDATE withdrawals SET status = 'Rejected', created_at = CURRENT_TIMESTAMP WHERE id = %s", (withdraw_id,))
                    conn.commit()
            
        cur.close()
        conn.close()
        return redirect(url_for('admin'))
    
    cur.execute("""
        SELECT tasks.id, users.full_name, users.whatsapp, tasks.gid, tasks.name, 
               tasks.dob_year, tasks.email, tasks.password, tasks.price, tasks.status,
               COALESCE(TO_CHAR(tasks.created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
        FROM tasks 
        JOIN users ON tasks.user_id = users.id 
        WHERE tasks.status != 'active' 
        ORDER BY (CASE WHEN tasks.status = 'pending' THEN 1 ELSE 2 END), tasks.id DESC 
        LIMIT 30
    """)
    all_tasks = cur.fetchall()
    
    cur.execute("""
        SELECT withdrawals.id, users.full_name, users.whatsapp, withdrawals.method, 
               withdrawals.account_number, withdrawals.amount, withdrawals.status,
               COALESCE(TO_CHAR(withdrawals.created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
        FROM withdrawals 
        JOIN users ON withdrawals.user_id = users.id 
        ORDER BY (CASE WHEN withdrawals.status = 'pending' THEN 1 ELSE 2 END), withdrawals.id DESC 
        LIMIT 30
    """)
    all_withdrawals = cur.fetchall()

    cur.execute("""
        SELECT full_name, whatsapp, password,
               COALESCE(TO_CHAR(created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
        FROM users 
        ORDER BY id DESC
    """)
    all_users = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('admin.html', tasks=all_tasks, withdrawals=all_withdrawals, users=all_users)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

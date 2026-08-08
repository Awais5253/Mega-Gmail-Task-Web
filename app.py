import os
import random
import psycopg2
from psycopg2 import pool
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = 'mega_gmail_task_secret_key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

DATABASE_URL = os.environ.get('DATABASE_URL')

db_pool = pool.ThreadedConnectionPool(
    1, 20, DATABASE_URL,
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5
)

@contextmanager
def db_cursor():
    conn = None
    for attempt in range(2):
        try:
            conn = db_pool.getconn()
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            cur.close()
            break
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            if conn:
                try:
                    db_pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = None
            if attempt == 1:
                raise
    try:
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise e
    finally:
        if conn:
            try:
                db_pool.putconn(conn)
            except Exception:
                pass

def cleanup_old_records():
    try:
        with db_cursor() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM tasks WHERE created_at < NOW() - INTERVAL '30 days';")
            cur.execute("DELETE FROM withdrawals WHERE created_at < NOW() - INTERVAL '30 days';")
            cur.execute("DELETE FROM referral_earnings WHERE created_at < NOW() - INTERVAL '30 days';")
            cur.close()
    except Exception as e:
        print("Cleanup error:", e)

def init_db():
    with db_cursor() as conn:
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                whatsapp VARCHAR(20) UNIQUE NOT NULL,
                password VARCHAR(100) NOT NULL,
                balance NUMERIC DEFAULT 0,
                status VARCHAR(20) DEFAULT 'Approved',
                referred_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(20);")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by INTEGER REFERENCES users(id) ON DELETE SET NULL;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        
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
        cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")

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
        cur.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS referral_earnings (
                id SERIAL PRIMARY KEY,
                referrer_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                referred_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                amount NUMERIC DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cur.execute("ALTER TABLE referral_earnings ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        cur.close()

try:
    init_db()
except Exception as e:
    print("Database init error:", e)

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
    
    with db_cursor() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tasks")
        total_count = cur.fetchone()[0] + 1
        gid = f"G{total_count}"
        
        cur.execute("DELETE FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
        
        cur.execute('''
            INSERT INTO tasks (user_id, gid, name, dob_year, email, password, price, status)
            VALUES (%s, %s, %s, %s, %s, %s, 30, 'active')
        ''', (user_id, gid, full_name, dob_year, email, password))
        cur.close()

@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    ref_param = (request.args.get('ref') or request.form.get('ref') or '').strip()
    
    ref_db_id = None
    if ref_param.isdigit():
        val = int(ref_param)
        ref_db_id = val - 100 if val > 100 else val

    valid_referrer_id = None
    is_valid_ref = False

    if ref_param:
        try:
            with db_cursor() as conn:
                cur = conn.cursor()
                if ref_db_id is not None:
                    cur.execute("SELECT id FROM users WHERE id = %s LIMIT 1", (ref_db_id,))
                else:
                    cur.execute("SELECT id FROM users WHERE full_name = %s LIMIT 1", (ref_param,))
                
                user_row = cur.fetchone()
                cur.close()

                if user_row:
                    valid_referrer_id = user_row[0]
                    is_valid_ref = True
        except Exception as e:
            print("Referrer lookup error:", e)

    is_locked = False
    if request.method == 'GET':
        if ref_param and is_valid_ref:
            is_locked = True
        elif ref_param and not is_valid_ref:
            flash("Invalid Referral Link or Code!", "danger")
            ref_param = ''

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        whatsapp = request.form.get('whatsapp', '').strip()
        password = request.form.get('password', '').strip()

        if ref_param and not is_valid_ref:
            flash("Invalid Referral Code! User does not exist.", "danger")
            return render_template('register.html', ref=ref_param, is_locked=False)

        try:
            with db_cursor() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO users (full_name, whatsapp, password, referred_by) 
                    VALUES (%s, %s, %s, %s)
                """, (full_name, whatsapp, password, valid_referrer_id))
                cur.close()
            flash("Registration Successful! Please Login.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            flash("WhatsApp Number already registered!", "danger")
            return render_template('register.html', ref=ref_param, is_locked=is_locked)

    return render_template('register.html', ref=ref_param, is_locked=is_locked)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        whatsapp = request.form['whatsapp']
        password = request.form['password']
        
        with db_cursor() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, full_name, password FROM users WHERE whatsapp = %s", (whatsapp,))
            user = cur.fetchone()
            cur.close()
        
        if user and user[2] == password:
            session.permanent = True
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
    
    with db_cursor() as conn:
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
        cur.close()
    
    recent_activities = []
    for row in activity_rows:
        recent_activities.append({
            'gid': row[0],
            'email': row[1],
            'status': row[2]
        })
    
    return render_template('home.html', user=user_info, recent_activities=recent_activities)

@app.route('/referrals')
def referrals():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cleanup_old_records()
    user_id = session['user_id']
    
    with db_cursor() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT id, full_name, balance FROM users WHERE id = %s", (user_id,))
        user_row = cur.fetchone()
        
        cur.execute("SELECT COUNT(*) FROM users WHERE referred_by = %s", (user_id,))
        total_referrals = cur.fetchone()[0]
        
        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM referral_earnings 
            WHERE referrer_id = %s AND created_at >= NOW() - INTERVAL '30 days'
        """, (user_id,))
        ref_earnings = cur.fetchone()[0]
        
        cur.execute("""
            SELECT u.full_name, COALESCE(SUM(re.amount), 0) as earned_30d
            FROM users u
            LEFT JOIN referral_earnings re ON re.referred_user_id = u.id 
                AND re.referrer_id = %s 
                AND re.created_at >= NOW() - INTERVAL '30 days'
            WHERE u.referred_by = %s
            GROUP BY u.id, u.full_name
            ORDER BY u.id DESC
        """, (user_id, user_id))
        
        ref_rows = cur.fetchall()
        cur.close()
        
    referrals_list = []
    for row in ref_rows:
        referrals_list.append({
            'username': row[0],
            'earned_30d': row[1]
        })
        
    user_info = [user_row[0], user_row[1], user_row[2]]
    display_id = user_row[0] + 100
    
    return render_template(
        'referrals.html', 
        user=user_info, 
        display_id=display_id,
        total_referrals=total_referrals, 
        ref_earnings=ref_earnings, 
        referrals_list=referrals_list
    )

@app.route('/account-history')
def account_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cleanup_old_records()
    
    with db_cursor() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT gid, email, status, price 
            FROM tasks 
            WHERE user_id = %s AND status != 'active' 
            ORDER BY (CASE WHEN status = 'pending' THEN 1 ELSE 2 END), id DESC
        """, (session['user_id'],))
        
        activity_rows = cur.fetchall()
        cur.close()
        
    history = []
    for row in activity_rows:
        history.append({
            'gid': row[0],
            'email': row[1],
            'status': row[2],
            'price': row[3]
        })
        
    return render_template('account_history.html', history=history)

@app.route('/withdraw-history')
def withdraw_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cleanup_old_records()
    
    with db_cursor() as conn:
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
        
    return render_template('withdraw_history.html', withdrawals=withdrawals)

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    cleanup_old_records()
    user_id = session['user_id']
    
    with db_cursor() as conn:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT full_name, whatsapp, 
                   COALESCE(TO_CHAR(created_at + INTERVAL '5 hours', 'DD Mon YYYY'), 'N/A')
            FROM users WHERE id = %s
        """, (user_id,))
        u_row = cur.fetchone()
        
        user_name = u_row[0] if u_row else ''
        user_phone = u_row[1] if u_row else ''
        joining_date = u_row[2] if u_row else ''
        
        display_user_id = user_id + 100
        
        cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = %s AND status = 'Approved'", (user_id,))
        approved_tasks = cur.fetchone()[0]
        
        cur.execute("SELECT COALESCE(SUM(price), 0) FROM tasks WHERE user_id = %s AND status = 'Approved'", (user_id,))
        task_earned = float(cur.fetchone()[0])
        
        cur.execute("SELECT COALESCE(SUM(amount), 0) FROM referral_earnings WHERE referrer_id = %s", (user_id,))
        ref_earned = float(cur.fetchone()[0])
        
        total_earned = task_earned + ref_earned
        
        cur.execute("SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE user_id = %s AND status = 'Approved'", (user_id,))
        total_withdrawn = float(cur.fetchone()[0])
        
        cur.close()
    
    return render_template(
        'profile.html',
        user_id=display_user_id,
        user_name=user_name,
        user_phone=user_phone,
        joining_date=joining_date,
        total_earned=total_earned,
        total_withdrawn=total_withdrawn,
        approved_tasks=approved_tasks
    )

@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    old_password = request.form.get('old_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    
    with db_cursor() as conn:
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        current_db_password = cur.fetchone()[0]
        
        if current_db_password == old_password:
            cur.execute("UPDATE users SET password = %s WHERE id = %s", (new_password, user_id))
            flash("Password updated successfully!", "success")
        else:
            flash("Incorrect Old Password!", "danger")
        cur.close()
    
    return redirect(url_for('profile'))

@app.route('/tasks', methods=['GET', 'POST'])
def tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    with db_cursor() as conn:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM tasks 
            WHERE user_id = %s AND status = 'active' 
            AND created_at < NOW() - INTERVAL '1 hour'
        """, (user_id,))
        cur.close()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'start_new':
            generate_random_task(user_id)
            return redirect(url_for('tasks'))
            
        elif action == 'done':
            with db_cursor() as conn:
                cur = conn.cursor()
                cur.execute("UPDATE tasks SET status = 'pending' WHERE user_id = %s AND status = 'active'", (user_id,))
                cur.close()
            return redirect(url_for('home'))
            
        elif action == 'cancel':
            with db_cursor() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
                cur.close()
            return redirect(url_for('tasks'))

    with db_cursor() as conn:
        cur = conn.cursor()
        cur.execute("SELECT gid, name, dob_year, email, password, price FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
        active_row = cur.fetchone()
        cur.close()
    
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
    
    if request.method == 'POST':
        method = request.form.get('method')
        account_number = request.form.get('account_number', '').strip()
        try:
            amount = float(request.form.get('amount', 0))
        except ValueError:
            amount = 0
            
        with db_cursor() as conn:
            cur = conn.cursor()
            cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            user_balance = float(cur.fetchone()[0])
            cur.close()
            
        if method not in ['JazzCash', 'EasyPaisa']:
            flash("Please select JazzCash or EasyPaisa!", "danger")
        elif not account_number.isdigit() or len(account_number) != 11:
            flash("Account number must be exactly 11 digits!", "danger")
        elif amount < 30:
            flash("Minimum withdrawal amount is PKR 30!", "danger")
        elif amount > user_balance:
            flash("Insufficient balance!", "danger")
        else:
            with db_cursor() as conn:
                cur = conn.cursor()
                cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (amount, user_id))
                cur.execute("""
                    INSERT INTO withdrawals (user_id, method, account_number, amount, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                """, (user_id, method, account_number, amount))
                cur.close()
            flash("Withdrawal request submitted successfully!", "success")
            return redirect(url_for('wallet'))

    with db_cursor() as conn:
        cur = conn.cursor()
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
        
    return render_template('wallet.html', balance=balance, withdrawals=withdrawals)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    cleanup_old_records()
    
    if request.method == 'POST':
        task_id = request.form.get('task_id')
        withdraw_id = request.form.get('withdraw_id')
        action = request.form.get('action')
        
        with db_cursor() as conn:
            cur = conn.cursor()
            if task_id:
                if action == 'approve':
                    cur.execute("SELECT user_id, price, status FROM tasks WHERE id = %s", (task_id,))
                    row = cur.fetchone()
                    if row and row[2] == 'pending':
                        u_id, price = row[0], row[1]
                        cur.execute("UPDATE tasks SET status = 'Approved', created_at = CURRENT_TIMESTAMP WHERE id = %s", (task_id,))
                        cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (price, u_id))
                        
                        cur.execute("SELECT referred_by FROM users WHERE id = %s", (u_id,))
                        ref_row = cur.fetchone()
                        if ref_row and ref_row[0]:
                            referrer_id = ref_row[0]
                            cur.execute("UPDATE users SET balance = balance + 10 WHERE id = %s", (referrer_id,))
                            cur.execute("""
                                INSERT INTO referral_earnings (referrer_id, referred_user_id, task_id, amount)
                                VALUES (%s, %s, %s, 10)
                            """, (referrer_id, u_id, task_id))
                elif action == 'not_exist':
                    cur.execute("UPDATE tasks SET status = 'Not Exist', created_at = CURRENT_TIMESTAMP WHERE id = %s", (task_id,))
                elif action == 'reject':
                    cur.execute("UPDATE tasks SET status = 'Rejected', created_at = CURRENT_TIMESTAMP WHERE id = %s", (task_id,))
                    
            elif withdraw_id:
                if action == 'approve_withdraw':
                    cur.execute("UPDATE withdrawals SET status = 'Approved', created_at = CURRENT_TIMESTAMP WHERE id = %s", (withdraw_id,))
                elif action == 'reject_withdraw':
                    cur.execute("SELECT user_id, amount, status FROM withdrawals WHERE id = %s", (withdraw_id,))
                    w_row = cur.fetchone()
                    if w_row and w_row[2] == 'pending':
                        u_id, w_amount = w_row[0], w_row[1]
                        cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (w_amount, u_id))
                        cur.execute("UPDATE withdrawals SET status = 'Rejected', created_at = CURRENT_TIMESTAMP WHERE id = %s", (withdraw_id,))
            cur.close()
            
        return redirect(url_for('admin'))
    
    user_page = request.args.get('user_page', 1, type=int)
    task_page = request.args.get('task_page', 1, type=int)
    withdraw_page = request.args.get('withdraw_page', 1, type=int)
    per_page = 50

    with db_cursor() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        total_user_pages = (total_users + per_page - 1) // per_page
        user_offset = (user_page - 1) * per_page

        cur.execute("""
            SELECT (id + 100), full_name, whatsapp, password,
                   COALESCE(TO_CHAR(created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
            FROM users 
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """, (per_page, user_offset))
        all_users = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM tasks WHERE status != 'active'")
        total_tasks = cur.fetchone()[0]
        total_task_pages = (total_tasks + per_page - 1) // per_page
        task_offset = (task_page - 1) * per_page

        cur.execute("""
            SELECT tasks.id, users.full_name, users.whatsapp, tasks.gid, tasks.name, 
                   tasks.dob_year, tasks.email, tasks.password, tasks.price, tasks.status,
                   COALESCE(TO_CHAR(tasks.created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
            FROM tasks 
            JOIN users ON tasks.user_id = users.id 
            WHERE tasks.status != 'active' 
            ORDER BY (CASE WHEN tasks.status = 'pending' THEN 1 ELSE 2 END), tasks.id DESC 
            LIMIT %s OFFSET %s
        """, (per_page, task_offset))
        all_tasks = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) FROM withdrawals")
        total_withdrawals = cur.fetchone()[0]
        total_withdraw_pages = (total_withdrawals + per_page - 1) // per_page
        withdraw_offset = (withdraw_page - 1) * per_page

        cur.execute("""
            SELECT withdrawals.id, users.full_name, users.whatsapp, withdrawals.method, 
                   withdrawals.account_number, withdrawals.amount, withdrawals.status,
                   COALESCE(TO_CHAR(withdrawals.created_at + INTERVAL '5 hours', 'DD-Mon-YYYY HH12:MI AM'), 'N/A')
            FROM withdrawals 
            JOIN users ON withdrawals.user_id = users.id 
            ORDER BY (CASE WHEN withdrawals.status = 'pending' THEN 1 ELSE 2 END), withdrawals.id DESC 
            LIMIT %s OFFSET %s
        """, (per_page, withdraw_offset))
        all_withdrawals = cur.fetchall()
        
        cur.close()
    
    return render_template(
        'admin.html', 
        tasks=all_tasks, 
        withdrawals=all_withdrawals, 
        users=all_users, 
        user_page=user_page, 
        total_user_pages=total_user_pages,
        task_page=task_page,
        total_task_pages=total_task_pages,
        withdraw_page=withdraw_page,
        total_withdraw_pages=total_withdraw_pages
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

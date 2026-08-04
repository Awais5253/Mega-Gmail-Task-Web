import os
import random
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
    
    dob_year = str(random.randint(1993, 2004)) # 20+ years old
    rand_num = random.randint(1000000, 9999999)
    email = f"{first.lower()}{last.lower()}{rand_num}@gmail.com"
    password = "aass1122"  # Strictly fixed password as requested
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tasks")
    total_count = cur.fetchone()[0] + 1
    gid = f"G{total_count}"
    
    # Delete old active task if exists (Cleanup)
    cur.execute("DELETE FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
    
    # Insert new active task
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

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Fetch User Details
    cur.execute("SELECT full_name, balance, status FROM users WHERE id = %s", (session['user_id'],))
    user_info = cur.fetchone()
    
    # Fetch Recent Activity (Pending first, then Approved/Rejected, Limit 10)
    cur.execute("""
        SELECT gid, email, status 
        FROM tasks 
        WHERE user_id = %s AND status != 'active' 
        ORDER BY (CASE WHEN status = 'pending' THEN 1 ELSE 2 END), id DESC 
        LIMIT 10
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

@app.route('/tasks', methods=['GET', 'POST'])
def tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1-Hour Task Expiry Cleanup
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
            # Change status from active to pending
            cur.execute("UPDATE tasks SET status = 'pending' WHERE user_id = %s AND status = 'active'", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('home'))
            
        elif action == 'cancel':
            # Delete active task to save DB memory
            cur.execute("DELETE FROM tasks WHERE user_id = %s AND status = 'active'", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('tasks'))

    # Fetch active task if exists
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

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        task_id = request.form.get('task_id')
        action = request.form.get('action')
        
        if action == 'approve':
            # Get user_id and price
            cur.execute("SELECT user_id, price FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            if row:
                u_id, price = row[0], row[1]
                # Update task status to Approved
                cur.execute("UPDATE tasks SET status = 'Approved' WHERE id = %s", (task_id,))
                # Add balance to user account
                cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (price, u_id))
                conn.commit()
                
        elif action == 'not_exist':
            cur.execute("UPDATE tasks SET status = 'Not Exist' WHERE id = %s", (task_id,))
            conn.commit()
            
        elif action == 'reject':
            cur.execute("UPDATE tasks SET status = 'Rejected' WHERE id = %s", (task_id,))
            conn.commit()
            
        cur.close()
        conn.close()
        return redirect(url_for('admin'))
    
    # Fetch all pending tasks joined with user details
    cur.execute("""
        SELECT tasks.id, users.full_name, users.whatsapp, tasks.gid, tasks.name, 
               tasks.dob_year, tasks.email, tasks.password, tasks.price
        FROM tasks 
        JOIN users ON tasks.user_id = users.id 
        WHERE tasks.status = 'pending' 
        ORDER BY tasks.id DESC
    """)
    pending_tasks = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('admin.html', tasks=pending_tasks)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

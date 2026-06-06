# backend/database.py
import sqlite3
import os
from datetime import datetime # Import datetime

def get_db_connection(db_path):
    """Establishes a connection to the database."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True) # Ensure data directory exists
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # Return rows as dict-like objects
    # Enable foreign key support if needed later
    # conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(db_path):
    """Initializes the database and creates the tasks table if it doesn't exist."""
    conn = None # Initialize conn
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT CHECK(priority IN ('高', '中', '低')) DEFAULT '中', -- Added CHECK constraint
                completed BOOLEAN DEFAULT 0,
                category TEXT,
                due_date TEXT, -- Store dates as ISO8601 strings (YYYY-MM-DD HH:MM:SS) or NULL
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                -- Add fields for recurring tasks, reminders etc. later
            )
        ''')
        # Add trigger to update updated_at timestamp
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS update_task_updated_at
            AFTER UPDATE ON tasks
            FOR EACH ROW
            WHEN OLD.updated_at = NEW.updated_at -- Avoid infinite loop if updated_at is explicitly set
            BEGIN
                UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;
        ''')
        conn.commit()
        print(f"Database initialized/checked at {db_path}")
    except sqlite3.Error as e:
        print(f"Database error during initialization: {e}")
    finally:
        if conn:
            conn.close()


def get_tasks(db_path):
    tasks = []
    conn = None # Initialize conn
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        # Order by completion status (incomplete first), then priority (High first), then due date
        cursor.execute("""
            SELECT * FROM tasks
            ORDER BY
                completed ASC,
                CASE priority
                    WHEN '高' THEN 1
                    WHEN '中' THEN 2
                    WHEN '低' THEN 3
                    ELSE 4
                END ASC,
                due_date ASC,
                created_at DESC
        """)
        tasks = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Database error getting tasks: {e}")
    finally:
        if conn:
            conn.close()
    return tasks

def add_task(db_path, task_data):
    task_id = None
    conn = None # Initialize conn
    # Validate priority
    priority = task_data.get('priority', '中')
    if priority not in ('高', '中', '低'):
        priority = '中' # Default to medium if invalid

    sql = """
        INSERT INTO tasks (title, description, priority, category, due_date, completed)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    params = (
        task_data.get('title'),
        task_data.get('description'),
        priority,
        task_data.get('category'),
        task_data.get('due_date'), # Already formatted by JS or None
        task_data.get('completed', 0) # Allow setting completion on add
    )
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        task_id = cursor.lastrowid
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error adding task: {e}")
        if conn:
            conn.rollback() # Rollback on error
    finally:
        if conn:
            conn.close()
    return task_id


def update_task(db_path, task_id, task_data):
    updated_rows = 0
    conn = None
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # Build SET clause dynamically based on provided data
        fields = []
        values = []
        allowed_fields = ['title', 'description', 'priority', 'completed', 'category', 'due_date']

        for key, value in task_data.items():
            if key in allowed_fields:
                # Validate priority
                if key == 'priority' and value not in ('高', '中', '低'):
                    continue # Skip invalid priority update
                # Handle boolean conversion for 'completed'
                if key == 'completed':
                    value = 1 if value else 0
                # Handle empty strings for optional fields (set to NULL)
                if key in ['description', 'category', 'due_date'] and value == '':
                     value = None

                fields.append(f"{key} = ?")
                values.append(value)

        if not fields:
            print("No valid fields provided for update.")
            return False # Nothing to update or invalid fields

        # Add updated_at manually here if not using trigger or want specific time
        # fields.append("updated_at = ?")
        # values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        values.append(task_id) # Add task_id for WHERE clause
        sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"

        cursor.execute(sql, tuple(values))
        updated_rows = cursor.rowcount
        conn.commit()

    except sqlite3.Error as e:
        print(f"Database error updating task {task_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    return updated_rows > 0


def delete_task(db_path, task_id):
    deleted_rows = 0
    conn = None
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        deleted_rows = cursor.rowcount
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error deleting task {task_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    return deleted_rows > 0

# Optional: Function to get a single task by ID (useful for returning after add/update)
def get_task_by_id(db_path, task_id):
    task = None
    conn = None
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if row:
            task = dict(row)
    except sqlite3.Error as e:
        print(f"Database error getting task by ID {task_id}: {e}")
    finally:
        if conn:
            conn.close()
    return task
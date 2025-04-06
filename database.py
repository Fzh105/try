import sqlite3
import hashlib # 用于密码哈希（虽然简单，但比明文好）
import os

DATABASE_NAME = 'output_time.db'

# --- 用户相关 ---
def initialize_users_table():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            has_rest_day_next_week INTEGER DEFAULT 1 NOT NULL CHECK(has_rest_day_next_week IN (0, 1))
        )
    ''')
    conn.commit()
    conn.close()
    print("Users table initialized.")

def add_user(email, password):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    # 简单的哈希处理，实际应用应使用更安全的库如 bcrypt
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    try:
        cursor.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, hashed_password))
        conn.commit()
        print(f"User {email} added.")
        return True
    except sqlite3.IntegrityError:
        print(f"User {email} already exists.")
        return False
    finally:
        conn.close()

def verify_user(email, password):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute("SELECT password_hash FROM users WHERE email = ?", (email,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0] == hashed_password:
        return True
    return False

def get_all_users():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT email, has_rest_day_next_week FROM users")
    users = cursor.fetchall()
    conn.close()
    return users # 返回 [(email1, has_rest_day1), (email2, has_rest_day2)]

def update_rest_day_status(email, has_rest_day):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET has_rest_day_next_week = ? WHERE email = ?", (1 if has_rest_day else 0, email))
    conn.commit()
    conn.close()

def can_use_rest_day(email):
    """检查用户本周是否还有休息日额度"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT has_rest_day_next_week FROM users WHERE email = ?", (email,))
    result = cursor.fetchone()
    conn.close()
    # 注意：这里的命名是 has_rest_day_NEXT_week，但我们用它来控制 *本周* 能否使用
    # 惩罚是在周日晚上执行，所以周一到周日看这个标志位是合理的
    return result and result[0] == 1

# --- 总结相关 ---
def initialize_summaries_table():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            submission_date DATE NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            is_rest_day INTEGER DEFAULT 0 NOT NULL CHECK(is_rest_day IN (0, 1)),
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
    ''')
    # 添加唯一约束，防止同一用户同一天提交多次 (休息日标记除外)
    # 如果希望允许覆盖，则不加此约束
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_date
        ON summaries (user_email, submission_date)
        WHERE is_rest_day = 0
    ''')
    conn.commit()
    conn.close()
    print("Summaries table initialized.")

def save_summary(user_email, submission_date, content, word_count, is_rest_day=0):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
         # 简单处理：如果今天已经提交过非休息日的总结，不允许再提交 (除非是休息日标记)
         # 更优：可以允许覆盖，使用 INSERT OR REPLACE
        cursor.execute("""
            INSERT INTO summaries (user_email, submission_date, content, word_count, is_rest_day)
            VALUES (?, ?, ?, ?, ?)
        """, (user_email, submission_date, content, word_count, 1 if is_rest_day else 0))
        conn.commit()
        print(f"Summary saved for {user_email} on {submission_date}.")
        return True
    except sqlite3.IntegrityError:
         print(f"Error: User {user_email} already submitted a non-rest-day summary for {submission_date}.")
         return False # 或者在这里实现更新逻辑
    except Exception as e:
        print(f"An error occurred: {e}")
        return False
    finally:
        conn.close()

def get_summaries_by_user(user_email):
    conn = sqlite3.connect(DATABASE_NAME)
    # 使用 pandas 读取更方便 Streamlit 显示
    query = f"SELECT submission_date, content, word_count, is_rest_day FROM summaries WHERE user_email = '{user_email}' ORDER BY submission_date DESC"
    try:
        import pandas as pd
        df = pd.read_sql_query(query, conn)
        # 将 is_rest_day 从 0/1 转为 True/False 或 Yes/No
        if not df.empty:
             df['is_rest_day'] = df['is_rest_day'].apply(lambda x: 'Yes' if x == 1 else 'No')
             df.rename(columns={'submission_date': 'Date', 'content': 'Summary', 'word_count':'Words', 'is_rest_day':'Used Rest Day?'}, inplace=True)
        return df
    except Exception as e:
        print(f"Error reading summaries: {e}")
        return pd.DataFrame() # 返回空 DataFrame
    finally:
        conn.close()

def check_submission_today(user_email, check_date):
    """检查用户今天是否提交了有效的总结（非休息日且字数>200）"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM summaries
        WHERE user_email = ? AND submission_date = ? AND is_rest_day = 0 AND word_count >= 200
    """, (user_email, check_date))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def check_if_rest_day_used(user_email, check_date):
     """检查用户今天是否将此日标记为休息日"""
     conn = sqlite3.connect(DATABASE_NAME)
     cursor = conn.cursor()
     cursor.execute("""
         SELECT 1 FROM summaries
         WHERE user_email = ? AND submission_date = ? AND is_rest_day = 1
     """, (user_email, check_date))
     result = cursor.fetchone()
     conn.close()
     return result is not None


def get_valid_submission_dates_for_week(user_email, start_date, end_date):
    """获取指定周内有效提交的日期列表"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT submission_date FROM summaries
        WHERE user_email = ? AND submission_date BETWEEN ? AND ? AND is_rest_day = 0 AND word_count >= 200
    """, (user_email, start_date, end_date))
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def get_used_rest_dates_for_week(user_email, start_date, end_date):
     """获取指定周内标记为休息日的日期列表"""
     conn = sqlite3.connect(DATABASE_NAME)
     cursor = conn.cursor()
     cursor.execute("""
         SELECT submission_date FROM summaries
         WHERE user_email = ? AND submission_date BETWEEN ? AND ? AND is_rest_day = 1
     """, (user_email, start_date, end_date))
     dates = [row[0] for row in cursor.fetchall()]
     conn.close()
     return dates


# --- 初始化 ---
def initialize_database():
    if not os.path.exists(DATABASE_NAME):
         print(f"Database {DATABASE_NAME} not found, creating...")
         initialize_users_table()
         initialize_summaries_table()
         # 你可以在这里添加初始用户，方便测试
         # add_user('test@example.com', 'password123')
         # add_user('friend1@email.com', 'friendpass')
    else:
         # 确保表结构是最新的（如果后续修改了表结构）
         initialize_users_table()
         initialize_summaries_table()
         print(f"Database {DATABASE_NAME} already exists. Tables checked/initialized.")

if __name__ == '__main__':
    # 首次运行此脚本来创建数据库和表
    initialize_database()
    print("Database setup script finished.")
    # 手动添加用户示例
    # add_user('1057456026@qq.com', '123')
    # add_user('friend_email@example.com', 'friend_password')
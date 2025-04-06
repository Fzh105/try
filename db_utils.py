from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, extract
from datetime import date, timedelta
import bcrypt # 用于密码处理
from models import User, Summary, SessionLocal # 从 models.py 导入

MIN_WORD_COUNT = 200 # 保持和主应用一致

# --- 数据库会话管理 ---
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 用户相关操作 ---
def add_user(db: Session, email: str, password: str):
    """添加新用户，对密码进行哈希处理"""
    # 检查用户是否已存在
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        print(f"User {email} already exists.")
        return False
    try:
        # 哈希密码
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        db_user = User(email=email, password_hash=hashed_password.decode('utf-8')) # 存储解码后的哈希字符串
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        print(f"User {email} added successfully.")
        return True
    except Exception as e:
        db.rollback()
        print(f"Error adding user {email}: {e}")
        return False

def verify_user(db: Session, email: str, password: str):
    """验证用户邮箱和密码"""
    user = db.query(User).filter(User.email == email).first()
    if user:
        # 验证密码哈希
        if bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            return True
    return False

def get_all_users(db: Session):
    """获取所有用户信息 (邮箱和下周休息日状态)"""
    return db.query(User.email, User.has_rest_day_next_week).all()

def update_rest_day_status(db: Session, email: str, has_rest_day: bool):
    """更新用户的下周休息日状态"""
    user = db.query(User).filter(User.email == email).first()
    if user:
        try:
            user.has_rest_day_next_week = has_rest_day
            db.commit()
            print(f"Updated rest day status for {email} to {has_rest_day}")
        except Exception as e:
            db.rollback()
            print(f"Error updating rest day status for {email}: {e}")

def can_use_rest_day(db: Session, email: str):
    """检查用户本周是否还有休息日额度"""
    user = db.query(User).filter(User.email == email).first()
    return user and user.has_rest_day_next_week

# --- 总结相关操作 ---
def save_summary(db: Session, user_email: str, submission_date: date, content: str, word_count: int, is_rest_day: bool = False):
    """保存每日总结"""
    try:
        # 对于非休息日，唯一约束会阻止重复提交
        db_summary = Summary(
            user_email=user_email,
            submission_date=submission_date,
            content=content,
            word_count=word_count,
            is_rest_day=is_rest_day
        )
        db.add(db_summary)
        db.commit()
        db.refresh(db_summary)
        print(f"Summary saved for {user_email} on {submission_date}.")
        return True
    except Exception as e: # 捕获包括唯一约束在内的错误
        db.rollback()
        print(f"Error saving summary for {user_email} on {submission_date}: {e}")
        # 可以检查错误类型，如果是唯一约束违反，给用户更明确的提示
        if "UniqueViolation" in str(e) or "_user_date_uc" in str(e):
             print("Maybe a non-rest-day summary for this date already exists?")
        return False


def get_summaries_by_user_df(db: Session, user_email: str):
    """获取指定用户的所有总结，并返回 Pandas DataFrame"""
    summaries = db.query(
        Summary.submission_date,
        Summary.content,
        Summary.word_count,
        Summary.is_rest_day
    ).filter(Summary.user_email == user_email).order_by(Summary.submission_date.desc()).all()

    # 转换为 DataFrame
    import pandas as pd
    if summaries:
        df = pd.DataFrame(summaries, columns=['Date', 'Summary', 'Words', 'Used Rest Day?'])
        df['Used Rest Day?'] = df['Used Rest Day?'].apply(lambda x: 'Yes' if x else 'No')
        return df
    else:
        return pd.DataFrame(columns=['Date', 'Summary', 'Words', 'Used Rest Day?']) # 返回空 DataFrame


def check_submission_today(db: Session, user_email: str, check_date: date):
    """检查用户今天是否提交了有效的总结"""
    summary = db.query(Summary).filter(
        Summary.user_email == user_email,
        Summary.submission_date == check_date,
        Summary.is_rest_day == False,
        Summary.word_count >= MIN_WORD_COUNT
    ).first()
    return summary is not None

def check_if_rest_day_used(db: Session, user_email: str, check_date: date):
     """检查用户今天是否将此日标记为休息日"""
     summary = db.query(Summary).filter(
         Summary.user_email == user_email,
         Summary.submission_date == check_date,
         Summary.is_rest_day == True
     ).first()
     return summary is not None


def get_valid_submission_dates_for_week(db: Session, user_email: str, start_date: date, end_date: date):
    """获取指定周内有效提交的日期列表"""
    dates = db.query(Summary.submission_date).filter(
        Summary.user_email == user_email,
        Summary.submission_date.between(start_date, end_date),
        Summary.is_rest_day == False,
        Summary.word_count >= MIN_WORD_COUNT
    ).all()
    return [d[0] for d in dates]

def get_used_rest_dates_for_week(db: Session, user_email: str, start_date: date, end_date: date):
     """获取指定周内标记为休息日的日期列表"""
     dates = db.query(Summary.submission_date).filter(
         Summary.user_email == user_email,
         Summary.submission_date.between(start_date, end_date),
         Summary.is_rest_day == True
     ).all()
     return [d[0] for d in dates]

# 可以在这里添加其他需要的数据库操作函数
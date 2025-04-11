# db_utils.py

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, extract
from datetime import date, timedelta
import bcrypt # 用于密码处理
from models import User, Summary, SessionLocal # 从 models.py 导入
import pandas as pd # 用于返回 DataFrame

MIN_WORD_COUNT = 200 # 保持和主应用一致

# --- 数据库会话管理 ---
def get_db():
    """获取数据库会话，使用生成器模式确保关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 用户相关操作 ---
def add_user(db: Session, email: str, password: str):
    """添加新用户，对密码进行哈希处理"""
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        print(f"User {email} already exists.")
        return False
    try:
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        # 新用户默认接受提醒 (在模型中定义)
        db_user = User(email=email, password_hash=hashed_password.decode('utf-8'))
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
    if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return True
    return False

def get_user_preferences(db: Session, email: str):
    """获取指定用户的偏好设置 (是否接受提醒, 下周是否有休息日)"""
    user = db.query(User.accepts_reminders, User.has_rest_day_next_week).filter(User.email == email).first()
    if user:
        # 返回一个字典方便访问
        return {"accepts_reminders": user.accepts_reminders, "has_rest_day": user.has_rest_day_next_week}
    print(f"Preferences not found for user {email}")
    return None # 或者返回默认值字典

def update_reminder_preference(db: Session, email: str, accepts: bool):
    """更新用户是否接受邮件提醒的偏好"""
    user = db.query(User).filter(User.email == email).first()
    if user:
        try:
            user.accepts_reminders = accepts
            # 如果用户不接受提醒，则休息日规则对他们无效
            # 将 has_rest_day_next_week 设为 False 可能更清晰地表示无效状态
            if not accepts:
                user.has_rest_day_next_week = False
            db.commit()
            print(f"Updated reminder preference for {email} to {accepts}")
            return True
        except Exception as e:
            db.rollback()
            print(f"Error updating reminder preference for {email}: {e}")
            return False
    else:
        print(f"User {email} not found for preference update.")
        return False

def get_all_users_for_reminders(db: Session):
    """获取所有需要检查提醒和惩罚的用户信息 (邮箱, 是否接受提醒, 下周是否有休息日)"""
    # 返回一个包含所需信息的列表，后续在定时任务中处理
    return db.query(User.email, User.accepts_reminders, User.has_rest_day_next_week).all()

def update_rest_day_status_for_penalty(db: Session, email: str, has_rest_day: bool):
    """更新用户的下周休息日状态 (只应该由惩罚逻辑调用, 且只对接受提醒的用户有效)"""
    user = db.query(User).filter(User.email == email, User.accepts_reminders == True).first()
    if user:
        try:
            user.has_rest_day_next_week = has_rest_day
            db.commit()
            print(f"Updated rest day status via penalty for {email} to {has_rest_day}")
        except Exception as e:
            db.rollback()
            print(f"Error updating rest day status for penalty {email}: {e}")
    else:
        print(f"User {email} not found or does not accept reminders. No penalty status update.")

def can_use_rest_day(db: Session, email: str):
    """检查用户本周是否还有休息日额度 (必须接受提醒才有)"""
    user = db.query(User).filter(User.email == email).first()
    # 用户必须接受提醒，并且 has_rest_day_next_week 标志为 True
    return user and user.accepts_reminders and user.has_rest_day_next_week

# --- 总结相关操作 ---
def save_summary(db: Session, user_email: str, submission_date: date, content: str, word_count: int, is_rest_day: bool = False):
    """保存每日总结"""
    try:
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
    except Exception as e:
        db.rollback()
        print(f"Error saving summary for {user_email} on {submission_date}: {e}")
        if "UniqueViolation" in str(e) or "uq_user_submission_date_not_rest_day" in str(e):
             print("Constraint Violation: Maybe a non-rest-day summary for this date already exists?")
        return False

def get_summaries_by_user_df(db: Session, user_email: str):
    """获取指定用户的所有总结，并返回 Pandas DataFrame"""
    query = db.query(
        Summary.submission_date,
        Summary.content,
        Summary.word_count,
        Summary.is_rest_day
    ).filter(Summary.user_email == user_email).order_by(Summary.submission_date.desc())

    try:
        df = pd.read_sql_query(query.statement, query.session.bind)
        if not df.empty:
            df['Used Rest Day?'] = df['is_rest_day'].apply(lambda x: 'Yes' if x else 'No')
            df.rename(columns={'submission_date': 'Date', 'content': 'Summary', 'word_count':'Words'}, inplace=True)
            # 选择并重排最终显示的列
            return df[['Date', 'Summary', 'Words', 'Used Rest Day?']]
        else:
            return pd.DataFrame(columns=['Date', 'Summary', 'Words', 'Used Rest Day?'])
    except Exception as e:
        print(f"Error reading summaries into DataFrame: {e}")
        return pd.DataFrame(columns=['Date', 'Summary', 'Words', 'Used Rest Day?'])

def check_submission_today(db: Session, user_email: str, check_date: date):
    """检查用户今天是否提交了有效的总结 (字数达标且非休息日标记)"""
    summary = db.query(Summary.id).filter( # 只查询 ID 即可判断是否存在
        Summary.user_email == user_email,
        Summary.submission_date == check_date,
        Summary.is_rest_day == False,
        Summary.word_count >= MIN_WORD_COUNT
    ).first()
    return summary is not None

def check_if_rest_day_used(db: Session, user_email: str, check_date: date):
     """检查用户今天是否将此日标记为休息日"""
     summary = db.query(Summary.id).filter(
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
    # all() 返回的是元组列表 [(date1,), (date2,)]，需要提取第一个元素
    return [d[0] for d in dates]

def get_used_rest_dates_for_week(db: Session, user_email: str, start_date: date, end_date: date):
     """获取指定周内标记为休息日的日期列表"""
     dates = db.query(Summary.submission_date).filter(
         Summary.user_email == user_email,
         Summary.submission_date.between(start_date, end_date),
         Summary.is_rest_day == True
     ).all()
     return [d[0] for d in dates]
from datetime import date, timedelta, datetime
import db_utils # 导入新的数据库工具
import mailer
from models import SessionLocal # 导入 SessionLocal

MIN_WORD_COUNT = 200

def send_reminder_emails():
    """检查当天未提交的用户并发送提醒邮件 (晚上 10 点运行)"""
    print(f"Running reminder check at {datetime.now()}...")
    today = date.today()
    db = next(db_utils.get_db()) # 获取数据库会话
    try:
        users = db_utils.get_all_users(db) # [(email1, has_rest_day1), ...]

        for user_email, has_rest_day_flag in users:
            # 1. 检查今天是否已提交有效总结
            submitted_today = db_utils.check_submission_today(db, user_email, today)

            if submitted_today:
                print(f"User {user_email} submitted today. No reminder needed.")
                continue # 已提交，跳过

            # 2. 检查今天是否已被标记为休息日
            used_rest_day_today = db_utils.check_if_rest_day_used(db, user_email, today)
            if used_rest_day_today:
                 print(f"User {user_email} marked today as rest day. No reminder needed.")
                 continue # 已标记休息日，跳过

            # 3. 如果既没提交，也没标记为休息日，发送提醒
            print(f"User {user_email} has not submitted or marked rest day for {today}. Sending reminder...")
            subject = f"OutputTime Reminder - {today}"
            body = f"Hi {user_email.split('@')[0]},\n\nJust a friendly reminder to complete your daily summary for {today} on OutputTime!\n\nDon't forget, consistency is key.\n\nBest,\nOutputTime Bot"
            mailer.send_email(user_email, subject, body)
    finally:
        db.close() # 确保关闭数据库会话

def apply_penalties():
    """检查上周完成情况并应用惩罚 (每周日晚上或周一凌晨运行)"""
    print(f"Running penalty check for the past week at {datetime.now()}...")
    today = date.today()
    last_sunday = today - timedelta(days=today.weekday() + 1)
    last_monday = last_sunday - timedelta(days=6)
    print(f"Checking week: {last_monday} to {last_sunday}")

    db = next(db_utils.get_db()) # 获取数据库会话
    try:
        users = db_utils.get_all_users(db)

        for user_email, _ in users: # 不需要当前的休息日状态
            # 获取上周有效提交的日期列表
            valid_submission_dates = db_utils.get_valid_submission_dates_for_week(db, user_email, last_monday, last_sunday)
            # 获取上周标记为休息日的日期列表
            used_rest_dates = db_utils.get_used_rest_dates_for_week(db, user_email, last_monday, last_sunday)

            required_days = 7 # 一周总天数
            allowed_rest_days = 1 # 每周允许的休息日
            actual_submissions = len(valid_submission_dates)
            actual_rest_days_used = len(used_rest_dates)

            # 计算需要完成的天数
            days_needed_to_complete = required_days - min(actual_rest_days_used, allowed_rest_days)

            print(f"User: {user_email}, Week: {last_monday}-{last_sunday}")
            print(f"  Valid submissions: {actual_submissions}")
            print(f"  Rest days used: {actual_rest_days_used}")
            print(f"  Days needed to complete: {days_needed_to_complete}")

            # 判断是否需要惩罚
            if actual_submissions < days_needed_to_complete:
                print(f"  Penalty applied! User {user_email} loses rest day next week.")
                db_utils.update_rest_day_status(db, user_email, has_rest_day=False)
                # 发送惩罚通知邮件
                subject = "OutputTime - Rest Day Status Update"
                body = f"Hi {user_email.split('@')[0]},\n\nBased on your activity last week ({last_monday} to {last_sunday}), you did not meet the minimum requirement ({days_needed_to_complete} summaries).\n\nAs a result, your rest day for the upcoming week has been cancelled.\n\nLet's aim for better consistency this week!\n\nBest,\nOutputTime Bot"
                mailer.send_email(user_email, subject, body)
            else:
                print(f"  No penalty. User {user_email} keeps rest day next week.")
                db_utils.update_rest_day_status(db, user_email, has_rest_day=True) # 确保下周有休息日
    finally:
        db.close() # 确保关闭数据库会话

# 测试部分可以保持不变或相应更新
if __name__ == '__main__':
    print("Testing reminder function...")
    # send_reminder_emails()
    print("\nTesting penalty function...")
    # apply_penalties()
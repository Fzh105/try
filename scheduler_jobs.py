# scheduler_jobs.py

from datetime import date, timedelta, datetime, time, timezone # 导入 time 和 timezone
import db_utils # 导入新的数据库工具
import mailer   # 导入邮件模块
from models import SessionLocal # 导入 SessionLocal

MIN_WORD_COUNT = 200
REMINDER_HOUR = 22  # 提醒时间：晚上 10 点 (本地时间)
PENALTY_DAY_OF_WEEK = 'mon' # 周一执行惩罚检查 (对应服务器时间)
PENALTY_HOUR = 0    # 凌晨 0 点 (对应服务器时间)
PENALTY_MINUTE = 5  # 5 分 (对应服务器时间)

# --- 邮件提醒任务 ---
def send_reminder_emails():
    """
    检查当天未提交且接受提醒的用户，并在指定时间窗口内发送提醒邮件。
    增加时间窗口检查以防止邮件刷屏。
    """
    # 使用服务器或容器的本地时区
    local_tz = datetime.now().astimezone().tzinfo
    now = datetime.now(tz=local_tz)
    print(f"Scheduler: Reminder check triggered at {now}...")

    # *** Bug Fix: 严格的时间窗口检查 ***
    # 只在晚上 REMINDER_HOUR:00 到 REMINDER_HOUR:15 这个本地时间段内执行
    reminder_start_time = time(REMINDER_HOUR, 0, tzinfo=local_tz)
    reminder_end_time = time(REMINDER_HOUR, 15, tzinfo=local_tz) # 15分钟窗口

    if not (reminder_start_time <= now.time() <= reminder_end_time):
        print(f"Scheduler: Current time {now.time()} is outside the reminder window ({reminder_start_time}-{reminder_end_time}). Skipping email sending.")
        return # 不在指定时间，直接退出

    print(f"Scheduler: Running reminder check within window at {now}...")
    today = now.date()
    db = next(db_utils.get_db()) # 获取数据库会话
    try:
        users_to_check = db_utils.get_all_users_for_reminders(db)

        for user_email, accepts_reminders, _ in users_to_check: # 不需要 has_rest_day_flag
            # Requirement 1: 跳过不接受提醒的用户
            if not accepts_reminders:
                print(f"Scheduler: User {user_email} does not accept reminders. Skipping.")
                continue

            # 检查今天是否提交
            submitted_today = db_utils.check_submission_today(db, user_email, today)
            if submitted_today:
                print(f"Scheduler: User {user_email} submitted today. No reminder needed.")
                continue

            # 检查今天是否标记为休息日
            used_rest_day_today = db_utils.check_if_rest_day_used(db, user_email, today)
            if used_rest_day_today:
                 print(f"Scheduler: User {user_email} marked today as rest day. No reminder needed.")
                 continue

            # 如果既没提交也没标记休息日，发送邮件
            print(f"Scheduler: User {user_email} needs reminder for {today}. Sending email...")
            subject = f"OutputTime Reminder - {today}"
            body = f"Hi {user_email.split('@')[0]},\n\nJust a friendly reminder to complete your daily summary for {today} on OutputTime before the day ends!\n\nBest,\nOutputTime Bot"
            mailer.send_email(user_email, subject, body)
            # Requirement 2: 一天只发一条由时间窗口保证，若任务意外重叠执行，此逻辑保证单次执行只发一条

    except Exception as e:
         print(f"Scheduler: An error occurred during reminder check: {e}")
    finally:
        if db:
            db.close() # 确保关闭数据库会话

# --- 惩罚应用任务 ---
def apply_penalties():
    """
    检查上周完成情况并应用惩罚 (只对接受提醒的用户)。
    惩罚仅取消本周的休息日。
    """
    local_tz = datetime.now().astimezone().tzinfo
    now = datetime.now(tz=local_tz)
    print(f"Scheduler: Running penalty check for the past week at {now}...")

    # 可选：为惩罚任务也增加时间窗口，作为额外保险
    # penalty_start_time = time(PENALTY_HOUR, PENALTY_MINUTE, tzinfo=local_tz)
    # penalty_end_time = time(PENALTY_HOUR, PENALTY_MINUTE + 15, tzinfo=local_tz) # 15分钟窗口
    # if not (penalty_start_time <= now.time() <= penalty_end_time):
    #     print(f"Scheduler: Current time {now.time()} is outside the penalty window. Skipping penalty calculation.")
    #     return

    today = now.date()
    # 计算上周的开始和结束日期 (以周一为一周开始)
    last_sunday = today - timedelta(days=today.weekday() + 1)
    last_monday = last_sunday - timedelta(days=6)
    print(f"Scheduler: Checking week: {last_monday} to {last_sunday}")

    db = next(db_utils.get_db())
    try:
        users_to_check = db_utils.get_all_users_for_reminders(db)

        for user_email, accepts_reminders, _ in users_to_check: # 不需要 has_rest_day_flag
             # Requirement 1: 跳过不接受提醒的用户
             if not accepts_reminders:
                 print(f"Scheduler: User {user_email} does not accept reminders. Skipping penalty check.")
                 continue

             # 获取上周的提交和休息日数据
             valid_submission_dates = db_utils.get_valid_submission_dates_for_week(db, user_email, last_monday, last_sunday)
             used_rest_dates = db_utils.get_used_rest_dates_for_week(db, user_email, last_monday, last_sunday)

             required_days = 7       # 一周总天数
             allowed_rest_days = 1   # 每周允许的休息日
             actual_submissions = len(valid_submission_dates)
             actual_rest_days_used = len(used_rest_dates)

             # 计算上周需要完成的天数 (总天数 - 最多抵扣1个已用休息日)
             days_needed_to_complete = required_days - min(actual_rest_days_used, allowed_rest_days)

             print(f"Scheduler: User: {user_email}, Week: {last_monday}-{last_sunday}")
             print(f"  Valid submissions: {actual_submissions}")
             print(f"  Rest days used: {actual_rest_days_used}")
             print(f"  Days needed to complete: {days_needed_to_complete}")

             # 判断是否需要惩罚
             # Requirement 3: 惩罚只影响本周休息日，下周会自动恢复（除非再次未完成）
             if actual_submissions < days_needed_to_complete:
                 print(f"Scheduler: Penalty applied! User {user_email} loses rest day for the current week.")
                 # 使用特定函数更新惩罚状态
                 db_utils.update_rest_day_status_for_penalty(db, user_email, has_rest_day=False)
                 # 发送惩罚通知邮件
                 subject = "OutputTime - Rest Day Status Update"
                 body = f"Hi {user_email.split('@')[0]},\n\nBased on your activity last week ({last_monday} to {last_sunday}), you did not meet the minimum requirement ({days_needed_to_complete} summaries).\n\nAs a result, your rest day for the current week ({today} to {today + timedelta(days=6)}) has been cancelled.\n\nLet's aim for better consistency!\n\nBest,\nOutputTime Bot"
                 mailer.send_email(user_email, subject, body)
             else:
                 print(f"Scheduler: No penalty. User {user_email} keeps rest day for the current week.")
                 # 如果未受惩罚，确保当前周有休息日额度
                 db_utils.update_rest_day_status_for_penalty(db, user_email, has_rest_day=True)

    except Exception as e:
        print(f"Scheduler: An error occurred during penalty check: {e}")
    finally:
        if db:
            db.close()

# --- 用于测试的入口 (可选) ---
if __name__ == '__main__':
    print("Testing scheduler jobs...")
    # print("Testing reminder function...")
    # send_reminder_emails()
    # print("\nTesting penalty function...")
    # apply_penalties()
    print("Test finished.")
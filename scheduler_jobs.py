from datetime import date, timedelta, datetime
import database as db # 导入我们之前写的数据库模块
import mailer # 导入邮件模块

MIN_WORD_COUNT = 200

def send_reminder_emails():
    """检查当天未提交的用户并发送提醒邮件 (晚上 10 点运行)"""
    print(f"Running reminder check at {datetime.now()}...")
    today = date.today()
    users = db.get_all_users() # [(email1, has_rest_day1), ...]

    for user_email, has_rest_day_flag in users:
        # 1. 检查今天是否已提交有效总结
        submitted_today = db.check_submission_today(user_email, today)

        if submitted_today:
            print(f"User {user_email} submitted today. No reminder needed.")
            continue # 已提交，跳过

        # 2. 检查今天是否已被标记为休息日
        used_rest_day_today = db.check_if_rest_day_used(user_email, today)
        if used_rest_day_today:
             print(f"User {user_email} marked today as rest day. No reminder needed.")
             continue # 已标记休息日，跳过

        # 3. 如果既没提交，也没标记为休息日，发送提醒
        print(f"User {user_email} has not submitted or marked rest day for {today}. Sending reminder...")
        subject = f"OutputTime Reminder - {today}"
        body = f"Hi {user_email.split('@')[0]},\n\nJust a friendly reminder to complete your daily summary for {today} on OutputTime!\n\nDon't forget, consistency is key.\n\nBest,\nOutputTime Bot"
        mailer.send_email(user_email, subject, body)

def apply_penalties():
    """检查上周完成情况并应用惩罚 (每周日晚上或周一凌晨运行)"""
    print(f"Running penalty check for the past week at {datetime.now()}...")
    today = date.today()
    # 计算上周的开始和结束日期 (假设周一为一周开始)
    last_sunday = today - timedelta(days=today.weekday() + 1)
    last_monday = last_sunday - timedelta(days=6)

    print(f"Checking week: {last_monday} to {last_sunday}")

    users = db.get_all_users()

    for user_email, _ in users: # 不需要当前的休息日状态
        # 获取上周有效提交的日期列表
        valid_submission_dates = db.get_valid_submission_dates_for_week(user_email, last_monday, last_sunday)
        # 获取上周标记为休息日的日期列表
        used_rest_dates = db.get_used_rest_dates_for_week(user_email, last_monday, last_sunday)

        required_days = 7 # 一周总天数
        allowed_rest_days = 1 # 每周允许的休息日
        actual_submissions = len(valid_submission_dates)
        actual_rest_days_used = len(used_rest_dates)

        # 计算需要完成的天数 = 总天数 - 使用的休息日天数 (最多抵扣1天)
        days_needed_to_complete = required_days - min(actual_rest_days_used, allowed_rest_days)

        print(f"User: {user_email}, Week: {last_monday}-{last_sunday}")
        print(f"  Valid submissions: {actual_submissions}")
        print(f"  Rest days used: {actual_rest_days_used}")
        print(f"  Days needed to complete: {days_needed_to_complete}")


        # 判断是否需要惩罚
        if actual_submissions < days_needed_to_complete:
            print(f"  Penalty applied! User {user_email} loses rest day next week.")
            db.update_rest_day_status(user_email, has_rest_day=False)
            # 可以选择性地发送惩罚通知邮件
            subject = "OutputTime - Rest Day Status Update"
            body = f"Hi {user_email.split('@')[0]},\n\nBased on your activity last week ({last_monday} to {last_sunday}), you did not meet the minimum requirement ({days_needed_to_complete} summaries).\n\nAs a result, your rest day for the upcoming week has been cancelled.\n\nLet's aim for better consistency this week!\n\nBest,\nOutputTime Bot"
            mailer.send_email(user_email, subject, body)
        else:
            print(f"  No penalty. User {user_email} keeps rest day next week.")
            db.update_rest_day_status(user_email, has_rest_day=True) # 确保下周有休息日

if __name__ == '__main__':
    # 测试函数 (确保数据库中有测试数据)
    print("Testing reminder function...")
    # send_reminder_emails() # 取消注释以测试提醒

    print("\nTesting penalty function...")
    # apply_penalties() # 取消注释以测试惩罚
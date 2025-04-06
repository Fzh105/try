import streamlit as st
from datetime import date, datetime, timedelta
import database as db # 导入数据库模块
import scheduler_jobs # 导入定时任务函数
from apscheduler.schedulers.background import BackgroundScheduler # 使用后台调度器

MIN_WORD_COUNT = 200

# --- 应用状态管理 ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_email'] = None

# --- 数据库初始化 ---
# 确保每次启动应用时，数据库和表都存在
db.initialize_database()

# --- 定时任务调度器 ---
# 只在主进程中初始化和启动调度器，防止 Streamlit 重复运行
# (Streamlit 会在代码更改或交互时重新运行脚本)
# 使用一个简单的技巧来判断是否是首次运行或主进程
if 'scheduler_started' not in st.session_state:
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai") # 设置时区
    # 添加每日提醒任务 (每天晚上 10:00)
    scheduler.add_job(scheduler_jobs.send_reminder_emails, 'cron', hour=22, minute=0)
    # 添加每周惩罚任务 (每周一凌晨 00:05)
    scheduler.add_job(scheduler_jobs.apply_penalties, 'cron', day_of_week='mon', hour=0, minute=5)
    try:
        scheduler.start()
        st.session_state['scheduler_started'] = True
        print("Scheduler started.")
    except Exception as e:
         print(f"Error starting scheduler: {e}")
         # 在 Streamlit Cloud 等环境中，如果调度器无法启动，可能需要不同的策略
         # 例如使用外部的 cron 服务调用一个 API 端点来触发任务

# --- 登录界面 ---
def show_login_page():
    st.header("Login to OutputTime")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if db.verify_user(email, password):
            st.session_state['logged_in'] = True
            st.session_state['user_email'] = email
            st.rerun() # 重新运行脚本以显示主界面
        else:
            st.error("Invalid email or password")
    # 可选：添加简单的注册入口（如果允许用户自己注册）
    # with st.expander("Register"):
    #     reg_email = st.text_input("New Email")
    #     reg_password = st.text_input("New Password", type="password", key="reg_pass")
    #     if st.button("Register"):
    #         if db.add_user(reg_email, reg_password):
    #             st.success("Registration successful! Please login.")
    #         else:
    #             st.error("Registration failed. Email might already exist.")

# --- 主应用界面 ---
def show_main_page():
    user_email = st.session_state['user_email']
    st.sidebar.header(f"Welcome, {user_email.split('@')[0]}!")
    st.sidebar.write(f"Today: {date.today()}")

    # 显示是否有休息日额度
    can_rest = db.can_use_rest_day(user_email)
    if can_rest:
         st.sidebar.success("✅ You have a rest day available this week.")
    else:
         st.sidebar.warning("❌ No rest day available this week.")

    st.title("OutputTime - Daily Summary")

    today_str = date.today().isoformat()

    # 检查今天是否已提交
    submitted_today = db.check_submission_today(user_email, today_str)
    rest_day_used_today = db.check_if_rest_day_used(user_email, today_str)

    if submitted_today:
        st.success(f"Great job! You've already submitted your summary for {today_str}.")
    elif rest_day_used_today:
         st.info(f"You've marked today ({today_str}) as your rest day.")
    else:
        st.subheader(f"Write your summary for {today_str}")
        summary_text = st.text_area("Minimum 200 words:", height=250)
        word_count = len(summary_text.split())
        st.write(f"Word count: {word_count}")

        use_rest_day = False
        if can_rest:
             use_rest_day = st.checkbox(f"Use today ({today_str}) as my rest day?")

        submit_button = st.button("Submit Summary")

        if submit_button:
            if use_rest_day:
                # 标记为休息日
                if db.save_summary(user_email, today_str, "REST DAY", 0, is_rest_day=True):
                     st.success("Today marked as rest day!")
                     st.rerun() # 刷新页面
                else:
                     st.error("Failed to mark rest day. Maybe you already submitted?")
            elif word_count >= MIN_WORD_COUNT:
                # 提交有效总结
                if db.save_summary(user_email, today_str, summary_text, word_count, is_rest_day=False):
                    st.success("Summary submitted successfully!")
                    st.rerun() # 刷新页面
                else:
                    st.error("Failed to submit summary. Maybe you already submitted today?")
            else:
                st.warning(f"Summary must be at least {MIN_WORD_COUNT} words long (currently {word_count}).")

    st.divider() # 分割线

    # --- 显示历史记录 ---
    st.subheader("Your Summary History")
    history_df = db.get_summaries_by_user(user_email)
    if not history_df.empty:
        st.dataframe(history_df, use_container_width=True)
    else:
        st.write("No summaries submitted yet.")

    # --- 登出按钮 ---
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.session_state['user_email'] = None
        st.session_state.pop('scheduler_started', None) # 允许下次登录时重新启动调度器 (可选)
        st.rerun()


# --- 主逻辑：根据登录状态显示不同页面 ---
if st.session_state['logged_in']:
    show_main_page()
else:
    show_login_page()

# --- 页脚 (可选) ---
st.markdown("---")
st.caption("OutputTime v0.1")
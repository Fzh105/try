import streamlit as st
from datetime import date, datetime, timedelta
import db_utils # 使用新的数据库工具
import scheduler_jobs
from models import create_tables # 导入创建表的函数
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd # 确保导入 pandas

MIN_WORD_COUNT = 200

# --- 数据库初始化 ---
# 在应用启动时确保数据库表已创建
# 注意：在 Streamlit Cloud 上，这通常只在容器首次启动时运行
try:
    create_tables()
except Exception as e:
     # 如果数据库连接失败 (例如 Secrets 未配置)，这里会报错
     st.error(f"Database connection failed: {e}. Please check secrets configuration.")
     st.stop() # 阻止应用继续运行

# --- 应用状态管理 ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_email'] = None
    st.session_state['page'] = 'Login' # 新增页面状态

# --- 定时任务调度器 (保持不变) ---
if 'scheduler_started' not in st.session_state:
    # ... (调度器初始化和启动代码，和之前一样) ...
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai") # 设置时区
    scheduler.add_job(scheduler_jobs.send_reminder_emails, 'cron', hour=22, minute=0)
    scheduler.add_job(scheduler_jobs.apply_penalties, 'cron', day_of_week='mon', hour=0, minute=5)
    try:
        scheduler.start()
        st.session_state['scheduler_started'] = True
        print("Scheduler started.")
    except Exception as e:
         print(f"Error starting scheduler: {e}")
         # 提醒：在 Streamlit Cloud 上调度器可能不稳定


# --- 登录页面 ---
def show_login_page():
    st.header("Login to OutputTime")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            db = next(db_utils.get_db())
            try:
                if db_utils.verify_user(db, email, password):
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = email
                    st.session_state['page'] = 'Main' # 切换到主页
                    st.rerun()
                else:
                    st.error("Invalid email or password")
            finally:
                db.close()

    if st.button("Don't have an account? Register"):
        st.session_state['page'] = 'Register'
        st.rerun()

# --- 注册页面 ---
def show_register_page():
    st.header("Register for OutputTime")
    with st.form("register_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Register")
        if submitted:
            if password != confirm_password:
                st.error("Passwords do not match!")
            elif not email or not password:
                 st.error("Email and password cannot be empty!")
            else:
                db = next(db_utils.get_db())
                try:
                    if db_utils.add_user(db, email, password):
                        st.success("Registration successful! Please login.")
                        st.session_state['page'] = 'Login' # 跳转回登录页
                        st.rerun()
                    else:
                        # add_user 函数内部会打印错误，这里给用户通用提示
                        st.error("Registration failed. Email might already exist.")
                finally:
                    db.close()

    if st.button("Already have an account? Login"):
        st.session_state['page'] = 'Login'
        st.rerun()


# --- 主应用界面 ---
def show_main_page():
    user_email = st.session_state['user_email']
    db = next(db_utils.get_db())
    try:
        st.sidebar.header(f"Welcome, {user_email.split('@')[0]}!")
        st.sidebar.write(f"Today: {date.today()}")

        # 显示是否有休息日额度
        can_rest = db_utils.can_use_rest_day(db, user_email)
        if can_rest:
             st.sidebar.success("✅ You have a rest day available this week.")
        else:
             st.sidebar.warning("❌ No rest day available this week.")

        st.title("OutputTime - Daily Summary")
        today_str = date.today() # 直接用 date 对象

        # 检查今天是否已提交
        submitted_today = db_utils.check_submission_today(db, user_email, today_str)
        rest_day_used_today = db_utils.check_if_rest_day_used(db, user_email, today_str)

        if submitted_today:
            st.success(f"Great job! You've already submitted your summary for {today_str}.")
        elif rest_day_used_today:
             st.info(f"You've marked today ({today_str}) as your rest day.")
        else:
            st.subheader(f"Write your summary for {today_str}")
            with st.form(f"summary_form_{today_str}"): # 使用 form 避免多控件交互触发 rerun
                 summary_text = st.text_area("Minimum 200 words:", height=250, key=f"summary_text_{today_str}")
                 word_count = len(summary_text.split())
                 st.write(f"Word count: {word_count}")

                 use_rest_day = False
                 if can_rest:
                      use_rest_day = st.checkbox(f"Use today ({today_str}) as my rest day?", key=f"rest_day_{today_str}")

                 submit_button = st.form_submit_button("Submit Summary")

                 if submit_button:
                     if use_rest_day:
                         # 标记为休息日
                         if db_utils.save_summary(db, user_email, today_str, "REST DAY", 0, is_rest_day=True):
                              st.success("Today marked as rest day!")
                              st.rerun()
                         else:
                              st.error("Failed to mark rest day. Maybe you already submitted today?")
                     elif word_count >= MIN_WORD_COUNT:
                         # 提交有效总结
                         if db_utils.save_summary(db, user_email, today_str, summary_text, word_count, is_rest_day=False):
                             st.success("Summary submitted successfully!")
                             st.rerun()
                         else:
                             st.error("Failed to submit summary. Maybe you already submitted today?")
                     else:
                         st.warning(f"Summary must be at least {MIN_WORD_COUNT} words long (currently {word_count}).")

        st.divider()

        # --- 显示历史记录 ---
        st.subheader("Your Summary History")
        history_df = db_utils.get_summaries_by_user_df(db, user_email) # 使用新的 DataFrame 函数
        if not history_df.empty:
            st.dataframe(history_df, use_container_width=True)
        else:
            st.write("No summaries submitted yet.")

        # --- 登出按钮 ---
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.session_state['user_email'] = None
            st.session_state['page'] = 'Login'
            st.session_state.pop('scheduler_started', None) # 可选：允许下次登录时重新启动调度器
            st.rerun()
    finally:
        db.close() # 确保关闭数据库会话


# --- 页面路由逻辑 ---
if not st.session_state.get('logged_in', False):
    if st.session_state.get('page', 'Login') == 'Register':
        show_register_page()
    else:
        show_login_page()
else:
    show_main_page()


# --- 页脚 (可选) ---
st.markdown("---")
st.caption("OutputTime v0.2 - Cloud Ready")
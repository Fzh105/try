# app.py

import streamlit as st
from datetime import date, datetime, timedelta
# 直接导入 SessionLocal 用于创建会话
from models import create_tables, SessionLocal
# 仍然需要导入 db_utils 来使用其中的数据库操作函数
import db_utils
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import time
import pytz # 用于处理时区

MIN_WORD_COUNT = 200
DEFAULT_TIMEZONE = "Asia/Shanghai" # 时区设置

# --- 数据库初始化 ---
try:
    # 确保应用启动时数据库表结构存在
    create_tables()
except Exception as e:
     # 如果数据库连接失败（例如 Secrets 错误），应用将停止
     st.error(f"Database connection/setup failed: {e}. Please check secrets configuration and database status.")
     st.stop()

# --- 应用状态管理 ---
# 初始化 session_state 中的变量
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_email'] = None
    st.session_state['page'] = 'Login' # 控制显示哪个页面

# --- 定时任务调度器 ---
# 确保调度器只启动一次
if 'scheduler_started' not in st.session_state:
    try:
        # 创建后台调度器并设置时区
        scheduler = BackgroundScheduler(timezone=DEFAULT_TIMEZONE)
        # 从 scheduler_jobs 导入任务函数和配置
        from scheduler_jobs import send_reminder_emails, apply_penalties, REMINDER_HOUR, PENALTY_DAY_OF_WEEK, PENALTY_HOUR, PENALTY_MINUTE
        # 添加定时任务，增加宽限时间防止因小延迟错过执行
        scheduler.add_job(send_reminder_emails, 'cron', hour=REMINDER_HOUR, minute=0, misfire_grace_time=600)
        scheduler.add_job(apply_penalties, 'cron', day_of_week=PENALTY_DAY_OF_WEEK, hour=PENALTY_HOUR, minute=PENALTY_MINUTE, misfire_grace_time=600)
        # 启动调度器
        scheduler.start()
        st.session_state['scheduler_started'] = True
        print(f"Scheduler started with timezone {DEFAULT_TIMEZONE}.")
    except Exception as e:
         # 如果调度器启动失败，打印错误，但不停止应用
         print(f"Error starting scheduler: {e}. Timed reminders/penalties might not work.")


# --- 登录页面 ---
def show_login_page():
    st.header("Login to OutputTime")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            # 直接创建和关闭 Session
            db = SessionLocal()
            try:
                # 使用 db_utils 中的函数验证用户，传入 db 会话
                if db_utils.verify_user(db, email, password):
                    # 登录成功，更新 session_state
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = email
                    st.session_state['page'] = 'Main'
                    st.rerun() # <-- 修改处
                else:
                    st.error("Invalid email or password")
            finally:
                db.close() # 确保会话被关闭

    # 跳转到注册页面的按钮
    if st.button("Don't have an account? Register"):
        st.session_state['page'] = 'Register'
        st.rerun() # <-- 修改处

# --- 注册页面 ---
def show_register_page():
    st.header("Register for OutputTime")
    with st.form("register_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Register")
        if submitted:
            # 基本的输入验证
            if password != confirm_password:
                st.error("Passwords do not match!")
            elif not email or not password:
                 st.error("Email and password cannot be empty!")
            else:
                # 直接创建和关闭 Session
                db = SessionLocal()
                try:
                    # 使用 db_utils 中的函数添加用户，传入 db 会话
                    if db_utils.add_user(db, email, password):
                        st.success("Registration successful! Please login.")
                        st.info("Reminders are active by default. You can change this in Settings after logging in.")
                        st.session_state['page'] = 'Login' # 跳转回登录页
                        st.rerun() # <-- 修改处
                    else:
                        # add_user 内部会打印具体错误，这里给通用提示
                        st.error("Registration failed. Email might already exist.")
                finally:
                    db.close() # 确保会话被关闭

    # 跳转回登录页面的按钮
    if st.button("Already have an account? Login"):
        st.session_state['page'] = 'Login'
        st.rerun() # <-- 修改处


# --- 设置页面 ---
def show_settings_page():
    st.header("Settings")
    user_email = st.session_state['user_email']

    # 直接创建和关闭 Session
    db = SessionLocal()
    try:
        # 使用 db_utils 获取用户偏好，传入 db 会话
        prefs = db_utils.get_user_preferences(db, user_email)

        # 如果无法加载偏好设置，显示错误并退出
        if prefs is None:
            st.error("Could not load your preferences. Please try again later.")
            if st.button("Back to Main"):
                st.session_state['page'] = 'Main'
                st.rerun() # <-- 修改处
            return

        st.subheader("Email Reminders & Rules")
        current_preference = prefs['accepts_reminders']

        # 使用 Radio 按钮让用户选择是否接受提醒
        new_preference = st.radio(
            "Receive daily email reminders and participate in the rest day/penalty system?",
            options=[True, False], # 选项值
            format_func=lambda x: "Yes, activate reminders and rules" if x else "No, deactivate reminders and rules", # 选项显示文本
            index=0 if current_preference else 1, # 根据当前值设置默认选中
            key='reminder_pref_radio' # 给控件一个唯一的 key
        )

        # 只有当用户的选择与当前设置不同时，才显示“保存”按钮
        if new_preference != current_preference:
            if st.button("Save Preference Change"):
                 # 使用 db_utils 更新偏好，传入 db 会话
                 if db_utils.update_reminder_preference(db, user_email, new_preference):
                     st.success("Preference updated successfully!")
                     time.sleep(1.5) # 等待用户看到成功消息
                     st.rerun() # <-- 修改处
                 else:
                     st.error("Failed to update preference. Please try again.")
        else:
             # 如果设置未改变，可以禁用保存按钮或不显示
             st.button("Save Preference Change", disabled=True)

        # 根据最终确定的（可能已更新的）偏好显示提示信息
        if new_preference:
            st.info("Reminders and the rest day system are currently set to **Active**.")
        else:
            st.warning("Reminders and the rest day system are currently set to **Inactive**. You will not receive reminder emails, and the rest day feature/penalty will not apply to you.")

    finally:
        db.close() # 确保会话被关闭

    # 返回主页按钮
    st.divider()
    if st.button("Back to Main Page"):
        st.session_state['page'] = 'Main'
        st.rerun() # <-- 修改处


# --- 主应用界面 ---
def show_main_page():
    user_email = st.session_state['user_email']

    # 直接创建和关闭 Session
    db = SessionLocal()
    try:
        # 获取用户偏好
        prefs = db_utils.get_user_preferences(db, user_email)
        if not prefs:
             st.error("Could not load user data. Please try logging out and back in.")
             if st.button("Logout"):
                  st.session_state['logged_in'] = False
                  st.session_state['user_email'] = None
                  st.session_state['page'] = 'Login'
                  st.session_state.pop('scheduler_started', None)
                  st.rerun() # <-- 修改处
             return

        accepts_reminders = prefs['accepts_reminders']

        # --- 侧边栏 ---
        st.sidebar.header(f"Welcome, {user_email.split('@')[0]}!")
        # 设置时区并显示本地日期
        try:
            local_tz = pytz.timezone(DEFAULT_TIMEZONE)
        except pytz.UnknownTimeZoneError:
            local_tz = pytz.utc # 如果时区无效，使用 UTC 作为备用
            st.sidebar.warning(f"Timezone '{DEFAULT_TIMEZONE}' not found, using UTC.")
        today_local = datetime.now(local_tz).date()
        st.sidebar.write(f"Today ({local_tz}): {today_local}")


        # 根据偏好显示休息日和提醒状态
        if accepts_reminders:
            can_rest_this_week = db_utils.can_use_rest_day(db, user_email)
            if can_rest_this_week:
                 st.sidebar.success("✅ Rest day available this week.")
            else:
                 st.sidebar.warning("❌ No rest day available this week.")
            st.sidebar.info("Reminders & Rules: Active")
        else:
             st.sidebar.info("Reminders & Rules: Inactive")
             st.sidebar.caption("Activate in Settings to use rest days.")

        # 设置按钮
        if st.sidebar.button("⚙️ Settings"):
             st.session_state['page'] = 'Settings'
             st.rerun() # <-- 修改处

        st.sidebar.divider()
        # 登出按钮
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.session_state['user_email'] = None
            st.session_state['page'] = 'Login'
            st.session_state.pop('scheduler_started', None) # 移除调度器状态
            st.rerun() # <-- 修改处


        # --- 主内容区 ---
        st.title("OutputTime - Daily Summary")
        # 使用服务器/容器的日期进行数据库查询和保存
        today_for_summary = date.today()

        # 检查今天的提交状态
        submitted_today = db_utils.check_submission_today(db, user_email, today_for_summary)
        rest_day_used_today = db_utils.check_if_rest_day_used(db, user_email, today_for_summary)

        # 根据提交状态显示不同内容
        if submitted_today:
            st.success(f"Great job! You've already submitted your summary for {today_for_summary}.")
        elif rest_day_used_today:
             st.info(f"You've marked today ({today_for_summary}) as your rest day.")
        else:
            # 显示提交表单
            st.subheader(f"Write your summary for {today_for_summary}")
            with st.form(f"summary_form_{today_for_summary}", clear_on_submit=True):
                 summary_text = st.text_area("Minimum 200 words:", height=250, key=f"summary_text_{today_for_summary}")
                 word_count = len(summary_text.split())
                 st.caption(f"Word count: {word_count}")

                 use_rest_day = False
                 can_rest_today_check = False # 初始化变量
                 # 仅在用户接受提醒时处理休息日逻辑
                 if accepts_reminders:
                     can_rest_today_check = db_utils.can_use_rest_day(db, user_email)
                     if can_rest_today_check:
                          use_rest_day = st.checkbox(f"Use today ({today_for_summary}) as my rest day?", key=f"rest_day_{today_for_summary}")
                     else:
                          st.caption("Rest day not available for use this week.")
                 else:
                      st.caption("Rest day feature is inactive as reminders are turned off.")

                 # 提交按钮
                 submit_button = st.form_submit_button("Submit Summary")

                 # 处理表单提交
                 if submit_button:
                     # 情况1：使用休息日（必须接受提醒、勾选了选项、且有额度）
                     if accepts_reminders and use_rest_day and can_rest_today_check: # 双重检查额度
                         if db_utils.save_summary(db, user_email, today_for_summary, "REST DAY", 0, is_rest_day=True):
                              st.success("Today marked as rest day!")
                              time.sleep(1) # 短暂显示成功消息
                              st.rerun() # <-- 修改处
                         else:
                              st.error("Failed to mark rest day. Maybe you already submitted today?")
                     # 情况2：正常提交总结（字数达标）
                     elif word_count >= MIN_WORD_COUNT:
                         if db_utils.save_summary(db, user_email, today_for_summary, summary_text, word_count, is_rest_day=False):
                             st.success("Summary submitted successfully!")
                             time.sleep(1)
                             st.rerun() # <-- 修改处
                         else:
                             st.error("Failed to submit summary. Maybe you already submitted today?")
                     # 情况3：未勾选休息日且字数不够
                     elif not use_rest_day:
                         st.warning(f"Summary must be at least {MIN_WORD_COUNT} words long (currently {word_count}).")
                     # 其他情况（例如勾选了休息日但没额度）可以不处理或给出提示

        st.divider()

        # --- 显示历史记录 ---
        st.subheader("Your Summary History")
        # 使用 db_utils 获取 DataFrame
        history_df = db_utils.get_summaries_by_user_df(db, user_email)
        if not history_df.empty:
            # 使用 st.dataframe 展示，可以启用列配置等高级功能
            st.dataframe(history_df, use_container_width=True, hide_index=True)
        else:
            st.write("No summaries submitted yet.")

    finally:
        db.close() # 确保在函数结束时关闭会话


# --- 页面路由逻辑 ---
# 根据 session_state 中的 page 值决定显示哪个函数定义的页面
if not st.session_state.get('logged_in', False):
    # 未登录状态
    if st.session_state.get('page', 'Login') == 'Register':
        show_register_page()
    else: # 默认显示登录页
        show_login_page()
else:
    # 已登录状态
    if st.session_state.get('page', 'Main') == 'Settings':
        show_settings_page()
    else: # 默认显示主页 (Main)
        # 确保 page 状态明确，如果不是 Settings，则设为 Main
        st.session_state['page'] = 'Main'
        show_main_page()


# --- 页脚 ---
st.markdown("---")
st.caption("OutputTime v0.3 - Rerun Fix")
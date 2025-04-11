# app.py

import streamlit as st
from datetime import date, datetime, timedelta
import db_utils # 使用更新后的数据库工具
from models import create_tables # 导入创建表的函数
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd # 确保导入 pandas
import time # 用于可能的延迟
import pytz # 用于处理时区

MIN_WORD_COUNT = 200
DEFAULT_TIMEZONE = "Asia/Shanghai" # 或者选择一个适合你用户的时区

# --- 数据库初始化 ---
try:
    create_tables()
except Exception as e:
     st.error(f"Database connection failed: {e}. Please check secrets configuration and database status.")
     st.stop()

# --- 应用状态管理 ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_email'] = None
    st.session_state['page'] = 'Login' # 页面状态: Login, Register, Main, Settings

# --- 定时任务调度器 ---
# 确保只初始化一次，并设置合适的时区
if 'scheduler_started' not in st.session_state:
    try:
        scheduler = BackgroundScheduler(timezone=DEFAULT_TIMEZONE)
        from scheduler_jobs import send_reminder_emails, apply_penalties, REMINDER_HOUR, PENALTY_DAY_OF_WEEK, PENALTY_HOUR, PENALTY_MINUTE
        # 添加任务，增加 misfire_grace_time 防止任务因短暂延迟而丢失
        scheduler.add_job(send_reminder_emails, 'cron', hour=REMINDER_HOUR, minute=0, misfire_grace_time=600)
        scheduler.add_job(apply_penalties, 'cron', day_of_week=PENALTY_DAY_OF_WEEK, hour=PENALTY_HOUR, minute=PENALTY_MINUTE, misfire_grace_time=600)
        scheduler.start()
        st.session_state['scheduler_started'] = True
        print(f"Scheduler started with timezone {DEFAULT_TIMEZONE}.")
    except Exception as e:
         print(f"Error starting scheduler: {e}. Timed reminders/penalties might not work.")
         # 不停止应用，但后台任务可能失败


# --- 登录页面 ---
def show_login_page():
    st.header("Login to OutputTime")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            # 使用 with 语句管理数据库会话
            with db_utils.get_db() as db:
                if db_utils.verify_user(db, email, password):
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = email
                    st.session_state['page'] = 'Main'
                    st.rerun()
                else:
                    st.error("Invalid email or password")

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
            # TODO: 可以加更复杂的密码策略检查
            else:
                with db_utils.get_db() as db:
                    if db_utils.add_user(db, email, password):
                        st.success("Registration successful! Please login.")
                        st.info("Reminders are active by default. You can change this in Settings after logging in.")
                        st.session_state['page'] = 'Login'
                        st.experimental_rerun() # 使用 rerun 的新方式
                    else:
                        st.error("Registration failed. Email might already exist.")

    if st.button("Already have an account? Login"):
        st.session_state['page'] = 'Login'
        st.experimental_rerun()


# --- 设置页面 ---
def show_settings_page():
    st.header("Settings")
    user_email = st.session_state['user_email']

    with db_utils.get_db() as db:
        prefs = db_utils.get_user_preferences(db, user_email)

        if prefs is None:
            st.error("Could not load your preferences. Please try again later.")
            if st.button("Back to Main"):
                st.session_state['page'] = 'Main'
                st.experimental_rerun()
            return # 无法加载偏好，退出函数

        st.subheader("Email Reminders & Rules")
        current_preference = prefs['accepts_reminders']

        # 使用 radio 提供清晰选项
        new_preference = st.radio(
            "Receive daily email reminders and participate in the rest day/penalty system?",
            options=[True, False],
            format_func=lambda x: "Yes, activate reminders and rules" if x else "No, deactivate reminders and rules",
            index=0 if current_preference else 1, # 根据当前值设置默认选中项
            key='reminder_pref_radio'
        )

        # 只有当选项改变时才显示保存按钮，避免误操作
        if new_preference != current_preference:
            if st.button("Save Preference Change"):
                 if db_utils.update_reminder_preference(db, user_email, new_preference):
                     st.success("Preference updated successfully!")
                     # 等待一下让用户看到消息，然后刷新
                     time.sleep(1.5)
                     st.experimental_rerun()
                 else:
                     st.error("Failed to update preference. Please try again.")
        else:
             # 如果没变化，可以不显示按钮，或者显示一个禁用的按钮
             st.button("Save Preference Change", disabled=True)


        if new_preference:
            st.info("Reminders and the rest day system are currently set to **Active**.")
        else:
            st.warning("Reminders and the rest day system are currently set to **Inactive**. You will not receive reminder emails, and the rest day feature/penalty will not apply to you.")


    # 返回主页按钮
    st.divider()
    if st.button("Back to Main Page"):
        st.session_state['page'] = 'Main'
        st.experimental_rerun()


# --- 主应用界面 ---
def show_main_page():
    user_email = st.session_state['user_email']

    with db_utils.get_db() as db:
        # 获取用户偏好，这是控制显示的关键
        prefs = db_utils.get_user_preferences(db, user_email)
        if not prefs:
             st.error("Could not load user data. Please try logging out and back in.")
             # 可以提供登出按钮
             if st.button("Logout"):
                  st.session_state['logged_in'] = False
                  # ... (其余登出逻辑)
                  st.experimental_rerun()
             return # 停止渲染

        accepts_reminders = prefs['accepts_reminders']

        # --- 侧边栏 ---
        st.sidebar.header(f"Welcome, {user_email.split('@')[0]}!")
        # 使用本地时区显示日期
        local_tz = pytz.timezone(DEFAULT_TIMEZONE) # 或让用户选择
        today_local = datetime.now(local_tz).date()
        st.sidebar.write(f"Today: {today_local}")

        # 根据偏好显示侧边栏信息
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
             st.experimental_rerun()

        st.sidebar.divider()
        # 登出按钮
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.session_state['user_email'] = None
            st.session_state['page'] = 'Login'
            st.session_state.pop('scheduler_started', None) # 移除调度器状态
            st.experimental_rerun()


        # --- 主内容区 ---
        st.title("OutputTime - Daily Summary")
        today_for_summary = date.today() # 使用服务器/容器日期进行数据库操作

        submitted_today = db_utils.check_submission_today(db, user_email, today_for_summary)
        rest_day_used_today = db_utils.check_if_rest_day_used(db, user_email, today_for_summary)

        if submitted_today:
            st.success(f"Great job! You've already submitted your summary for {today_for_summary}.")
        elif rest_day_used_today:
             st.info(f"You've marked today ({today_for_summary}) as your rest day.")
        else:
            # 未提交也未标记休息日，显示提交表单
            st.subheader(f"Write your summary for {today_for_summary}")
            # 使用 key 来确保表单状态正确管理
            with st.form(f"summary_form_{today_for_summary}", clear_on_submit=True):
                 summary_text = st.text_area("Minimum 200 words:", height=250, key=f"summary_text_{today_for_summary}")
                 word_count = len(summary_text.split())
                 st.caption(f"Word count: {word_count}") # 使用 caption 更低调

                 use_rest_day = False
                 # 仅当用户接受提醒时，才显示并处理休息日选项
                 if accepts_reminders:
                     can_rest_today_check = db_utils.can_use_rest_day(db, user_email)
                     if can_rest_today_check:
                          use_rest_day = st.checkbox(f"Use today ({today_for_summary}) as my rest day?", key=f"rest_day_{today_for_summary}")
                     else:
                          st.caption("Rest day not available for use this week.")
                 else:
                      # 用户不接受提醒，明确告知休息日功能无效
                      st.caption("Rest day feature is inactive as reminders are turned off.")


                 submit_button = st.form_submit_button("Submit Summary")

                 if submit_button:
                     # 仅当用户接受提醒且勾选了休息日才处理
                     if accepts_reminders and use_rest_day and can_rest_today_check: # 双重检查额度
                         if db_utils.save_summary(db, user_email, today_for_summary, "REST DAY", 0, is_rest_day=True):
                              st.success("Today marked as rest day!")
                              time.sleep(1) # 短暂显示成功消息
                              st.experimental_rerun()
                         else:
                              st.error("Failed to mark rest day. Maybe you already submitted today?")
                     # 处理正常提交
                     elif word_count >= MIN_WORD_COUNT:
                         if db_utils.save_summary(db, user_email, today_for_summary, summary_text, word_count, is_rest_day=False):
                             st.success("Summary submitted successfully!")
                             time.sleep(1)
                             st.experimental_rerun()
                         else:
                             st.error("Failed to submit summary. Maybe you already submitted today?")
                     # 如果没勾选休息日且字数不够
                     elif not use_rest_day:
                         st.warning(f"Summary must be at least {MIN_WORD_COUNT} words long (currently {word_count}).")
                     # 如果勾选了休息日但不满足条件 (比如额度没了)，可以不提示或给特定提示
                     # else: pass

        st.divider()

        # --- 显示历史记录 ---
        st.subheader("Your Summary History")
        # 从数据库获取最新的历史记录 DataFrame
        history_df = db_utils.get_summaries_by_user_df(db, user_email)
        if not history_df.empty:
            # 使用 st.dataframe 展示，可以启用列配置等高级功能
            st.dataframe(history_df, use_container_width=True, hide_index=True)
        else:
            st.write("No summaries submitted yet.")


# --- 页面路由逻辑 ---
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
st.caption("OutputTime v0.3 - Preferences & BugFix")
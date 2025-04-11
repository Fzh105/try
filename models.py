# models.py

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Date, Boolean,
    ForeignKey, Index
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
import streamlit as st

# --- 数据库连接 (保持不变) ---
DATABASE_URL = st.secrets.get("database", {}).get("url", "postgresql://user:password@host:port/db_needs_configuration")
if DATABASE_URL == "postgresql://user:password@host:port/db_needs_configuration":
    print("警告：数据库 URL 未在 secrets 中配置，将使用默认/无效值。")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 数据模型定义 (User 和 Summary 类保持不变，包含 accepts_reminders 列) ---
class User(Base):
    __tablename__ = "users"
    email = Column(String, primary_key=True, index=True)
    password_hash = Column(String, nullable=False)
    has_rest_day_next_week = Column(Boolean, default=True, nullable=False)
    accepts_reminders = Column(Boolean, default=True, nullable=False) # 确保新模型包含此列
    summaries = relationship("Summary", back_populates="user")

class Summary(Base):
    __tablename__ = "summaries"
    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, ForeignKey("users.email"), nullable=False, index=True)
    submission_date = Column(Date, nullable=False, index=True)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    is_rest_day = Column(Boolean, default=False, nullable=False)
    user = relationship("User", back_populates="summaries")
    __table_args__ = (
        Index(
            'uq_user_submission_date_not_rest_day',
            'user_email',
            'submission_date',
            unique=True,
            postgresql_where=(is_rest_day == False)
        ),
    )

# --- 创建数据库表的函数 (保持不变) ---
def create_tables():
    """在数据库中创建所有定义的表 (如果它们不存在)"""
    # 这个函数只负责创建，不负责删除
    try:
        Base.metadata.create_all(bind=engine)
        print("数据库表已检查/创建成功。")
    except Exception as e:
        print(f"创建数据库表时出错: {e}")
        # 注意：如果表已存在但结构不同，create_all 通常不会修改它们

# --- 修改执行入口 ---
if __name__ == "__main__":
    # 当直接运行 python models.py 时执行以下操作
    print("警告：即将执行数据库清空和重新初始化操作！")
    print("这将删除 users 和 summaries 表中的所有数据。")
    confirm = input("输入 'yes' 以确认执行此操作: ")

    if confirm.lower() == 'yes':
        print("正在尝试连接数据库...")
        try:
            # 1. 删除所有由 Base.metadata 定义的表
            print("正在尝试删除旧表...")
            Base.metadata.drop_all(bind=engine)
            print("旧表删除成功（如果存在）。")

            # 2. 根据当前模型创建新表
            print("正在尝试创建新表...")
            create_tables() # 调用上面的创建函数
            print("数据库初始化完成。")

        except Exception as e:
            print(f"数据库操作失败: {e}")
            print("请检查数据库连接 URL 和服务状态。")
    else:
        print("操作已取消。数据库未作更改。")
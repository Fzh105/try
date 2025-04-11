# models.py

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Date, Boolean,
    ForeignKey, Index # 确保导入 Index
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
import streamlit as st # 用于获取数据库连接字符串

# --- 数据库连接 ---
# 从 Streamlit Secrets 获取数据库连接 URI
DATABASE_URL = st.secrets.get("database", {}).get("url", "postgresql://user:password@host:port/db_needs_configuration")
if DATABASE_URL == "postgresql://user:password@host:port/db_needs_configuration":
    print("警告：数据库 URL 未在 secrets 中配置，将使用默认/无效值。")

# SQLAlchemy 配置
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 数据模型定义 ---
class User(Base):
    __tablename__ = "users"

    email = Column(String, primary_key=True, index=True)
    password_hash = Column(String, nullable=False)
    has_rest_day_next_week = Column(Boolean, default=True, nullable=False)
    # 新增字段：用户是否接受邮件提醒和参与规则，默认为 True
    accepts_reminders = Column(Boolean, default=True, nullable=False)

    summaries = relationship("Summary", back_populates="user") # 用户与总结的一对多关系

class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, ForeignKey("users.email"), nullable=False, index=True)
    submission_date = Column(Date, nullable=False, index=True)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    # is_rest_day 列对象将在索引条件中被引用
    is_rest_day = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="summaries") # 总结与用户的多对一关系

    # 使用 Index 实现部分唯一约束：只在 is_rest_day 为 False 时，
    # user_email 和 submission_date 的组合必须唯一。
    __table_args__ = (
        Index(
            'uq_user_submission_date_not_rest_day', # 索引名称
            'user_email',                           # 列名
            'submission_date',                      # 列名
            unique=True,                            # 唯一索引
            postgresql_where=(is_rest_day == False) # PostgreSQL 特定条件
        ),
    )

# --- 创建数据库表的函数 ---
def create_tables():
    """在数据库中创建所有定义的表 (如果它们不存在)"""
    try:
        with engine.connect() as connection:
            print("数据库连接成功。")
        Base.metadata.create_all(bind=engine)
        print("数据库表已检查/创建成功。")
    except Exception as e:
        print(f"数据库操作失败: {e}")
        print("请检查数据库连接 URL 和服务状态。")

if __name__ == "__main__":
    # 首次运行此脚本来创建数据库表
    print("正在初始化数据库表...")
    create_tables()
    print("数据库初始化脚本执行完毕。")
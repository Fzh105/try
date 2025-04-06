# models.py

# 确保导入了 Index 类
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Date, Boolean,
    ForeignKey, UniqueConstraint, Index # <-- 导入 Index
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
import streamlit as st # 用于获取数据库连接字符串

# --- 数据库连接 ---
# 从 Streamlit Secrets 获取数据库连接 URI
# 提供一个默认值或明确提示，以防 secrets 未配置
DATABASE_URL = st.secrets.get("database", {}).get("url", "postgresql://user:password@host:port/db_needs_configuration")
if DATABASE_URL == "postgresql://user:password@host:port/db_needs_configuration":
    # 在实际应用中，如果未配置 secrets，可能需要更健壮的处理，例如抛出错误或使用备用配置
    print("警告：数据库 URL 未在 secrets 中配置，将使用默认/无效值。")
    # 对于本地运行 `python models.py`，如果 .streamlit/secrets.toml 不存在或未配置，也会看到此警告

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

    summaries = relationship("Summary", back_populates="user") # 建立用户和总结的一对多关系

class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, ForeignKey("users.email"), nullable=False, index=True)
    submission_date = Column(Date, nullable=False, index=True)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    # 这是我们将在索引条件中引用的列对象
    is_rest_day = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="summaries") # 建立总结和用户的多对一关系

    # --- 修改后的 __table_args__ ---
    # 使用 Index 实现部分唯一约束：只在 is_rest_day 为 False 时，
    # user_email 和 submission_date 的组合必须唯一。
    __table_args__ = (
        Index(
            'uq_user_submission_date_not_rest_day', # 给索引起一个描述性的名字
            'user_email',                           # 列名，字符串形式
            'submission_date',                      # 列名，字符串形式
            unique=True,                            # 设置为唯一索引
            # 在条件中使用 Column 对象 'is_rest_day'
            postgresql_where=(is_rest_day == False)
        ),
        # 如果需要，可以在这里添加其他表级别的约束
    )


# --- 创建数据库表的函数 ---
def create_tables():
    """在数据库中创建所有定义的表 (如果它们不存在)"""
    try:
        # 尝试连接以检查配置是否有效
        with engine.connect() as connection:
            print("数据库连接成功。")
        # 创建表
        Base.metadata.create_all(bind=engine)
        print("数据库表已检查/创建成功。")
    except Exception as e:
        print(f"数据库操作失败: {e}")
        print("请检查：")
        print("1. 数据库服务是否正在运行且网络可达？")
        print("2. 数据库连接 URL 是否在 secrets 中正确配置？")
        print(f"   当前使用的 URL (可能来自 secrets 或默认值): {DATABASE_URL}")


if __name__ == "__main__":
    # 首次运行或需要确保表存在时，可以执行此脚本
    # 它会读取 secrets 并尝试连接数据库来创建表
    print("正在初始化数据库表...")
    create_tables()
    print("数据库初始化脚本执行完毕。")
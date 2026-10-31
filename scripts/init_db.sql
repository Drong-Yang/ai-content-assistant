-- ============================================================
-- AI 内容运营助手 - 数据库初始化脚本
-- ============================================================
-- 
-- 使用步骤：
-- 
-- 方法1: 使用 psql 命令行
--   1. 打开命令行，连接到 PostgreSQL:
--      psql -h localhost -U postgres
--   
--   2. 创建数据库:
--      CREATE DATABASE aicontent;
--   
--   3. 连接到新数据库:
--      \c aicontent
--   
--   4. 运行此脚本（可选，LangGraph 会自动创建表）:
--      \i scripts/init_db.sql
--
-- 方法2: 使用 pgAdmin 或其他 GUI 工具
--   1. 连接到 PostgreSQL 服务器
--   2. 右键点击 "Databases" -> "Create" -> "Database"
--   3. 输入数据库名: aicontent
--   4. 点击 "Save"
--
-- ============================================================

-- 启用 UUID 扩展（可选，用于生成 UUID）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 用户表
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建用户名索引
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ============================================================
-- LangGraph Checkpointer 表结构（参考）
-- ============================================================
-- 
-- 以下表由 AsyncPostgresSaver.setup() 自动创建，无需手动执行
-- 这里仅作为参考
--
-- checkpoint 表 - 存储图状态快照
-- checkpoint_blobs 表 - 存储大型二进制数据
-- checkpoint_writes 表 - 存储待写入数据
-- checkpoint_migrations 表 - 记录迁移版本
--
-- ============================================================

-- ============================================================
-- 配置信息
-- ============================================================
-- 
-- .env 文件中的数据库配置：
-- POSTGRES_URI=postgresql://postgres:password@localhost:5432/aicontent
--
-- 如果你的 PostgreSQL 配置不同，请修改 .env 文件中的连接字符串
-- 
-- 连接字符串格式：
-- postgresql://用户名:密码@主机:端口/数据库名
--
-- ============================================================

-- 验证数据库连接
SELECT 'Database connection successful!' AS status, current_database() AS database_name, current_user AS user_name;

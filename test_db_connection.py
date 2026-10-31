"""临时测试脚本 - 测试 PostgreSQL 连接"""
import asyncio
from psycopg_pool import AsyncConnectionPool

async def test_connection():
    uri = "postgresql://postgres:123456@localhost:5432/langgraph_db"
    print(f"测试连接: localhost:5432/langgraph_db")
    
    try:
        pool = AsyncConnectionPool(conninfo=uri, min_size=1, max_size=2, open=False)
        await pool.open()
        
        async with pool.connection() as conn:
            result = await conn.execute("SELECT current_database(), current_user, version()")
            row = await result.fetchone()
            print(f"✅ 连接成功!")
            print(f"   数据库: {row[0]}")
            print(f"   用户: {row[1]}")
            print(f"   PostgreSQL 版本: {row[2][:60]}...")
        
        await pool.close()
        print("✅ 连接池已关闭")
        return True
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())

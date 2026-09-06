import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/appdb")

engine = create_engine(DATABASE_URL)

def init_db():
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS requests_log (
        id SERIAL PRIMARY KEY,
        endpoint TEXT,
        status INT,
        version TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """
    create_users_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE,
        hashed_password TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """
    create_orders_sql = """
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        user_id INT,
        items JSONB,
        total REAL,
        app_version TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.execute(text(create_users_sql))
        conn.execute(text(create_orders_sql))
        conn.commit()

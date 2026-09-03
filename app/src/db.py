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
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()

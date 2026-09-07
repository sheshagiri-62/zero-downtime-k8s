import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/appdb")

# Force SQLAlchemy to use pg8000 driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def init_audit_db():
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS decision_log (
        id SERIAL PRIMARY KEY,
        rollout_name TEXT,
        namespace TEXT,
        decision_timestamp TIMESTAMP DEFAULT NOW(),
        from_version TEXT,
        to_version TEXT,
        rollout_phase TEXT,
        step_weight INT,
        snapshot JSONB,
        violations JSONB,
        safety_score FLOAT,
        classification TEXT,
        decision TEXT,
        action_taken TEXT,
        action_success BOOLEAN,
        rollback_triggered BOOLEAN DEFAULT FALSE,
        recovery_verified BOOLEAN,
        time_to_recover_seconds FLOAT,
        reason TEXT
    );
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(create_table_sql))
        logger.info("Audit database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize audit database: {e}")

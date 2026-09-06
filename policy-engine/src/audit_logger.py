import logging
import json
from sqlalchemy import text
from src.db import engine

logger = logging.getLogger(__name__)

class AuditLogger:
    def log_decision(self, **kwargs) -> int:
        """
        Inserts a new decision log row and returns its ID.
        kwargs should map to the columns in the decision_log table.
        """
        columns = []
        values = []
        params = {}
        
        for k, v in kwargs.items():
            columns.append(k)
            values.append(f":{k}")
            
            # Serialize dicts/lists to JSON strings
            if isinstance(v, (dict, list)):
                params[k] = json.dumps(v)
            else:
                params[k] = v
                
        if not columns:
            return None
            
        cols_str = ", ".join(columns)
        vals_str = ", ".join(values)
        
        sql = f"INSERT INTO decision_log ({cols_str}) VALUES ({vals_str}) RETURNING id;"
        
        try:
            with engine.begin() as conn:
                result = conn.execute(text(sql), params)
                inserted_id = result.scalar()
                return inserted_id
        except Exception as e:
            logger.warning(f"Audit log failed (insert): {e}")
            return None

    def update_recovery(self, log_id: int, recovery_verified: bool, time_to_recover_seconds: float):
        """
        Updates an existing decision log row with recovery verification results.
        """
        if not log_id:
            return
            
        sql = """
            UPDATE decision_log 
            SET recovery_verified = :verified, time_to_recover_seconds = :time
            WHERE id = :id
        """
        try:
            with engine.begin() as conn:
                conn.execute(text(sql), {
                    "verified": recovery_verified,
                    "time": time_to_recover_seconds,
                    "id": log_id
                })
        except Exception as e:
            logger.warning(f"Audit log failed (update): {e}")

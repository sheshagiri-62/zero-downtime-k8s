import os
from src.db import engine
from sqlalchemy import text

sql = """
SELECT decision_timestamp, rollout_phase, step_weight, classification, decision, 
       action_taken, action_success, rollback_triggered, recovery_verified, time_to_recover_seconds 
FROM decision_log 
ORDER BY decision_timestamp;
"""

with engine.connect() as conn:
    result = conn.execute(text(sql))
    
    print(f"{'TIMESTAMP':<28} | {'PHASE':<12} | {'WT':<3} | {'CLASS':<8} | {'DECISION':<22} | {'ACTION_SUCCESS':<14} | {'RECOVERY':<8} | {'RECOVERY_TIME':<13}")
    print("-" * 130)
    for row in result:
        timestamp = str(row.decision_timestamp)[:23] if row.decision_timestamp else "N/A"
        phase = row.rollout_phase or ""
        wt = row.step_weight or 0
        cls = row.classification or ""
        
        # In newer sqlalchemy, row might be a tuple or mapping
        if hasattr(row, '_mapping'):
            d = row._mapping
            decision = d.get('decision', '')
            if decision == 'SKIPPED_GRACE_PERIOD':
                decision = 'SKIP_GRACE'
            act_succ = str(d.get('action_success', ''))
            rec_ver = str(d.get('recovery_verified', ''))
            rec_time = str(d.get('time_to_recover_seconds', ''))
        else:
            decision = row[4]
            if decision == 'SKIPPED_GRACE_PERIOD':
                decision = 'SKIP_GRACE'
            act_succ = str(row[6])
            rec_ver = str(row[8])
            rec_time = str(row[9])
            
        print(f"{timestamp:<28} | {phase:<12} | {wt:<3} | {cls:<8} | {decision:<22} | {act_succ:<14} | {rec_ver:<8} | {rec_time:<13}")


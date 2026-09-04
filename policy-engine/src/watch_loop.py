import os
import time
import logging
import sys
from datetime import datetime

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector import PrometheusCollector
from src.rules import RuleEngine, Rule, DEFAULT_RULES
from src.scoring import safety_score, classify
from src.rollout_controller import get_rollout_status, promote, abort
from src.decision_engine import decide

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

ROLLOUT_NAME = os.environ.get("ROLLOUT_NAME", "myapp")
NAMESPACE = os.environ.get("NAMESPACE", "zero-downtime")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
CONSECUTIVE_REQUIRED = int(os.environ.get("CONSECUTIVE_REQUIRED", "2"))
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")

def main():
    # Update rules to use the configured consecutive requirement
    rules = []
    for r in DEFAULT_RULES:
        rules.append(Rule(
            name=r.name,
            metric_key=r.metric_key,
            threshold=r.threshold,
            comparison=r.comparison,
            severity=r.severity,
            duration_violations_required=CONSECUTIVE_REQUIRED
        ))
        
    engine = RuleEngine(rules=rules)
    collector = PrometheusCollector(PROMETHEUS_URL)
    
    logger.info(f"Starting watch loop for {NAMESPACE}/{ROLLOUT_NAME}")
    logger.info(f"Poll interval: {POLL_INTERVAL_SECONDS}s, Consecutive Required: {CONSECUTIVE_REQUIRED}")
    
    has_aborted_current = False
    
    while True:
        try:
            status = get_rollout_status(ROLLOUT_NAME, NAMESPACE)
            phase = status["phase"]
            
            if not status["is_canary"]:
                logger.info(f"[{datetime.now().isoformat()}] Rollout {ROLLOUT_NAME} is {phase}. Sleeping...")
                has_aborted_current = False
                # Reset rule engine state so old violations don't carry over to the next rollout
                engine.consecutive_violations = {rule.name: 0 for rule in engine.rules}
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
                
            snapshot = collector.get_snapshot(NAMESPACE)
            violations = engine.evaluate(snapshot)
            score = safety_score(violations)
            classification = classify(score)
            
            decision = decide(classification, violations)
            
            # Format snapshot for logging
            snap_str = ", ".join([f"{k}={v:.2f}" for k, v in snapshot.items()])
            log_line = (f"[{datetime.now().isoformat()}] Phase={phase} Step={status['step_index']} "
                        f"Weight={status['weight']}% | Snap: [{snap_str}] | "
                        f"Score={score} Class={classification.upper()} -> {decision}")
            logger.info(log_line)
            
            if decision == "PROMOTE":
                # Only promote if it's currently paused
                if phase == "Paused":
                    logger.info("Executing PROMOTE...")
                    promote(ROLLOUT_NAME, NAMESPACE)
                else:
                    logger.info("Decision is PROMOTE, but rollout is already Progressing. Waiting for next pause.")
                    
            elif decision == "HOLD":
                logger.warning("Executing HOLD...")
                for v in violations:
                    logger.warning(f"  Violation: {v.severity.upper()} rule '{v.rule_name}' "
                                   f"({v.metric_key}) violated {v.consecutive_count} times")
                                   
            elif decision == "ROLLBACK":
                if not has_aborted_current:
                    logger.error("Executing ABORT...")
                    for v in violations:
                        logger.error(f"  Violation: {v.severity.upper()} rule '{v.rule_name}' "
                                     f"({v.metric_key}) violated {v.consecutive_count} times")
                    abort(ROLLOUT_NAME, NAMESPACE)
                    has_aborted_current = True
                else:
                    logger.info("Already aborted this rollout. Waiting for phase change...")
                    
        except Exception as e:
            logger.error(f"[{datetime.now().isoformat()}] Error in watch loop: {e}")
            
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()

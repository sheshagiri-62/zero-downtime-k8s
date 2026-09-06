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
from src.rollout_controller import get_rollout_status, promote
import src.rollout_controller as rollout_controller_module
from src.decision_engine import decide
from src.rollback_manager import RollbackManager
from src.recovery_verifier import RecoveryVerifier
from src.db import init_audit_db
from src.audit_logger import AuditLogger

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

ROLLOUT_NAME = os.environ.get("ROLLOUT_NAME", "myapp")
NAMESPACE = os.environ.get("NAMESPACE", "zero-downtime")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
CONSECUTIVE_REQUIRED = int(os.environ.get("CONSECUTIVE_REQUIRED", "2"))
GRACE_PERIOD_SECONDS = int(os.environ.get("GRACE_PERIOD_SECONDS", "20"))
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")

class WatchLoop:
    def __init__(self, engine, collector, rollout_name, namespace, grace_period):
        self.engine = engine
        self.collector = collector
        self.rollout_name = rollout_name
        self.namespace = namespace
        self.grace_period = grace_period
        self.last_weight = -1
        self.last_weight_change_time = 0
        self.rollback_manager = RollbackManager(rollout_name, namespace)
        self.recovery_verifier = RecoveryVerifier(engine, collector, rollout_controller_module)
        self.audit_logger = AuditLogger()
        
    def step(self):
        status = get_rollout_status(self.rollout_name, self.namespace)
        phase = status["phase"]
        
        if not status["is_canary"]:
            logger.info(f"[{datetime.now().isoformat()}] Rollout {self.rollout_name} is {phase}. Sleeping...")
            self.engine.consecutive_violations = {rule.name: 0 for rule in self.engine.rules}
            return
            
        current_weight = status.get("weight", 0)
        if current_weight != self.last_weight:
            self.last_weight = current_weight
            self.last_weight_change_time = time.time()
            
        snapshot = self.collector.get_snapshot(self.namespace)
        snap_str = ", ".join([f"{k}={v:.2f}" for k, v in snapshot.items()])
        
        time_since_change = time.time() - self.last_weight_change_time
        if time_since_change < self.grace_period:
            remaining = int(self.grace_period - time_since_change)
            logger.info(f"[{datetime.now().isoformat()}] Phase={phase} Step={status['step_index']} "
                        f"Weight={current_weight}% | Snap: [{snap_str}] | "
                        f"grace period active ({remaining}s remaining), skipping evaluation")
            self.audit_logger.log_decision(
                rollout_name=self.rollout_name, namespace=self.namespace,
                rollout_phase=phase, step_weight=current_weight, 
                decision="SKIPPED_GRACE_PERIOD", action_taken="none"
            )
            return
            
        violations = self.engine.evaluate(snapshot)
        score = safety_score(violations)
        classification = classify(score)
        
        decision = decide(classification, violations)
        
        log_line = (f"[{datetime.now().isoformat()}] Phase={phase} Step={status['step_index']} "
                    f"Weight={current_weight}% | Snap: [{snap_str}] | "
                    f"Score={score} Class={classification.upper()} -> {decision}")
        logger.info(log_line)
        
        if decision == "PROMOTE":
            if phase == "Paused":
                logger.info("Executing PROMOTE...")
                promote(self.rollout_name, self.namespace)
                self.audit_logger.log_decision(
                    rollout_name=self.rollout_name, namespace=self.namespace,
                    rollout_phase=phase, step_weight=current_weight, snapshot=snapshot,
                    safety_score=score, classification=classification.upper(),
                    decision=decision, action_taken="promote", action_success=True, rollback_triggered=False
                )
            else:
                logger.info("Decision is PROMOTE, but rollout is already Progressing. Waiting for next pause.")
                
        elif decision == "HOLD":
            logger.warning("Executing HOLD...")
            for v in violations:
                logger.warning(f"  Violation: {v.severity.upper()} rule '{v.rule_name}' "
                               f"({v.metric_key}) violated {v.consecutive_count} times")
            
            violations_dict = [v.__dict__ for v in violations]
            self.audit_logger.log_decision(
                rollout_name=self.rollout_name, namespace=self.namespace,
                rollout_phase=phase, step_weight=current_weight, snapshot=snapshot,
                violations=violations_dict, safety_score=score, classification=classification.upper(),
                decision=decision, action_taken="none", reason=f"{len(violations)} rule(s) violated"
            )
                               
        elif decision == "ROLLBACK":
            generation = status.get("generation", 0)
            success = self.rollback_manager.trigger(violations, generation)
            
            violations_dict = [v.__dict__ for v in violations]
            log_id = self.audit_logger.log_decision(
                rollout_name=self.rollout_name, namespace=self.namespace,
                rollout_phase=phase, step_weight=current_weight, snapshot=snapshot,
                violations=violations_dict, safety_score=score, classification=classification.upper(),
                decision=decision, action_taken="rollback", action_success=success, rollback_triggered=True
            )
            
            if success:
                logger.info("Rollback triggered successfully. Verifying recovery...")
                result = self.recovery_verifier.verify(self.rollout_name, self.namespace, violations)
                if result.recovered:
                    logger.info(f"RECOVERY CONFIRMED in {result.time_to_recover_seconds}s. System is stable.")
                else:
                    logger.critical(f"ALERT: System did NOT recover after rollback! Manual intervention required. Final snapshot: {result.final_snapshot}")
                
                if log_id:
                    self.audit_logger.update_recovery(log_id, result.recovered, result.time_to_recover_seconds)
            else:
                logger.critical("ALERT: Rollback abort command failed to execute. Manual intervention required.")

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
    
    logger.info("Initializing Audit Database...")
    init_audit_db()
    
    logger.info(f"Starting watch loop for {NAMESPACE}/{ROLLOUT_NAME}")
    logger.info(f"Poll interval: {POLL_INTERVAL_SECONDS}s, Consecutive Required: {CONSECUTIVE_REQUIRED}, Grace Period: {GRACE_PERIOD_SECONDS}s")
    
    loop = WatchLoop(engine, collector, ROLLOUT_NAME, NAMESPACE, GRACE_PERIOD_SECONDS)
    
    while True:
        try:
            loop.step()
        except Exception as e:
            logger.error(f"[{datetime.now().isoformat()}] Error in watch loop: {e}")
            
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()

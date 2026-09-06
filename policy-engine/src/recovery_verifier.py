from dataclasses import dataclass
import time
import logging

logger = logging.getLogger(__name__)

@dataclass
class RecoveryResult:
    recovered: bool
    time_to_recover_seconds: int
    final_snapshot: dict
    checks_performed: int

class RecoveryVerifier:
    def __init__(self, engine, collector, rollout_controller_module):
        self.engine = engine
        self.collector = collector
        self.rollout_controller = rollout_controller_module

    def verify(self, rollout_name: str, namespace: str, violations: list = None, check_interval: int = 10) -> RecoveryResult:
        timeout_seconds = 90
        if violations:
            for v in violations:
                if "latency" in v.metric_key:
                    timeout_seconds = 360
                    
        logger.info(f"Starting recovery verification for {rollout_name} in {namespace}. Timeout: {timeout_seconds}s")
        start_time = time.time()
        consecutive_healthy = 0
        checks = 0
        final_snapshot = {}
        
        while time.time() - start_time < timeout_seconds:
            checks += 1
            time.sleep(check_interval)
            
            # Check phase
            try:
                status = self.rollout_controller.get_rollout_status(rollout_name, namespace)
            except Exception as e:
                logger.error(f"Failed to get rollout status during recovery check: {e}")
                continue
                
            phase = status["phase"]
            
            # We want it to be Healthy or Degraded (which Argo sets when aborted) but not stuck Progressing on a bad version
            if phase == "Progressing":
                logger.info(f"Recovery check {checks}: Rollout is still Progressing. Waiting...")
                consecutive_healthy = 0
                continue
                
            # Check metrics
            try:
                snapshot = self.collector.get_snapshot(namespace)
                final_snapshot = snapshot
                
                # We need to evaluate the snapshot without polluting the main watch loop's consecutive count.
                # So we manually check if any rule would trigger a violation.
                is_healthy = True
                for rule in self.engine.rules:
                    val = snapshot.get(rule.metric_key)
                    if val is not None:
                        is_violated = False
                        if rule.comparison == "gt" and val > rule.threshold:
                            is_violated = True
                        elif rule.comparison == "lt" and val < rule.threshold:
                            is_violated = True
                            
                        if is_violated:
                            is_healthy = False
                            logger.warning(f"Recovery check {checks}: Rule {rule.name} still failing (val={val})")
                            break
                        
                if is_healthy:
                    consecutive_healthy += 1
                    logger.info(f"Recovery check {checks}: Snapshot is HEALTHY ({consecutive_healthy}/2)")
                    if consecutive_healthy >= 2:
                        duration = int(time.time() - start_time)
                        logger.info(f"Recovery SUCCESSFUL in {duration} seconds.")
                        return RecoveryResult(True, duration, final_snapshot, checks)
                else:
                    consecutive_healthy = 0
                    
            except Exception as e:
                logger.error(f"Failed to get metrics during recovery check: {e}")
                consecutive_healthy = 0
                
        logger.critical(f"CRITICAL: Recovery verification TIMED OUT after {timeout_seconds}s for {rollout_name}. MANUAL INTERVENTION REQUIRED.")
        return RecoveryResult(False, timeout_seconds, final_snapshot, checks)

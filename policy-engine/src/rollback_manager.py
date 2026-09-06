import logging
import time
from .rollout_controller import abort

logger = logging.getLogger(__name__)

class RollbackManager:
    def __init__(self, rollout_name: str, namespace: str):
        self.rollout_name = rollout_name
        self.namespace = namespace
        self.aborted_generations = set()
        
    def trigger(self, violations: list, generation: int) -> bool:
        """
        Triggers an abort for the given generation if it hasn't been aborted yet.
        Returns True if successful or already aborted, False if it failed after retries.
        """
        if generation in self.aborted_generations:
            logger.info(f"Rollback already triggered for generation {generation}. Skipping.")
            return True
            
        logger.error("Executing ABORT...")
        for v in violations:
            logger.error(f"  Violation: {v.severity.upper()} rule '{v.rule_name}' "
                         f"({v.metric_key}) violated {v.consecutive_count} times")
                         
        # Retry logic
        for attempt in range(2):
            try:
                abort(self.rollout_name, self.namespace)
                self.aborted_generations.add(generation)
                return True
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"Abort command failed: {e}. Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    logger.critical(f"CRITICAL: Automated rollback failed after retries for {self.rollout_name}. "
                                    f"MANUAL INTERVENTION REQUIRED. Error: {e}")
                    return False
        return False

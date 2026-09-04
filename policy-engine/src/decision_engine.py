from typing import List
from .rules import Violation
import logging

logger = logging.getLogger(__name__)

def decide(classification: str, violations: List[Violation]) -> str:
    """
    Returns one of "PROMOTE", "HOLD", "ROLLBACK" based on the classification.
    """
    if classification == "critical":
        return "ROLLBACK"
    elif classification == "degraded":
        return "HOLD"
    elif classification == "healthy":
        return "PROMOTE"
    else:
        logger.warning(f"Unknown classification {classification}, defaulting to HOLD")
        return "HOLD"

from typing import List
from .rules import Violation

def safety_score(violations: List[Violation]) -> float:
    """
    Returns a score between 0 and 100 based on active violations.
    Weights are tunable later based on experiment results.
    """
    score = 100.0
    for violation in violations:
        if violation.severity == "critical":
            score -= 40.0
        elif violation.severity == "warning":
            score -= 15.0
            
    return max(0.0, score)

def classify(score: float) -> str:
    """
    Classify the score into a health state.
    """
    if score >= 80.0:
        return "healthy"
    elif score >= 50.0:
        return "degraded"
    else:
        return "critical"

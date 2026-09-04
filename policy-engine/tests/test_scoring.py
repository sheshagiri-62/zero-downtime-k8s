from src.scoring import safety_score, classify
from src.rules import Violation

def test_safety_score_perfect():
    assert safety_score([]) == 100.0

def test_safety_score_warning():
    violations = [Violation("rule1", "metric1", "warning", 2)]
    assert safety_score(violations) == 85.0

def test_safety_score_critical():
    violations = [Violation("rule1", "metric1", "critical", 2)]
    assert safety_score(violations) == 60.0

def test_safety_score_multiple():
    violations = [
        Violation("rule1", "metric1", "critical", 2),
        Violation("rule2", "metric2", "warning", 2),
        Violation("rule3", "metric3", "critical", 2)
    ]
    assert safety_score(violations) == 5.0  # (100 - 40 - 15 - 40) = 5
    # Ah, 100 - 40 - 15 - 40 = 5! Let's add another to hit 0.
    violations.append(Violation("rule4", "metric4", "warning", 2))
    assert safety_score(violations) == 0.0  # Capped at 0

def test_classify():
    assert classify(100.0) == "healthy"
    assert classify(80.0) == "healthy"
    assert classify(79.9) == "degraded"
    assert classify(50.0) == "degraded"
    assert classify(49.9) == "critical"
    assert classify(0.0) == "critical"

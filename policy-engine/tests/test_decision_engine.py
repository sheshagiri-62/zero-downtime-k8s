from src.decision_engine import decide
from src.rules import Violation

def test_decide_healthy():
    assert decide("healthy", []) == "PROMOTE"

def test_decide_degraded():
    violations = [Violation("rule", "metric", "warning", 2)]
    assert decide("degraded", violations) == "HOLD"

def test_decide_critical():
    violations = [Violation("rule", "metric", "critical", 2)]
    assert decide("critical", violations) == "ROLLBACK"

def test_decide_multiple_critical():
    violations = [
        Violation("rule1", "metric1", "critical", 2),
        Violation("rule2", "metric2", "critical", 2)
    ]
    assert decide("critical", violations) == "ROLLBACK"

def test_decide_unknown():
    assert decide("unknown", []) == "HOLD"

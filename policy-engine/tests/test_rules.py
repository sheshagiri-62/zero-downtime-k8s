import pytest
from src.rules import RuleEngine, Rule

def test_no_violations():
    engine = RuleEngine()
    snapshot = {
        "error_rate_pct": 1.0,
        "p95_latency_ms": 100.0,
        "ready_pods": 4,
        "pod_restarts_5m": 0
    }
    
    # 1st evaluation
    v1 = engine.evaluate(snapshot)
    assert len(v1) == 0
    
    # 2nd evaluation
    v2 = engine.evaluate(snapshot)
    assert len(v2) == 0

def test_warning_duration():
    engine = RuleEngine()
    snapshot = {
        "error_rate_pct": 10.0,  # > 5 (warning), < 15 (critical)
        "p95_latency_ms": 100.0,
        "ready_pods": 4,
        "pod_restarts_5m": 0
    }
    
    # 1st evaluation -> no violation yet because duration=2
    v1 = engine.evaluate(snapshot)
    assert len(v1) == 0
    
    # 2nd evaluation -> yields violation
    v2 = engine.evaluate(snapshot)
    assert len(v2) == 1
    assert v2[0].rule_name == "error_rate_warning"
    assert v2[0].severity == "warning"
    assert v2[0].consecutive_count == 2

def test_critical_trigger():
    engine = RuleEngine()
    snapshot = {
        "error_rate_pct": 20.0,  # > 15 (critical)
        "p95_latency_ms": 100.0,
        "ready_pods": 4,
        "pod_restarts_5m": 0
    }
    
    engine.evaluate(snapshot)
    v2 = engine.evaluate(snapshot)
    
    assert len(v2) == 2  # Will trigger both warning (>5) and critical (>15)
    severities = [v.severity for v in v2]
    assert "warning" in severities
    assert "critical" in severities

def test_reset_consecutive():
    engine = RuleEngine()
    
    # 1. Violates
    engine.evaluate({"error_rate_pct": 10.0})
    
    # 2. Healthy (resets count)
    v = engine.evaluate({"error_rate_pct": 1.0})
    assert len(v) == 0
    
    # 3. Violates again
    v = engine.evaluate({"error_rate_pct": 10.0})
    assert len(v) == 0  # Only 1 consecutive violation

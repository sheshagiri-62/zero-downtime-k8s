import pytest
import time
from unittest.mock import patch, MagicMock

from src.watch_loop import WatchLoop
from src.rules import RuleEngine, Rule

@pytest.fixture
def mock_dependencies():
    engine = RuleEngine(rules=[
        Rule(
            name="test_rule",
            metric_key="error_rate",
            threshold=15.0,
            comparison="gt",
            severity="critical",
            duration_violations_required=2
        )
    ])
    collector = MagicMock()
    return engine, collector

@patch("src.watch_loop.get_rollout_status")
@patch("src.watch_loop.time.time")
def test_grace_period_skips_evaluation(mock_time, mock_get_status, mock_dependencies):
    engine, collector = mock_dependencies
    
    # Snapshot that would trigger a violation
    collector.get_snapshot.return_value = {"error_rate": 20.0}
    
    loop = WatchLoop(
        engine=engine,
        collector=collector,
        rollout_name="myapp",
        namespace="zero-downtime",
        grace_period=20
    )
    
    # 1. First step: weight changes from -1 to 10. Grace period starts at t=100.
    mock_get_status.return_value = {
        "is_canary": True,
        "phase": "Paused",
        "weight": 10,
        "step_index": 1
    }
    mock_time.return_value = 100.0
    
    loop.step()
    
    # Should be inside grace period (t=100 - t=100 = 0 < 20).
    # Evaluation should be skipped, consecutive violations should be 0.
    assert engine.consecutive_violations["test_rule"] == 0
    
    # 2. Second step: Still inside grace period (t=110)
    mock_time.return_value = 110.0
    loop.step()
    assert engine.consecutive_violations["test_rule"] == 0
    
    # 3. Third step: Grace period expired (t=121)
    mock_time.return_value = 121.0
    loop.step()
    
    assert engine.consecutive_violations["test_rule"] == 1
    
    # 4. Fourth step: Grace period still expired (t=130)
    mock_time.return_value = 130.0
    loop.step()
    
    # Consecutive count should go to 2
    assert engine.consecutive_violations["test_rule"] == 2

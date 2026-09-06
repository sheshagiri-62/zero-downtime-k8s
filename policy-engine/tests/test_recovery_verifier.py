import pytest
from unittest.mock import MagicMock, patch

from src.recovery_verifier import RecoveryVerifier

@pytest.fixture
def mock_dependencies():
    engine = MagicMock()
    collector = MagicMock()
    rollout_controller = MagicMock()
    
    # Mock engine rules behavior
    rule1 = MagicMock()
    rule1.name = "test_rule"
    rule1.metric_key = "error_rate"
    rule1.threshold = 5.0
    rule1.comparison = "gt"
    
    engine.rules = [rule1]
    
    return engine, collector, rollout_controller

@patch("src.recovery_verifier.time.sleep")
@patch("src.recovery_verifier.time.time")
def test_recovery_success(mock_time, mock_sleep, mock_dependencies):
    engine, collector, rollout_controller = mock_dependencies
    
    # Simulate time progressing
    mock_time.side_effect = [100.0, 100.0, 100.0, 100.0, 100.0]
    
    # Rollout is Degraded (aborted state)
    rollout_controller.get_rollout_status.return_value = {"phase": "Degraded"}
    
    # Snapshot returns healthy metric
    collector.get_snapshot.return_value = {"error_rate": 0.0}
    
    verifier = RecoveryVerifier(engine, collector, rollout_controller)
    
    result = verifier.verify("myapp", "zero-downtime", timeout_seconds=90, check_interval=10)
    
    assert result.recovered is True
    assert result.checks_performed == 2 # Requires 2 consecutive checks
    
@patch("src.recovery_verifier.time.sleep")
@patch("src.recovery_verifier.time.time")
def test_recovery_timeout(mock_time, mock_sleep, mock_dependencies):
    engine, collector, rollout_controller = mock_dependencies
    
    # Simulate time progressing past timeout
    mock_time.side_effect = [100.0, 110.0, 120.0, 130.0, 200.0] # 200 - 100 > 90
    
    rollout_controller.get_rollout_status.return_value = {"phase": "Degraded"}
    
    collector.get_snapshot.return_value = {"error_rate": 50.0}
    
    verifier = RecoveryVerifier(engine, collector, rollout_controller)
    
    result = verifier.verify("myapp", "zero-downtime", timeout_seconds=90, check_interval=10)
    
    assert result.recovered is False
    assert result.checks_performed > 0

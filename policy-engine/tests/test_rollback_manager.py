import pytest
from unittest.mock import patch, MagicMock

from src.rollback_manager import RollbackManager
from src.rules import Violation

@patch("src.rollback_manager.abort")
def test_trigger_success_first_try(mock_abort):
    manager = RollbackManager("myapp", "zero-downtime")
    violations = [Violation("test", "error", "critical", 2)]
    
    result = manager.trigger(violations, generation=10)
    
    assert result is True
    mock_abort.assert_called_once_with("myapp", "zero-downtime")
    assert 10 in manager.aborted_generations

@patch("src.rollback_manager.time.sleep")
@patch("src.rollback_manager.abort")
def test_trigger_success_on_retry(mock_abort, mock_sleep):
    manager = RollbackManager("myapp", "zero-downtime")
    violations = []
    
    # Fail first time, succeed second time
    mock_abort.side_effect = [Exception("Failed"), None]
    
    result = manager.trigger(violations, generation=11)
    
    assert result is True
    assert mock_abort.call_count == 2
    mock_sleep.assert_called_once_with(5)
    assert 11 in manager.aborted_generations

@patch("src.rollback_manager.time.sleep")
@patch("src.rollback_manager.abort")
def test_trigger_failure(mock_abort, mock_sleep):
    manager = RollbackManager("myapp", "zero-downtime")
    violations = []
    
    # Fail both times
    mock_abort.side_effect = [Exception("Failed 1"), Exception("Failed 2")]
    
    result = manager.trigger(violations, generation=12)
    
    assert result is False
    assert mock_abort.call_count == 2
    assert 12 not in manager.aborted_generations

@patch("src.rollback_manager.abort")
def test_trigger_idempotency(mock_abort):
    manager = RollbackManager("myapp", "zero-downtime")
    manager.aborted_generations.add(10)
    
    result = manager.trigger([], generation=10)
    
    assert result is True
    mock_abort.assert_not_called()

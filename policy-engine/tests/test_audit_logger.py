import pytest
from unittest.mock import MagicMock, patch
from src.audit_logger import AuditLogger

@patch('src.audit_logger.engine')
def test_log_decision_success(mock_engine):
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    
    mock_result = MagicMock()
    mock_result.scalar.return_value = 42
    mock_conn.execute.return_value = mock_result
    
    logger = AuditLogger()
    inserted_id = logger.log_decision(
        rollout_name="myapp",
        namespace="zero-downtime",
        decision="PROMOTE",
        snapshot={"ready_pods": 4},
        action_success=True
    )
    
    assert inserted_id == 42
    assert mock_conn.execute.called
    
    # Verify the generated SQL contains the right columns
    args, kwargs = mock_conn.execute.call_args
    sql = str(args[0])
    assert "INSERT INTO decision_log" in sql
    assert "rollout_name" in sql
    assert "namespace" in sql
    assert "decision" in sql
    assert "snapshot" in sql
    assert "action_success" in sql

@patch('src.audit_logger.engine')
def test_log_decision_empty(mock_engine):
    logger = AuditLogger()
    inserted_id = logger.log_decision()
    
    assert inserted_id is None
    assert not mock_engine.begin.called

@patch('src.audit_logger.engine')
def test_log_decision_exception_swallowed(mock_engine):
    mock_engine.begin.side_effect = Exception("DB Connection Failed")
    
    logger = AuditLogger()
    inserted_id = logger.log_decision(decision="PROMOTE")
    
    assert inserted_id is None

@patch('src.audit_logger.engine')
def test_update_recovery_success(mock_engine):
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    
    logger = AuditLogger()
    logger.update_recovery(42, True, 10.5)
    
    assert mock_conn.execute.called
    args, kwargs = mock_conn.execute.call_args
    sql = str(args[0])
    assert "UPDATE decision_log" in sql
    assert "SET recovery_verified" in sql
    assert "time_to_recover_seconds" in sql

@patch('src.audit_logger.engine')
def test_update_recovery_exception_swallowed(mock_engine):
    mock_engine.begin.side_effect = Exception("DB Connection Failed")
    
    logger = AuditLogger()
    # Should not raise
    logger.update_recovery(42, True, 10.5)

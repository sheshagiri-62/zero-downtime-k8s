import pytest
from unittest.mock import patch, MagicMock
import json
from src.rollout_controller import get_rollout_status, promote, abort, run_command

@pytest.fixture
def mock_subprocess():
    with patch("src.rollout_controller.subprocess.run") as mock_run:
        yield mock_run

def test_run_command_success(mock_subprocess):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "success_output"
    mock_subprocess.return_value = mock_result
    
    assert run_command(["echo", "hello"]) == "success_output"
    mock_subprocess.assert_called_once_with(["echo", "hello"], capture_output=True, text=True)

def test_run_command_failure(mock_subprocess):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error_message"
    mock_subprocess.return_value = mock_result
    
    with pytest.raises(RuntimeError, match="Command failed"):
        run_command(["false"])

def test_get_rollout_status(mock_subprocess):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps({
        "status": {
            "phase": "Paused",
            "currentStepIndex": 1
        },
        "spec": {
            "strategy": {
                "canary": {
                    "steps": [
                        {"setWeight": 10},
                        {"pause": {}},
                        {"setWeight": 25}
                    ]
                }
            }
        }
    })
    mock_subprocess.return_value = mock_result
    
    status = get_rollout_status("myapp", "zero-downtime")
    
    assert status["phase"] == "Paused"
    assert status["step_index"] == 1
    assert status["weight"] == 10
    assert status["is_canary"] is True
    mock_subprocess.assert_called_once_with(["kubectl", "get", "rollout", "myapp", "-n", "zero-downtime", "-o", "json"], capture_output=True, text=True)

def test_promote(mock_subprocess):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_subprocess.return_value = mock_result
    
    promote("myapp", "zero-downtime")
    mock_subprocess.assert_called_once_with(["./kubectl-argo-rollouts.exe", "promote", "myapp", "-n", "zero-downtime"], capture_output=True, text=True)

def test_abort(mock_subprocess):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_subprocess.return_value = mock_result
    
    abort("myapp", "zero-downtime")
    mock_subprocess.assert_called_once_with(["./kubectl-argo-rollouts.exe", "abort", "myapp", "-n", "zero-downtime"], capture_output=True, text=True)

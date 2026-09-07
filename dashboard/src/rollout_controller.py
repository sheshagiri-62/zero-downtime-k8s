import subprocess
import json
import logging

logger = logging.getLogger(__name__)

def run_command(cmd_args: list[str]) -> str:
    """Run a subprocess command, capture output, and raise on failure."""
    logger.debug(f"Running command: {' '.join(cmd_args)}")
    result = subprocess.run(cmd_args, capture_output=True, text=True)
    if result.returncode != 0:
        error_msg = f"Command failed: {' '.join(cmd_args)}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    return result.stdout

def get_rollout_status(name: str, namespace: str) -> dict:
    """
    Returns rollout status:
    - phase (e.g. Progressing, Paused, Healthy, Degraded)
    - step_index (current step in the canary steps)
    - weight (current weight percentage)
    - is_canary (True if a canary is active, False if fully promoted/stable)
    """
    cmd = ["kubectl", "get", "rollout", name, "-n", namespace, "-o", "json"]
    output = run_command(cmd)
    data = json.loads(output)
    
    status = data.get("status", {})
    spec = data.get("spec", {})
    
    phase = status.get("phase", "Unknown")
    generation = data.get("metadata", {}).get("generation", 0)
    
    # If the phase is "Healthy", the rollout is usually fully promoted and stable.
    # If it's "Progressing" or "Paused", it's in a canary.
    current_step_index = status.get("currentStepIndex")
    steps = spec.get("strategy", {}).get("canary", {}).get("steps", [])
    
    weight = 100
    if phase == "Healthy":
        weight = 100
    elif current_step_index is not None and steps:
        if current_step_index >= len(steps):
            weight = 100
        else:
            for i in range(min(current_step_index, len(steps) - 1), -1, -1):
                if "setWeight" in steps[i]:
                    weight = steps[i]["setWeight"]
                    break
                
    is_canary = phase in ["Progressing", "Paused"]
    
    return {
        "phase": phase,
        "step_index": current_step_index,
        "weight": weight,
        "is_canary": is_canary,
        "generation": generation,
        "raw_status": status
    }

def promote(name: str, namespace: str):
    """Promote the rollout manually."""
    logger.info(f"Promoting rollout {name} in {namespace}")
    cmd = ["kubectl-argo-rollouts", "promote", name, "-n", namespace]
    run_command(cmd)

def abort(name: str, namespace: str):
    """Abort the rollout manually."""
    logger.warning(f"Aborting rollout {name} in {namespace}")
    cmd = ["kubectl-argo-rollouts", "abort", name, "-n", namespace]
    run_command(cmd)

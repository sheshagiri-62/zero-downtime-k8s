import sys
import os

# Add parent dir to path so we can import src as a module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector import PrometheusCollector
from src.rules import RuleEngine
from src.scoring import safety_score, classify

def main():
    print("Collecting snapshot from Prometheus (http://localhost:9090)...")
    try:
        collector = PrometheusCollector("http://localhost:9090")
        snapshot = collector.get_snapshot("zero-downtime")
        print("\n--- Snapshot ---")
        for k, v in snapshot.items():
            print(f"{k}: {v:.2f}")
            
        print("\n--- Evaluation ---")
        engine = RuleEngine()
        violations = engine.evaluate(snapshot)
        
        if not violations:
            print("No rules violated (wait, duration_violations_required is 2, so 1st eval won't trigger).")
            print("Running evaluation again with same snapshot to simulate 2nd poll...")
            violations = engine.evaluate(snapshot)
            
        if violations:
            print(f"Active Violations ({len(violations)}):")
            for v in violations:
                print(f"  - [{v.severity.upper()}] Rule '{v.rule_name}' violated {v.consecutive_count} consecutive times on '{v.metric_key}'")
        else:
            print("No active violations.")
            
        score = safety_score(violations)
        status = classify(score)
        
        print("\n--- Health Score ---")
        print(f"Score: {score:.1f}/100.0")
        print(f"Status: {status.upper()}")
        
    except Exception as e:
        print(f"Error connecting to Prometheus: {e}")

if __name__ == "__main__":
    main()

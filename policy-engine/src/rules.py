from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Rule:
    name: str
    metric_key: str
    threshold: float
    comparison: str  # "gt" or "lt"
    severity: str  # "warning" or "critical"
    duration_violations_required: int = 2

@dataclass
class Violation:
    rule_name: str
    metric_key: str
    severity: str
    consecutive_count: int

DEFAULT_RULES = [
    Rule("error_rate_warning", "error_rate_pct", 5.0, "gt", "warning"),
    Rule("error_rate_critical", "error_rate_pct", 15.0, "gt", "critical"),
    Rule("latency_warning", "p95_latency_ms", 500.0, "gt", "warning"),
    Rule("latency_critical", "p95_latency_ms", 2000.0, "gt", "critical"),
    Rule("ready_pods_critical", "ready_pods", 4.0, "lt", "critical"),  # Expected 4 replicas
    Rule("restarts_warning", "pod_restarts_5m", 0.0, "gt", "warning"),
    Rule("restarts_critical", "pod_restarts_5m", 3.0, "gt", "critical"),
]

class RuleEngine:
    def __init__(self, rules: List[Rule] = None):
        self.rules = rules or DEFAULT_RULES
        self.consecutive_violations: Dict[str, int] = {rule.name: 0 for rule in self.rules}
        
    def evaluate(self, snapshot: dict) -> List[Violation]:
        violations = []
        for rule in self.rules:
            if rule.metric_key not in snapshot:
                continue
                
            val = snapshot[rule.metric_key]
            
            is_violated = False
            if rule.comparison == "gt" and val > rule.threshold:
                is_violated = True
            elif rule.comparison == "lt" and val < rule.threshold:
                is_violated = True
                
            if is_violated:
                self.consecutive_violations[rule.name] += 1
            else:
                self.consecutive_violations[rule.name] = 0
                
            consecutive_count = self.consecutive_violations[rule.name]
            if consecutive_count >= rule.duration_violations_required:
                violations.append(Violation(
                    rule_name=rule.name,
                    metric_key=rule.metric_key,
                    severity=rule.severity,
                    consecutive_count=consecutive_count
                ))
                
        return violations

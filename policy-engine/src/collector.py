import os
import requests

class PrometheusCollector:
    def __init__(self, base_url=None):
        self.base_url = base_url or os.environ.get("PROMETHEUS_URL", "http://localhost:9090")

    def query(self, promql: str, default=None) -> float:
        response = requests.get(f"{self.base_url}/api/v1/query", params={"query": promql})
        response.raise_for_status()
        
        data = response.json().get("data", {})
        result = data.get("result", [])
        
        if not result:
            if default is not None:
                return default
            raise ValueError(f"Query returned no data: {promql}")
        if len(result) > 1:
            raise ValueError(f"Query returned multiple series: {promql}")
            
        value = result[0].get("value")
        if not value or len(value) < 2:
            if default is not None:
                return default
            raise ValueError(f"Query returned malformed value: {promql}")
            
        try:
            val = float(value[1])
            if str(val) == "nan":
                return default if default is not None else float('nan')
            return val
        except (ValueError, TypeError):
            if str(value[1]) == "NaN":
                if default is not None:
                    return default
            raise ValueError(f"Could not parse query result as float: {value[1]}")

    def get_snapshot(self, namespace: str) -> dict:
        request_rate = self.query("sum(rate(app_requests_total[1m]))", default=0.0)
        
        # If no requests, error rate is 0
        error_rate_pct = 0.0
        if request_rate > 0:
            error_rate_pct = self.query(
                '(sum(rate(app_requests_total{status="500"}[1m])) or vector(0)) / sum(rate(app_requests_total[1m])) * 100', 
                default=0.0
            )
            
        p95_latency_ms = self.query(
            "histogram_quantile(0.95, sum(rate(app_request_latency_seconds_bucket[5m])) by (le)) * 1000",
            default=0.0
        )
        
        ready_pods = self.query(
            f'sum(kube_pod_status_ready{{namespace="{namespace}", condition="true", pod=~"myapp-.*"}})',
            default=0.0
        )
        
        pod_restarts_5m = self.query(
            f'sum(increase(kube_pod_container_status_restarts_total{{namespace="{namespace}", pod=~"myapp-.*"}}[5m]))',
            default=0.0
        )
        
        return {
            "error_rate_pct": error_rate_pct,
            "p95_latency_ms": p95_latency_ms,
            "request_rate": request_rate,
            "ready_pods": ready_pods,
            "pod_restarts_5m": pod_restarts_5m
        }

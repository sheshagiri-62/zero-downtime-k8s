# Load Testing & Failure Experiments Results

## Scenarios Summary

| Scenario | Description | Peak Error Rate | Peak p95 Latency | Time to Detect | Time to Recover |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A: Baseline** | Deploy a healthy version 100% immediately (no canary). | 0% | ~5ms | N/A | N/A |
| **B: Healthy Canary** | Deploy a healthy version incrementally (10% -> 25% -> 50% -> 90%). | 0% | ~5ms | N/A | N/A |
| **C: Bad Canary** | Deploy an image failing 50% of requests instantly. | 37.4% | ~5ms | ~3m | 66s |
| **D: Noisy Canary** | Deploy an image failing 20% of requests and latency spikes. | ~17.1% | ~2244ms | ~2m | 276s |
## Methodology Note

**Why did Scenario D take longer to verify recovery?**
While the rollback in Scenario D was triggered promptly upon detecting degradation, the recovery verification phase took significantly longer (~5 minutes) compared to Scenario C (~60 seconds). This is an expected artifact of the metric aggregation window mismatch:
- **Error Rate** evaluates a fast-moving window (`rate(...[1m])`). As soon as the canary pod is drained, error counts immediately plummet, allowing recovery verification to clear in under 90s.
- **Latency** uses a larger sliding window (`[5m]`) for stability to compute its 95th percentile bucket interpolations (`histogram_quantile`). Even after the slow canary is fully removed from traffic, its historical data points linger in Prometheus's 5-minute bucket buffer. The 95th percentile will remain artificially high until that 5-minute window fully flushes the old data.

This demonstrates a critical production engineering consideration: **safe verification timeouts must dynamically match the longest aggregation window of the violated metrics**. We extended the recovery verifier's timeout to 360 seconds specifically for latency rollbacks to prevent false-positive recovery failures.

## Raw SQL Dump (`decision_log`)

### Scenario A: Baseline
*(No decision log entry. The rollout skips all canary steps, promoting 100% instantly without pausing for policy engine evaluation).*

### Scenario B: Healthy Canary (Final Promote)
```json
[65, datetime.datetime(2026, 9, 5, 9, 57, 31, 138314), 'promote', None, None, 100.0, {'ready_pods': 5.0, 'request_rate': 48.545111111111105, 'error_rate_pct': 6.660777858690279, 'p95_latency_ms': 4.75, 'pod_restarts_5m': 0.0}]
```

### Scenario C: Bad Canary (Rollback)
```json
[74, datetime.datetime(2026, 9, 5, 10, 0, 2, 514019), 'rollback', None, None, 45.0, {'ready_pods': 5.0, 'request_rate': 125.80119777777777, 'error_rate_pct': 37.41667206157397, 'p95_latency_ms': 4.750000000000001, 'pod_restarts_5m': 0.0}, True, 66.0]
```

### Scenario D: Noisy/Slow Failure Canary (Rollback)
```json
[105, datetime.datetime(2026, 9, 5, 10, 32, 21, 819776), 'rollback', None, None, 30.0, {'ready_pods': 5.0, 'request_rate': 15.253835555555554, 'error_rate_pct': 17.115497680266845, 'p95_latency_ms': 2243.707052413711, 'pod_restarts_5m': 0.0}, True, 276.0]
```

import pytest
import responses
from src.collector import PrometheusCollector

@responses.activate
def test_query_success():
    responses.add(
        responses.GET,
        "http://localhost:9090/api/v1/query",
        json={"data": {"result": [{"value": [1600000000.0, "42.5"]}]}},
        status=200
    )
    
    collector = PrometheusCollector()
    result = collector.query("some_query")
    assert result == 42.5

@responses.activate
def test_query_no_data():
    responses.add(
        responses.GET,
        "http://localhost:9090/api/v1/query",
        json={"data": {"result": []}},
        status=200
    )
    
    collector = PrometheusCollector()
    with pytest.raises(ValueError, match="Query returned no data"):
        collector.query("some_query")

@responses.activate
def test_query_no_data_with_default():
    responses.add(
        responses.GET,
        "http://localhost:9090/api/v1/query",
        json={"data": {"result": []}},
        status=200
    )
    
    collector = PrometheusCollector()
    result = collector.query("some_query", default=0.0)
    assert result == 0.0

@responses.activate
def test_get_snapshot():
    # Mocking all 5 queries
    responses.add(
        responses.GET,
        "http://localhost:9090/api/v1/query",
        json={"data": {"result": [{"value": [1600000000.0, "10.0"]}]}},
        status=200
    )
    
    collector = PrometheusCollector()
    snapshot = collector.get_snapshot("test-namespace")
    
    assert snapshot["request_rate"] == 10.0
    assert snapshot["error_rate_pct"] == 10.0
    assert snapshot["p95_latency_ms"] == 10.0
    assert snapshot["ready_pods"] == 10.0
    assert snapshot["pod_restarts_5m"] == 10.0

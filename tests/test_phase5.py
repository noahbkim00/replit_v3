from scripts.load_test import RequestResult, build_parser, summarize_results


def test_summarize_results_reports_latency_percentiles_and_rates():
    results = [
        RequestResult(status_code=200, latency_ms=10.0, error_type=None),
        RequestResult(status_code=200, latency_ms=20.0, error_type=None),
        RequestResult(status_code=429, latency_ms=30.0, error_type="rate_limit_exceeded"),
        RequestResult(status_code=500, latency_ms=40.0, error_type="upstream_error"),
    ]

    summary = summarize_results(
        results=results,
        elapsed_seconds=0.5,
        usage_events_before=7,
        usage_events_after=9,
    )

    assert summary.total_requests == 4
    assert summary.successful_requests == 2
    assert summary.requests_per_second == 8.0
    assert summary.p50_latency_ms == 25.0
    assert summary.p95_latency_ms == 40.0
    assert summary.p99_latency_ms == 40.0
    assert summary.error_rate == 0.5
    assert summary.limit_rejection_rate == 0.25
    assert summary.usage_event_count == 2


def test_summarize_results_handles_empty_results():
    summary = summarize_results(
        results=[],
        elapsed_seconds=0.0,
        usage_events_before=3,
        usage_events_after=3,
    )

    assert summary.total_requests == 0
    assert summary.requests_per_second == 0.0
    assert summary.p50_latency_ms == 0.0
    assert summary.error_rate == 0.0
    assert summary.limit_rejection_rate == 0.0
    assert summary.usage_event_count == 0


def test_load_test_parser_supports_proxy_and_real_ollama_modes():
    parser = build_parser()

    proxy_args = parser.parse_args(
        [
            "--mode",
            "proxy-overhead",
            "--requests",
            "25",
            "--concurrency",
            "5",
            "--set-request-limit",
            "10",
        ]
    )
    real_args = parser.parse_args(["--mode", "real-ollama", "--model", "llama3.2:1b"])

    assert proxy_args.mode == "proxy-overhead"
    assert proxy_args.requests == 25
    assert proxy_args.concurrency == 5
    assert proxy_args.set_request_limit == 10
    assert real_args.mode == "real-ollama"
    assert real_args.model == "llama3.2:1b"

from scripts.demo_load_test import RequestResult, build_parser, summarize_results


def test_summarize_results_reports_latency_percentiles_and_rates():
    results = [
        RequestResult(status_code=200, latency_ms=10.0, error_type=None),
        RequestResult(status_code=200, latency_ms=20.0, error_type=None),
        RequestResult(status_code=429, latency_ms=30.0, error_type="rate_limit_exceeded"),
        RequestResult(status_code=500, latency_ms=40.0, error_type="upstream_error"),
    ]

    summary = summarize_results(
        scenario="unit",
        results=results,
        elapsed_seconds=0.5,
        usage_events_before=7,
        usage_events_after=9,
        usage_requests_before=10,
        usage_requests_after=12,
    )

    assert summary.total_requests == 4
    assert summary.successful_requests == 2
    assert summary.limit_rejections == 1
    assert summary.other_failures == 1
    assert summary.requests_per_second == 8.0
    assert summary.p50_latency_ms == 25.0
    assert summary.p95_latency_ms == 40.0
    assert summary.p99_latency_ms == 40.0
    assert summary.error_rate == 0.5
    assert summary.limit_rejection_rate == 0.25
    assert summary.usage_event_count == 2
    assert summary.usage_request_count_delta == 2
    assert summary.pass_ is False


def test_summarize_results_handles_empty_results():
    summary = summarize_results(
        scenario="empty",
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
    assert summary.pass_ is True


def test_load_test_parser_supports_proxy_and_limited_scenario_options():
    parser = build_parser()

    args = parser.parse_args(
        [
            "--requests",
            "25",
            "--concurrency",
            "5",
            "--limited-allowed",
            "10",
        ]
    )

    assert args.requests == 25
    assert args.concurrency == 5
    assert args.limited_allowed == 10
    assert args.model == "llama3.2:1b"

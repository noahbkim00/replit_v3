import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from math import ceil
from statistics import median
from time import perf_counter
from typing import Any

try:
    from demo_helpers import (
        DemoFailure,
        build_openai_client,
        clear_limits,
        ensure_fresh_limit_window,
        error_type_from_exception,
        get_usage,
        get_usage_events,
        http_client,
        preflight_models,
        set_limits,
        text_messages,
        usage_request_count,
    )
except ModuleNotFoundError:
    from scripts.demo_helpers import (
        DemoFailure,
        build_openai_client,
        clear_limits,
        ensure_fresh_limit_window,
        error_type_from_exception,
        get_usage,
        get_usage_events,
        http_client,
        preflight_models,
        set_limits,
        text_messages,
        usage_request_count,
    )


@dataclass(frozen=True)
class RequestResult:
    status_code: int | None
    latency_ms: float
    error_type: str | None


@dataclass(frozen=True)
class UsageSnapshot:
    event_count: int
    request_count: int
    total_tokens: int


@dataclass(frozen=True)
class LoadTestSummary:
    scenario: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    limit_rejections: int
    other_failures: int
    requests_per_second: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    limit_rejection_rate: float
    usage_event_count: int
    usage_request_count_delta: int
    pass_: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run no-limit and high-but-binding OpenAI-client load demos."
    )
    parser.add_argument("--proxy-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="dev-token-demo-load-open")
    parser.add_argument("--user-id", default="demo_load_open")
    parser.add_argument("--limited-api-key", default="dev-token-demo-load-limited")
    parser.add_argument("--admin-api-key", default="dev-token-admin")
    parser.add_argument("--limited-user-id", default="demo_load_limited")
    parser.add_argument("--model", default="llama3.2:1b")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--limited-allowed", type=int, default=100)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    return parser


def summarize_results(
    *,
    scenario: str,
    results: list[RequestResult],
    elapsed_seconds: float,
    usage_events_before: int,
    usage_events_after: int,
    usage_requests_before: int = 0,
    usage_requests_after: int = 0,
    expected_successes: int | None = None,
    expected_limit_rejections: int | None = None,
) -> LoadTestSummary:
    total_requests = len(results)
    successful_requests = sum(
        1
        for result in results
        if result.status_code is not None and 200 <= result.status_code < 300
    )
    limit_rejections = sum(
        1
        for result in results
        if result.status_code == 429 or result.error_type == "rate_limit_exceeded"
    )
    failed_requests = total_requests - successful_requests
    other_failures = failed_requests - limit_rejections
    usage_event_count = max(usage_events_after - usage_events_before, 0)
    usage_request_count_delta = max(usage_requests_after - usage_requests_before, 0)
    latencies = [result.latency_ms for result in results]
    pass_value = other_failures == 0 and usage_request_count_delta == successful_requests
    if expected_successes is not None:
        pass_value = pass_value and successful_requests == expected_successes
    if expected_limit_rejections is not None:
        pass_value = pass_value and limit_rejections == expected_limit_rejections

    return LoadTestSummary(
        scenario=scenario,
        total_requests=total_requests,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        limit_rejections=limit_rejections,
        other_failures=other_failures,
        requests_per_second=_safe_div(total_requests, elapsed_seconds),
        p50_latency_ms=_p50(latencies),
        p95_latency_ms=_nearest_rank_percentile(latencies, 95),
        p99_latency_ms=_nearest_rank_percentile(latencies, 99),
        error_rate=_safe_div(failed_requests, total_requests),
        limit_rejection_rate=_safe_div(limit_rejections, total_requests),
        usage_event_count=usage_event_count,
        usage_request_count_delta=usage_request_count_delta,
        pass_=pass_value,
    )


async def run_requests(args: argparse.Namespace, api_key: str) -> list[RequestResult]:
    semaphore = asyncio.Semaphore(max(args.concurrency, 1))

    async def one_request(index: int) -> RequestResult:
        async with semaphore:
            return await asyncio.to_thread(send_chat_request, args, api_key, index)

    return await asyncio.gather(*(one_request(index) for index in range(max(args.requests, 0))))


def send_chat_request(args: argparse.Namespace, api_key: str, index: int) -> RequestResult:
    started_at = perf_counter()
    try:
        client = build_openai_client(args.proxy_url, api_key, args.timeout_seconds)
        client.chat.completions.create(
            model=args.model,
            messages=text_messages(f"load test {index}; reply with ok"),
            temperature=0,
            max_tokens=1,
        )
        status_code = 200
        error_type = None
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        error_type = error_type_from_exception(exc) or exc.__class__.__name__

    return RequestResult(
        status_code=status_code,
        latency_ms=(perf_counter() - started_at) * 1000,
        error_type=error_type,
    )


def usage_snapshot(client, api_key: str) -> UsageSnapshot:
    events = get_usage_events(client, api_key).get("events", [])
    usage = get_usage(client, api_key)
    aggregate = usage.get("aggregate", {})
    total_tokens = aggregate.get("total_tokens") if isinstance(aggregate, dict) else 0
    return UsageSnapshot(
        event_count=len(events) if isinstance(events, list) else 0,
        request_count=usage_request_count(usage),
        total_tokens=total_tokens if isinstance(total_tokens, int) else 0,
    )


def run_scenario(
    args: argparse.Namespace,
    *,
    scenario: str,
    api_key: str,
    expected_successes: int,
    expected_limit_rejections: int,
) -> LoadTestSummary:
    with http_client(args.proxy_url, args.timeout_seconds) as client:
        before = usage_snapshot(client, api_key)

    started_at = perf_counter()
    results = asyncio.run(run_requests(args, api_key))
    elapsed_seconds = perf_counter() - started_at

    with http_client(args.proxy_url, args.timeout_seconds) as client:
        after = usage_snapshot(client, api_key)

    return summarize_results(
        scenario=scenario,
        results=results,
        elapsed_seconds=elapsed_seconds,
        usage_events_before=before.event_count,
        usage_events_after=after.event_count,
        usage_requests_before=before.request_count,
        usage_requests_after=after.request_count,
        expected_successes=expected_successes,
        expected_limit_rejections=expected_limit_rejections,
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.limited_allowed >= args.requests:
            raise DemoFailure("--limited-allowed must be lower than --requests")
        preflight_models(
            proxy=args.proxy_url,
            api_key=args.api_key,
            required_models=[args.model],
            timeout_seconds=args.timeout_seconds,
        )
        preflight_models(
            proxy=args.proxy_url,
            api_key=args.limited_api_key,
            required_models=[args.model],
            timeout_seconds=args.timeout_seconds,
        )

        with http_client(args.proxy_url, args.timeout_seconds) as client:
            clear_limits(client, args.admin_api_key, args.user_id)
            clear_limits(client, args.admin_api_key, args.limited_user_id)
            ensure_fresh_limit_window(client, args.limited_api_key, label="limited load scenario")

        no_limits = run_scenario(
            args,
            scenario="no_limits",
            api_key=args.api_key,
            expected_successes=args.requests,
            expected_limit_rejections=0,
        )
        print(_summary_json(no_limits))

        try:
            with http_client(args.proxy_url, args.timeout_seconds) as client:
                set_limits(
                    client,
                    args.admin_api_key,
                    args.limited_user_id,
                    requests_per_minute=args.limited_allowed,
                )

            limited = run_scenario(
                args,
                scenario="limited",
                api_key=args.limited_api_key,
                expected_successes=args.limited_allowed,
                expected_limit_rejections=args.requests - args.limited_allowed,
            )
            print(_summary_json(limited, allowed=args.limited_allowed))
        finally:
            with http_client(args.proxy_url, args.timeout_seconds) as client:
                clear_limits(client, args.admin_api_key, args.limited_user_id)

        if not no_limits.pass_ or not limited.pass_:
            return 1
    except DemoFailure as exc:
        print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        return 1
    except Exception as exc:
        print(json.dumps({"pass": False, "error": f"{exc.__class__.__name__}: {exc}"}))
        return 1

    return 0


def _summary_json(summary: LoadTestSummary, **extra: Any) -> str:
    payload = asdict(summary)
    payload["pass"] = payload.pop("pass_")
    payload.update(extra)
    return json.dumps(payload, sort_keys=True)


def _p50(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(median(sorted(values)))


def _nearest_rank_percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = ceil((percentile / 100) * len(ordered)) - 1
    return float(ordered[min(max(index, 0), len(ordered) - 1)])


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


if __name__ == "__main__":
    sys.exit(main())

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from math import ceil
from statistics import median
from time import perf_counter
from typing import Any

import httpx


@dataclass(frozen=True)
class RequestResult:
    status_code: int | None
    latency_ms: float
    error_type: str | None


@dataclass(frozen=True)
class LoadTestSummary:
    total_requests: int
    successful_requests: int
    failed_requests: int
    limit_rejections: int
    requests_per_second: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    limit_rejection_rate: float
    usage_event_count: int


@dataclass(frozen=True)
class UsageSnapshot:
    event_count: int
    request_count: int
    total_tokens: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load test the FastAPI Ollama proxy through its OpenAI-compatible path."
    )
    parser.add_argument(
        "--mode",
        choices=("proxy-overhead", "real-ollama"),
        default="proxy-overhead",
        help="Label the run as a mock-upstream proxy overhead test or real Ollama test.",
    )
    parser.add_argument("--proxy-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="dev-token-user-a")
    parser.add_argument("--admin-token", default="dev-token-admin")
    parser.add_argument("--limit-user-id", default="user_a")
    parser.add_argument("--model", default="llama3.2:1b")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--set-request-limit",
        type=int,
        help="Set requests_per_minute for --limit-user-id before the run.",
    )
    parser.add_argument(
        "--clear-limits",
        action="store_true",
        help="Clear all configured limits for --limit-user-id before the run.",
    )
    return parser


def summarize_results(
    *,
    results: list[RequestResult],
    elapsed_seconds: float,
    usage_events_before: int,
    usage_events_after: int,
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
    latencies = [result.latency_ms for result in results]

    return LoadTestSummary(
        total_requests=total_requests,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        limit_rejections=limit_rejections,
        requests_per_second=_safe_div(total_requests, elapsed_seconds),
        p50_latency_ms=_p50(latencies),
        p95_latency_ms=_nearest_rank_percentile(latencies, 95),
        p99_latency_ms=_nearest_rank_percentile(latencies, 99),
        error_rate=_safe_div(failed_requests, total_requests),
        limit_rejection_rate=_safe_div(limit_rejections, total_requests),
        usage_event_count=max(usage_events_after - usage_events_before, 0),
    )


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


async def run_load_test(args: argparse.Namespace) -> tuple[LoadTestSummary, dict[str, Any]]:
    base_url = args.proxy_url.rstrip("/")
    timeout = httpx.Timeout(args.timeout_seconds)

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        if args.clear_limits:
            await _put_limits(client, args, None)
        if args.set_request_limit is not None:
            await _put_limits(client, args, args.set_request_limit)

        before = await _usage_snapshot(client, args.token)
        started_at = perf_counter()
        results = await _run_requests(client, args)
        elapsed_seconds = perf_counter() - started_at
        after = await _usage_snapshot(client, args.token)

    summary = summarize_results(
        results=results,
        elapsed_seconds=elapsed_seconds,
        usage_events_before=before.event_count,
        usage_events_after=after.event_count,
    )
    comparisons = {
        "usage_event_delta": after.event_count - before.event_count,
        "usage_request_count_delta": after.request_count - before.request_count,
        "usage_total_token_delta": after.total_tokens - before.total_tokens,
        "usage_events_match_successes": (
            after.event_count - before.event_count == summary.successful_requests
        ),
        "usage_totals_match_successes": (
            after.request_count - before.request_count == summary.successful_requests
        ),
    }
    return summary, comparisons


async def _run_requests(client: httpx.AsyncClient, args: argparse.Namespace) -> list[RequestResult]:
    queue: asyncio.Queue[int] = asyncio.Queue()
    for request_index in range(max(args.requests, 0)):
        queue.put_nowait(request_index)

    workers = [
        asyncio.create_task(_worker(client, args, queue))
        for _ in range(min(max(args.concurrency, 1), max(args.requests, 1)))
    ]

    results: list[RequestResult] = []
    for worker_results in await asyncio.gather(*workers):
        results.extend(worker_results)
    return results


async def _worker(
    client: httpx.AsyncClient, args: argparse.Namespace, queue: asyncio.Queue[int]
) -> list[RequestResult]:
    results: list[RequestResult] = []
    while True:
        try:
            request_index = queue.get_nowait()
        except asyncio.QueueEmpty:
            return results

        results.append(await _send_chat_request(client, args, request_index))
        queue.task_done()


async def _send_chat_request(
    client: httpx.AsyncClient, args: argparse.Namespace, request_index: int
) -> RequestResult:
    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": f"load test request {request_index}",
            }
        ],
        "max_tokens": max(args.max_tokens, 0),
        "temperature": 0,
    }
    started_at = perf_counter()
    try:
        response = await client.post(
            "/v1/chat/completions",
            headers=_auth_headers(args.token),
            json=payload,
        )
        latency_ms = (perf_counter() - started_at) * 1000
        return RequestResult(
            status_code=response.status_code,
            latency_ms=latency_ms,
            error_type=_error_type(response),
        )
    except httpx.HTTPError as exc:
        latency_ms = (perf_counter() - started_at) * 1000
        return RequestResult(
            status_code=None,
            latency_ms=latency_ms,
            error_type=exc.__class__.__name__,
        )


async def _usage_snapshot(client: httpx.AsyncClient, token: str) -> UsageSnapshot:
    events_response = await client.get("/usage/events", headers=_auth_headers(token))
    events_response.raise_for_status()
    events_payload = events_response.json()
    events = events_payload.get("events", [])
    event_count = len(events) if isinstance(events, list) else 0

    usage_response = await client.get("/usage", headers=_auth_headers(token))
    usage_response.raise_for_status()
    usage_payload = usage_response.json()
    aggregate = usage_payload.get("aggregate", {})
    return UsageSnapshot(
        event_count=event_count,
        request_count=_int_value(aggregate.get("request_count")),
        total_tokens=_int_value(aggregate.get("total_tokens")),
    )


async def _put_limits(
    client: httpx.AsyncClient, args: argparse.Namespace, requests_per_minute: int | None
) -> None:
    response = await client.put(
        f"/admin/users/{args.limit_user_id}/limits",
        headers=_auth_headers(args.admin_token),
        json={
            "requests_per_minute": requests_per_minute,
            "daily_tokens": None,
            "total_tokens": None,
        },
    )
    response.raise_for_status()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _error_type(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    error_type = error.get("type")
    return error_type if isinstance(error_type, str) else None


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _print_report(
    *, args: argparse.Namespace, summary: LoadTestSummary, comparisons: dict[str, Any]
) -> None:
    report = {
        "mode": args.mode,
        "proxy_url": args.proxy_url.rstrip("/"),
        "model": args.model,
        "configured_requests": args.requests,
        "configured_concurrency": args.concurrency,
        "summary": asdict(summary),
        "usage_comparison": comparisons,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


def main() -> None:
    args = build_parser().parse_args()
    summary, comparisons = asyncio.run(run_load_test(args))
    _print_report(args=args, summary=summary, comparisons=comparisons)


if __name__ == "__main__":
    main()

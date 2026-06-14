import argparse
import asyncio
import sys
from dataclasses import dataclass

from demo_helpers import (
    DemoFailure,
    add_common_args,
    build_openai_client,
    clear_limits,
    get_usage,
    get_usage_events,
    http_client,
    preflight_models,
    print_fail,
    print_pass,
    text_messages,
    usage_request_count,
)

USER_TOKENS = {
    "user_a": "dev-token-user-a",
    "user_b": "dev-token-user-b",
}


@dataclass(frozen=True)
class CallResult:
    user_id: str
    ok: bool
    error: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prove concurrent traffic remains isolated by user."
    )
    add_common_args(parser, include_admin=True, include_models=True)
    parser.add_argument("--requests-per-user", type=int, default=10)
    return parser


def send_chat(proxy_url: str, token: str, timeout_seconds: float, model: str, index: int) -> None:
    client = build_openai_client(proxy_url, token, timeout_seconds)
    client.chat.completions.create(
        model=model,
        messages=text_messages(f"concurrency request {index}; reply ok"),
        temperature=0,
        max_tokens=8,
    )


async def run_calls(args: argparse.Namespace) -> list[CallResult]:
    async def one_call(user_id: str, token: str, index: int) -> CallResult:
        try:
            await asyncio.to_thread(
                send_chat,
                args.proxy_url,
                token,
                args.timeout_seconds,
                args.text_model,
                index,
            )
            return CallResult(user_id=user_id, ok=True)
        except Exception as exc:
            return CallResult(user_id=user_id, ok=False, error=f"{exc.__class__.__name__}: {exc}")

    tasks = [
        one_call(user_id, token, index)
        for user_id, token in USER_TOKENS.items()
        for index in range(args.requests_per_user)
    ]
    return await asyncio.gather(*tasks)


def main() -> int:
    args = build_parser().parse_args()
    try:
        preflight_models(
            proxy=args.proxy_url,
            api_key=args.api_key,
            required_models=[args.text_model],
            timeout_seconds=args.timeout_seconds,
        )

        with http_client(args.proxy_url, args.timeout_seconds) as client:
            for user_id in USER_TOKENS:
                clear_limits(client, args.admin_api_key, user_id)
            before = {user_id: get_usage(client, token) for user_id, token in USER_TOKENS.items()}

        results = asyncio.run(run_calls(args))

        with http_client(args.proxy_url, args.timeout_seconds) as client:
            after = {user_id: get_usage(client, token) for user_id, token in USER_TOKENS.items()}
            events = {
                user_id: get_usage_events(client, token) for user_id, token in USER_TOKENS.items()
            }
            for user_id in USER_TOKENS:
                clear_limits(client, args.admin_api_key, user_id)

        for user_id in USER_TOKENS:
            user_results = [result for result in results if result.user_id == user_id]
            successes = sum(1 for result in user_results if result.ok)
            delta = usage_request_count(after[user_id]) - usage_request_count(before[user_id])
            if successes != args.requests_per_user or delta != args.requests_per_user:
                errors = [result.error for result in user_results if result.error]
                raise DemoFailure(
                    f"{user_id} expected {args.requests_per_user} successes/delta; "
                    f"successes={successes}, delta={delta}, errors={errors[:3]}"
                )
            print_pass(
                f"concurrency:{user_id}",
                sent=args.requests_per_user,
                successes=successes,
                usage_delta=delta,
            )

        isolation = all(
            all(event.get("user_id") == user_id for event in events[user_id].get("events", []))
            for user_id in USER_TOKENS
        )
        if not isolation:
            raise DemoFailure("usage events were not isolated by authenticated user")
        print_pass("concurrency:isolation")
    except DemoFailure as exc:
        print_fail("concurrency", str(exc))
        return 1
    except Exception as exc:
        print_fail("concurrency", f"{exc.__class__.__name__}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

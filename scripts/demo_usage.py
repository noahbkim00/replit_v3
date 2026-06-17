import argparse
import sys

from demo_helpers import (
    DemoFailure,
    add_common_args,
    build_openai_client,
    get_admin_usage,
    get_usage,
    get_usage_events,
    http_client,
    preflight_models,
    print_fail,
    print_pass,
    text_messages,
    usage_request_count,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prove usage APIs reflect real proxy traffic.")
    add_common_args(parser, include_admin=True, include_api_key=False)
    parser.add_argument("--usage-user-a-id", default="demo_usage_a")
    parser.add_argument("--usage-user-a-api-key", default="dev-token-demo-usage-a")
    parser.add_argument("--usage-user-b-id", default="demo_usage_b")
    parser.add_argument("--usage-user-b-api-key", default="dev-token-demo-usage-b")
    return parser


def user_tokens(args: argparse.Namespace) -> dict[str, str]:
    return {
        args.usage_user_a_id: args.usage_user_a_api_key,
        args.usage_user_b_id: args.usage_user_b_api_key,
    }


def main() -> int:
    args = build_parser().parse_args()
    tokens = user_tokens(args)
    try:
        preflight_models(
            proxy=args.proxy_url,
            api_key=args.usage_user_a_api_key,
            required_models=[args.text_model],
            timeout_seconds=args.timeout_seconds,
        )

        with http_client(args.proxy_url, args.timeout_seconds) as client:
            before = {user_id: get_usage(client, token) for user_id, token in tokens.items()}

        for user_id, token in tokens.items():
            openai_client = build_openai_client(args.proxy_url, token, args.timeout_seconds)
            openai_client.chat.completions.create(
                model=args.text_model,
                messages=text_messages(f"Reply with the user id {user_id}."),
                temperature=0,
                max_tokens=16,
            )

        with http_client(args.proxy_url, args.timeout_seconds) as client:
            after = {user_id: get_usage(client, token) for user_id, token in tokens.items()}
            events = {user_id: get_usage_events(client, token) for user_id, token in tokens.items()}
            admin_user_a = get_admin_usage(client, args.admin_api_key, args.usage_user_a_id)

        for user_id, token in tokens.items():
            _ = token
            delta = usage_request_count(after[user_id]) - usage_request_count(before[user_id])
            scoped = all(
                event.get("user_id") == user_id for event in events[user_id].get("events", [])
            )
            if delta != 1 or not scoped:
                raise DemoFailure(f"{user_id} usage proof failed: delta={delta}, scoped={scoped}")
            print_pass(f"usage:{user_id}", request_count_delta=delta, events_user_scoped=scoped)

        if usage_request_count(admin_user_a) != usage_request_count(after[args.usage_user_a_id]):
            raise DemoFailure(
                f"admin usage view for {args.usage_user_a_id} does not match user usage aggregate"
            )
        print_pass("usage:admin_view", user_id=args.usage_user_a_id)
    except DemoFailure as exc:
        print_fail("usage", str(exc))
        return 1
    except Exception as exc:
        print_fail("usage", f"{exc.__class__.__name__}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

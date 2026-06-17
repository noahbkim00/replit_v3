import argparse
import sys

from demo_helpers import (
    DemoFailure,
    add_common_args,
    build_openai_client,
    clear_limits,
    ensure_fresh_limit_window,
    error_type_from_exception,
    get_limits,
    get_usage,
    http_client,
    preflight_models,
    print_fail,
    print_pass,
    set_limits,
    text_messages,
    usage_request_count,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prove admin request limits reject before billing."
    )
    add_common_args(parser, include_admin=True, api_key_default="dev-token-demo-limits")
    parser.add_argument("--user-id", default="demo_limits")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    limits_cleared = False
    try:
        preflight_models(
            proxy=args.proxy_url,
            api_key=args.api_key,
            required_models=[args.text_model],
            timeout_seconds=args.timeout_seconds,
        )
        openai_client = build_openai_client(args.proxy_url, args.api_key, args.timeout_seconds)
        with http_client(args.proxy_url, args.timeout_seconds) as client:
            clear_limits(client, args.admin_api_key, args.user_id)
            limits_cleared = True
            ensure_fresh_limit_window(client, args.api_key, label="limits demo")
            before = get_usage(client, args.api_key)

            set_limits(
                client,
                args.admin_api_key,
                args.user_id,
                requests_per_minute=1,
                daily_tokens=None,
                total_tokens=None,
            )
            configured = get_limits(client, args.admin_api_key, args.user_id)
            if configured.get("requests_per_minute") != 1:
                raise DemoFailure(f"limit was not set correctly: {configured}")
            print_pass("limits:set", requests_per_minute=1)

            openai_client.chat.completions.create(
                model=args.text_model,
                messages=text_messages("Reply with ok."),
                temperature=0,
                max_tokens=8,
            )
            print_pass("limits:first_call", status="success")

            try:
                openai_client.chat.completions.create(
                    model=args.text_model,
                    messages=text_messages("This call should be rejected."),
                    temperature=0,
                    max_tokens=8,
                )
            except Exception as exc:
                error_type = error_type_from_exception(exc)
                if error_type != "rate_limit_exceeded":
                    raise DemoFailure(f"second call failed with unexpected error: {exc}") from exc
                print_pass("limits:second_call", status=429, type=error_type)
            else:
                raise DemoFailure("second call unexpectedly succeeded")

            after = get_usage(client, args.api_key)
            request_count_delta = usage_request_count(after) - usage_request_count(before)
            if request_count_delta != 1:
                raise DemoFailure(
                    f"expected usage request-count delta 1, got {request_count_delta}"
                )
            print_pass("limits:usage", request_count_delta=request_count_delta)
    except DemoFailure as exc:
        print_fail("limits", str(exc))
        return 1
    except Exception as exc:
        print_fail("limits", f"{exc.__class__.__name__}: {exc}")
        return 1
    finally:
        if limits_cleared:
            try:
                with http_client(args.proxy_url, args.timeout_seconds) as client:
                    clear_limits(client, args.admin_api_key, args.user_id)
            except Exception as exc:
                print_fail("limits:cleanup", f"{exc.__class__.__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

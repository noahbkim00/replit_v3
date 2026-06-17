import argparse
import sys
from pathlib import Path

from demo_helpers import (
    DemoFailure,
    add_common_args,
    auth_headers,
    build_openai_client,
    clear_limits,
    http_client,
    preflight_models,
    print_fail,
    print_pass,
    set_limits,
    text_messages,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and fetch the HTML usage report.")
    add_common_args(
        parser,
        include_admin=True,
        api_key_default="dev-token-demo-report",
    )
    parser.add_argument("--user-id", default="demo_report")
    parser.add_argument("--output", default="/tmp/replit-v3-usage-report.html")
    parser.add_argument("--admin-output", default="/tmp/replit-v3-admin-usage-report.html")
    return parser


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
            clear_limits(client, args.admin_api_key, args.user_id)
            set_limits(
                client,
                args.admin_api_key,
                args.user_id,
                requests_per_minute=10,
                daily_tokens=500,
                total_tokens=2000,
            )

        openai_client = build_openai_client(args.proxy_url, args.api_key, args.timeout_seconds)
        openai_client.chat.completions.create(
            model=args.text_model,
            messages=text_messages("Reply with only: usage report ready"),
            temperature=0,
            max_tokens=16,
        )

        with http_client(args.proxy_url, args.timeout_seconds) as client:
            report_response = client.get("/usage/report", headers=auth_headers(args.api_key))
            report_response.raise_for_status()
            admin_response = client.get(
                "/admin/usage/report", headers=auth_headers(args.admin_api_key)
            )
            admin_response.raise_for_status()
            browser_response = client.get("/usage/report/browser")
            browser_response.raise_for_status()

        if "text/html" not in report_response.headers.get("content-type", ""):
            raise DemoFailure("user report did not return HTML")
        if "text/html" not in browser_response.headers.get("content-type", ""):
            raise DemoFailure("browser report shell did not return HTML")
        if args.user_id not in report_response.text or "Total tokens" not in report_response.text:
            raise DemoFailure("user report missing expected usage labels")
        if args.user_id not in admin_response.text or "Associated Users" not in admin_response.text:
            raise DemoFailure("admin report missing associated user data")

        output_path = Path(args.output)
        output_path.write_text(report_response.text, encoding="utf-8")
        admin_output_path = Path(args.admin_output)
        admin_output_path.write_text(admin_response.text, encoding="utf-8")
        browser_url = f"{args.proxy_url.rstrip('/')}/usage/report/browser"

        print_pass(
            "usage-report:user",
            user_id=args.user_id,
            output=output_path,
            url=f"{args.proxy_url.rstrip('/')}/usage/report",
        )
        print_pass(
            "usage-report:admin",
            user_id=args.user_id,
            output=admin_output_path,
            url=f"{args.proxy_url.rstrip('/')}/admin/usage/report",
        )
        print_pass("usage-report:browser", url=browser_url)
    except DemoFailure as exc:
        print_fail("usage-report", str(exc))
        return 1
    except Exception as exc:
        print_fail("usage-report", f"{exc.__class__.__name__}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

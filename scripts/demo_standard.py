import argparse
import sys

from demo_helpers import (
    DemoFailure,
    add_common_args,
    build_openai_client,
    fetch_image_data_url,
    preflight_models,
    print_fail,
    print_pass,
    text_messages,
    usage_total_tokens,
    vision_messages,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run text and vision non-streaming OpenAI-compatible calls through the proxy."
    )
    add_common_args(parser)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        preflight_models(
            proxy=args.proxy_url,
            api_key=args.api_key,
            required_models=[args.text_model, args.vision_model],
            timeout_seconds=args.timeout_seconds,
        )
        client = build_openai_client(args.proxy_url, args.api_key, args.timeout_seconds)

        text_response = client.chat.completions.create(
            model=args.text_model,
            messages=text_messages("Answer in one word: what is 2+2?"),
            temperature=0,
            max_tokens=16,
        )
        text_content = text_response.choices[0].message.content or ""
        print_pass(
            "standard:text",
            model=args.text_model,
            total_tokens=usage_total_tokens(text_response.usage),
            snippet=repr(text_content[:80]),
        )

        image_data_url = fetch_image_data_url(
            "https://picsum.photos/seed/replit-v3-standard/320/240",
            args.timeout_seconds,
        )
        vision_response = client.chat.completions.create(
            model=args.vision_model,
            messages=vision_messages("Describe this image in one short sentence.", image_data_url),
            temperature=0,
            max_tokens=64,
        )
        vision_content = vision_response.choices[0].message.content or ""
        print_pass(
            "standard:vision",
            model=args.vision_model,
            total_tokens=usage_total_tokens(vision_response.usage),
            snippet=repr(vision_content[:80]),
        )
    except DemoFailure as exc:
        print_fail("standard", str(exc))
        return 1
    except Exception as exc:
        print_fail("standard", f"{exc.__class__.__name__}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

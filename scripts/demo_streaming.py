import argparse
import sys
from typing import Any

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
        description="Run text and vision streaming OpenAI-compatible calls through the proxy."
    )
    add_common_args(parser)
    return parser


def run_stream(client, *, model: str, messages: list[dict[str, Any]]) -> tuple[int, int | None]:
    chunks = 0
    final_usage = None
    for chunk in client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=64,
        stream=True,
        stream_options={"include_usage": True},
    ):
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                chunks += 1
                print(delta, end="", flush=True)
        if getattr(chunk, "usage", None) is not None:
            final_usage = chunk.usage
    print()
    return chunks, usage_total_tokens(final_usage)


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

        text_chunks, text_tokens = run_stream(
            client,
            model=args.text_model,
            messages=text_messages("Count from one to three, separated by commas."),
        )
        if text_chunks == 0:
            raise DemoFailure("text stream completed without content")
        print_pass("streaming:text", chunks=text_chunks, usage_total_tokens=text_tokens)

        image_data_url = fetch_image_data_url(
            "https://picsum.photos/seed/replit-v3-streaming/320/240",
            args.timeout_seconds,
        )
        vision_chunks, vision_tokens = run_stream(
            client,
            model=args.vision_model,
            messages=vision_messages("Describe this image briefly.", image_data_url),
        )
        if vision_chunks == 0:
            raise DemoFailure("vision stream completed without content")
        print_pass("streaming:vision", chunks=vision_chunks, usage_total_tokens=vision_tokens)
    except DemoFailure as exc:
        print_fail("streaming", str(exc))
        return 1
    except Exception as exc:
        print_fail("streaming", f"{exc.__class__.__name__}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Preflight check: prove credentials, workspace and model before a paid run.

    python -m settle.doctor

Costs a handful of tokens and saves finding out twelve cases in.
"""
from __future__ import annotations

import argparse
import os
import sys

from .llm import _load_dotenv, preflight, provider


def _list_models() -> None:
    """Ask the endpoint what it serves. Removes the guesswork from SETTLE_MODEL."""
    import json
    import urllib.error
    import urllib.request

    from .llm import provider

    if provider() == "openai":
        base = os.environ.get("SETTLE_BASE_URL", "").rstrip("/")
        key = os.environ.get("SETTLE_API_KEY", "")
        if not base or not key:
            print("Set SETTLE_BASE_URL and SETTLE_API_KEY in .env first.")
            return
        from .llm import HTTP_HEADERS
        req = urllib.request.Request(
            f"{base}/models",
            headers={**HTTP_HEADERS, "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            print(f"HTTP {exc.code}: {detail}")
            if exc.code == 403:
                print("\n  A 403 here is usually bot protection rather than a bad "
                      "key.\n  Check the key is correct and that SETTLE_BASE_URL "
                      "ends in /v1.\n  If it persists, the endpoint may be blocking "
                      "this network.")
            elif exc.code == 401:
                print("\n  401 means the key was read but rejected. Re-copy it "
                      "from the provider.")
            return
        ids = sorted(m.get("id", "") for m in data.get("data", []))
        print(f"{len(ids)} models available at {base}\n")
        for i in ids:
            print(f"  {i}")
        print("\nPut one of these in .env as SETTLE_MODEL.")
        print("Pick a small/cheap one -- the calls are short and structured.")
        return

    print("--list-models currently supports SETTLE_PROVIDER=openai endpoints.")
    print("For Anthropic, see https://platform.claude.com/settings/keys")


def main() -> None:
    _load_dotenv()
    ap = argparse.ArgumentParser(description="Check API access before a paid run.")
    ap.add_argument("--model", default=os.environ.get("SETTLE_MODEL", "claude-sonnet-4-6"))
    ap.add_argument("--list-models", action="store_true",
                    help="ask the endpoint which models this key can use, so "
                         "SETTLE_MODEL does not have to be guessed")
    args = ap.parse_args()

    if args.list_models:
        _list_models()
        return

    print("Settle preflight\n")
    if provider() == "openai":
        key = os.environ.get("SETTLE_API_KEY", "")
        print(f"  provider   openai-compatible")
        print(f"  endpoint   {os.environ.get('SETTLE_BASE_URL', 'NOT SET')}")
        print(f"  api key    {'set (' + key[:10] + '...)' if key else 'NOT SET'}")
    else:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        ws = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
        print(f"  provider   anthropic")
        print(f"  api key    {'set (' + key[:14] + '...)' if key else 'NOT SET'}")
        print(f"  workspace  {ws if ws else '(not set)'}")
    print(f"  model      {args.model}")
    print("\n  calling the API ...\n")

    ok, detail = preflight(args.model)
    if ok:
        print("  OK\n")
        for line in detail.splitlines():
            print(f"  {line}")
        print("\nReady. Run the paid targets.")
        sys.exit(0)

    print("  FAILED\n")
    for line in detail.splitlines():
        print(f"  {line}")
    sys.exit(1)


if __name__ == "__main__":
    main()

"""Model access, usage accounting and trajectory capture.

Every model call in this project goes through `call_model`, which means every
call is priced and every call is logged to trajectories/ as JSONL. That is what
makes the agent's behaviour auditable after the fact.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Approximate list prices in USD per million tokens. Override with
# SETTLE_PRICE_IN / SETTLE_PRICE_OUT if yours differ; the number is reported as
# an estimate, not a bill.
def _prices() -> dict:
    return {"in": float(os.environ.get("SETTLE_PRICE_IN", "3.0")),
            "out": float(os.environ.get("SETTLE_PRICE_OUT", "15.0"))}

_TRACE: Path | None = None
_client = None


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env loader so `cp .env.example .env` actually takes effect.

    No dependency on python-dotenv. Existing environment variables always win,
    so `SETTLE_MODEL=x python -m settle.agent ...` still overrides the file.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def set_trace(path: Path | None) -> None:
    global _TRACE
    _TRACE = path
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)


def _log(record: dict) -> None:
    if _TRACE is None:
        return
    with _TRACE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def trace_event(kind: str, **payload) -> None:
    """Record a non-model step (tool call, gate result, human checkpoint)."""
    _log({"ts": time.time(), "type": kind, **payload})


# --------------------------------------------------------------------------
# Provider selection.
#
# The adjudicator and verifier ask for one small JSON object and nothing else,
# so they are genuinely model-agnostic. Any OpenAI-compatible endpoint works,
# which includes several with free tiers. Set:
#
#   SETTLE_PROVIDER=openai
#   SETTLE_BASE_URL=https://api.groq.com/openai/v1
#   SETTLE_API_KEY=...
#   SETTLE_MODEL=<a model that endpoint serves>
#
# Default remains the Anthropic API.
# --------------------------------------------------------------------------

def provider() -> str:
    return os.environ.get("SETTLE_PROVIDER", "anthropic").strip().lower()


# Some endpoints sit behind bot protection that rejects urllib's default
# User-Agent with an HTTP 403 (Cloudflare error 1010). Identify ourselves.
HTTP_HEADERS = {
    "User-Agent": "settle-reconciliation/1.0 (+https://github.com/)",
    "Accept": "application/json",
}


def _openai_compat_call(model: str, system: str, user: str,
                        max_tokens: int) -> tuple[str, dict]:
    """Minimal OpenAI-compatible chat call over stdlib http."""
    import json as _json
    import urllib.error
    import urllib.request

    base = os.environ.get("SETTLE_BASE_URL", "").rstrip("/")
    key = os.environ.get("SETTLE_API_KEY", "")
    if not base:
        raise RuntimeError("SETTLE_PROVIDER=openai requires SETTLE_BASE_URL")
    if not key:
        raise RuntimeError("SETTLE_PROVIDER=openai requires SETTLE_API_KEY")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    # Reasoning models (gpt-oss and similar) spend part of the budget thinking
    # before emitting content. With a tight max_tokens the visible answer comes
    # back empty. Give these endpoints headroom, and cap reasoning effort where
    # the endpoint understands the parameter.
    payload = {"model": model, "messages": messages,
               "max_tokens": max(max_tokens, 1024) * 2}
    effort = os.environ.get("SETTLE_REASONING_EFFORT", "").strip()
    if effort:
        payload["reasoning_effort"] = effort
    body = _json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body,
        headers={**HTTP_HEADERS,
                 "Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = _json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code} from {base}: {detail}") from None

    msg = data["choices"][0].get("message", {}) or {}
    text = msg.get("content") or ""
    if not text.strip():
        # Some endpoints put everything in a separate reasoning channel when the
        # content budget runs out. The JSON we need is often still in there.
        text = msg.get("reasoning") or msg.get("reasoning_content") or ""
    u = data.get("usage", {}) or {}
    usage = {"input_tokens": u.get("prompt_tokens", 0),
             "output_tokens": u.get("completion_tokens", 0),
             "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0}
    return text, usage


def _get_client():
    """Build the client, including the workspace header when one is configured.

    A multi-workspace or identity-linked API key must name the workspace it acts
    in on every request; without it the API returns 400 before doing any work.
    """
    global _client
    if _client is None:
        import anthropic
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and "
                "fill it in, or run `make core` for the model-free ablation.")
        headers = {}
        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
        if workspace:
            headers["anthropic-workspace-id"] = workspace
        _client = (anthropic.Anthropic(default_headers=headers) if headers
                   else anthropic.Anthropic())
    return _client


WORKSPACE_HINT = """
Your API key is linked to more than one workspace, so every request must name
the workspace it acts in.

Two ways to fix it. The second is simpler and is what I would do:

  1. Set the right workspace ID. Find it at
     https://platform.claude.com/settings/workspaces
     It looks like wrkspc_01JwQvzr7rXLA5AGx3HKfFUJ. Put it in .env as
     ANTHROPIC_WORKSPACE_ID=wrkspc_...

  2. Create an API key scoped to a SINGLE workspace. A single-workspace key
     always runs in the workspace it was created for, so no header is needed
     at all -- delete ANTHROPIC_WORKSPACE_ID from .env entirely.

Nothing was charged for the rejected requests.
"""

CREDIT_HINT = """
Authentication is working -- the account simply has no credit.

Two options:

  1. Add credit at https://platform.claude.com/settings/billing
     The complete run costs about $1.19 (see: make estimate), so the smallest
     top-up is far more than enough.

  2. Run against a free OpenAI-compatible endpoint instead. The adjudicator and
     verifier ask for one small JSON object, so they are model-agnostic. In
     .env set:

         SETTLE_PROVIDER=openai
         SETTLE_BASE_URL=https://<your-endpoint>/v1
         SETTLE_API_KEY=<that provider's key>
         SETTLE_MODEL=<a model that endpoint serves>
         SETTLE_PRICE_IN=0
         SETTLE_PRICE_OUT=0

     Then re-run `doctor`. Record which model you used in the README -- the
     comparison stays fair as long as the baseline and Settle use the same one.
"""

WORKSPACE_NOT_FOUND_HINT = """
The workspace ID was sent and accepted as well-formed, but it does not resolve
to a workspace this key can act in. Usually one of:

  - the ID belongs to a different organization
  - your account has not been added to that workspace
  - a character was dropped when copying it

Two ways forward. The second is simpler:

  1. Re-copy the ID from https://platform.claude.com/settings/workspaces
     Open the workspace you intend to bill, and confirm you are a member of it.

  2. Create an API key scoped to that SINGLE workspace instead. A
     single-workspace key always runs where it was created, so no header is
     needed -- delete ANTHROPIC_WORKSPACE_ID from .env entirely and just use
     the new key.

Nothing was charged for the rejected requests.
"""


def preflight(model: str) -> tuple[bool, str]:
    """One cheap call to prove auth and the model string work.

    Worth a few tokens: without it the first real failure arrives twelve cases
    into a paid run.
    """
    if provider() == "openai":
        base = os.environ.get("SETTLE_BASE_URL", "(not set)")
        try:
            text, usage = _openai_compat_call(
                model, "", "Reply with the word: ok", 256)
            reply = text.strip()
            if not reply:
                return False, (
                    f"endpoint {base}\n"
                    f"model    {model}\n\n"
                    "The call succeeded but returned no text. This usually means "
                    "a reasoning model spent its whole budget thinking.\n"
                    "Try a non-reasoning model from `models`, or set "
                    "SETTLE_REASONING_EFFORT=low in .env.")
            return True, (f"provider   openai-compatible\n"
                          f"endpoint   {base}\n"
                          f"model      {model}\n"
                          f"reply      {reply[:40]!r}")
        except Exception as exc:                                # noqa: BLE001
            return False, f"endpoint {base}\n\n{str(exc)[:600]}"

    try:
        client = _get_client()
    except RuntimeError as exc:
        return False, str(exc)

    try:
        resp = client.messages.with_raw_response.create(
            model=model, max_tokens=8,
            messages=[{"role": "user", "content": "Reply with the word: ok"}])
        ws = resp.headers.get("anthropic-workspace-id", "(not reported)")
        org = resp.headers.get("anthropic-organization-id", "(not reported)")
        return True, (f"model      {model}\n"
                      f"workspace  {ws}\n"
                      f"org        {org}")
    except Exception as exc:                                    # noqa: BLE001
        msg = str(exc)
        # Order matters: a bad workspace also returns 404, and reporting it as a
        # model problem sends you chasing the wrong thing.
        if "anthropic-workspace-id" in msg:
            return False, "Workspace header required." + WORKSPACE_HINT
        if "orkspace" in msg and ("not found" in msg or "not_found" in msg):
            return False, ("Workspace not found." + WORKSPACE_NOT_FOUND_HINT
                           + f"\nRaw error:\n{msg[:300]}")
        if "not_found" in msg or "404" in msg:
            return False, (f"The model string {model!r} was rejected. Check "
                           f"SETTLE_MODEL in .env against the models your key "
                           f"can reach.\n\n{msg[:300]}")
        if "credit balance is too low" in msg:
            return False, ("No credit on the account." + CREDIT_HINT
                           + f"\nRaw error:\n{msg[:220]}")
        if "authentication" in msg.lower() or "401" in msg:
            return False, f"Authentication failed. Check ANTHROPIC_API_KEY.\n\n{msg[:300]}"
        return False, msg[:600]


MAX_ATTEMPTS = 4
BACKOFF_BASE = 4.0

# Free tiers cap requests per minute. Spacing calls is cheaper than absorbing
# 429s and backing off: set SETTLE_MIN_INTERVAL to the seconds between calls
# your tier allows (e.g. 2.0 for a 30 RPM limit).
_last_call_at = 0.0
_token_log: list[tuple[float, int]] = []   # (timestamp, tokens) over the last minute


def _throttle(est_tokens: int = 0) -> None:
    """Space requests by count and, if configured, by tokens per minute.

    Free tiers usually cap tokens per minute, not just requests. Sleeping a
    fixed interval does not help when a single request is larger than the
    minute's whole budget -- that has to be caught before it is sent.
    """
    global _last_call_at

    tpm = int(float(os.environ.get("SETTLE_TPM", "0") or 0))
    if tpm > 0 and est_tokens > 0:
        while True:
            now = time.time()
            _token_log[:] = [(t, n) for t, n in _token_log if now - t < 60]
            used = sum(n for _, n in _token_log)
            if used + est_tokens <= tpm or not _token_log:
                break
            wait = 61 - (now - _token_log[0][0])
            if wait <= 0:
                break
            print(f"    . {used:,}/{tpm:,} tokens used this minute, "
                  f"waiting {wait:.0f}s")
            time.sleep(wait)
        _token_log.append((time.time(), est_tokens))

    gap = float(os.environ.get("SETTLE_MIN_INTERVAL", "0") or 0)
    if gap > 0:
        wait = gap - (time.time() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
    _last_call_at = time.time()


def _est_tokens(system: str, user: str, max_tokens: int) -> int:
    return int((len(system) + len(user)) / 3.6) + max_tokens


def check_request_size(system: str, user: str, max_tokens: int) -> str | None:
    """Return a message if this request cannot fit the configured TPM cap."""
    tpm = int(float(os.environ.get("SETTLE_TPM", "0") or 0))
    if tpm <= 0:
        return None
    need = _est_tokens(system, user, max_tokens)
    if need > tpm:
        return (f"request needs ~{need:,} tokens but the per-minute cap is "
                f"{tpm:,}; no amount of waiting makes this fit")
    return None


def call_model(model: str, system: str, user: str, *, max_tokens: int = 2000,
               role: str = "model") -> tuple[str, dict]:
    """One model call, retried on transient failures.

    Sampling parameters are deliberately not passed: the current SDK does not
    accept `temperature` on messages.create, and the pipeline does not depend on
    it -- the ledger gate is what makes the output trustworthy, not determinism
    in the model.
    """
    if provider() == "openai":
        _throttle(_est_tokens(system, user, max_tokens))
        t0 = time.time()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                text, usage = _openai_compat_call(model, system, user, max_tokens)
                break
            except RuntimeError as exc:
                # 413 means the request itself is too big for the tier. No
                # amount of backoff changes that, so fail fast and say so.
                retryable = ("HTTP 413" not in str(exc)
                             and any(c in str(exc) for c in
                                     ("HTTP 429", "HTTP 500", "HTTP 502",
                                      "HTTP 503", "HTTP 529")))
                if not retryable or attempt == MAX_ATTEMPTS:
                    raise
                wait = BACKOFF_BASE * (2 ** (attempt - 1))
                print(f"    ! {str(exc)[:60]} (attempt {attempt}), "
                      f"retrying in {wait:.0f}s")
                time.sleep(wait)
        _log({"ts": t0, "type": "model_call", "role": role, "model": model,
              "provider": "openai_compat",
              "elapsed_s": round(time.time() - t0, 2), "usage": usage,
              "system": system[:2000], "user": user[:8000], "output": text[:8000]})
        return text, usage

    _throttle(_est_tokens(system, user, max_tokens))
    client = _get_client()
    kwargs = dict(model=model, max_tokens=max_tokens,
                  messages=[{"role": "user", "content": user}])
    if system:
        kwargs["system"] = system
        # The system prompt carries the whole forensics skill and is identical
        # on every call, so it is cached rather than re-sent. Cache reads are a
        # fraction of the input price, and the skill is ~1,180 tokens across
        # ~286 calls -- this is roughly half the run's input cost.
        if not os.environ.get("SETTLE_NO_CACHE"):
            kwargs["cache_control"] = {"type": "ephemeral"}

    t0 = time.time()
    resp = None
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = client.messages.create(**kwargs)
            break
        except Exception as exc:                                # noqa: BLE001
            last_exc = exc
            name = type(exc).__name__
            transient = any(k in name for k in
                            ("Overloaded", "RateLimit", "APIConnection",
                             "APITimeout", "InternalServer", "APIStatus"))
            if not transient or attempt == MAX_ATTEMPTS:
                _log({"ts": time.time(), "type": "model_error", "role": role,
                      "attempt": attempt, "error": f"{name}: {exc}"[:500]})
                raise
            wait = BACKOFF_BASE * (2 ** (attempt - 1))
            print(f"    ! {name} on attempt {attempt}/{MAX_ATTEMPTS}, "
                  f"retrying in {wait:.0f}s")
            _log({"ts": time.time(), "type": "model_retry", "role": role,
                  "attempt": attempt, "wait_s": wait, "error": f"{name}"[:200]})
            time.sleep(wait)
    if resp is None:                                            # pragma: no cover
        raise RuntimeError(f"model call failed after {MAX_ATTEMPTS} attempts: {last_exc}")
    elapsed = time.time() - t0

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    usage = {"input_tokens": resp.usage.input_tokens,
             "output_tokens": resp.usage.output_tokens,
             "cache_creation_input_tokens":
                 getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
             "cache_read_input_tokens":
                 getattr(resp.usage, "cache_read_input_tokens", 0) or 0}

    _log({"ts": t0, "type": "model_call", "role": role, "model": model,
          "elapsed_s": round(elapsed, 2), "usage": usage,
          "system": system[:2000], "user": user[:8000], "output": text[:8000]})
    return text, usage


# Cache writes cost more than a plain input token, cache reads far less.
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10


def price(model: str, usage: dict) -> float:
    p = _prices()
    return round(
        usage.get("input_tokens", 0) / 1e6 * p["in"]
        + usage.get("cache_creation_input_tokens", 0) / 1e6 * p["in"] * CACHE_WRITE_MULT
        + usage.get("cache_read_input_tokens", 0) / 1e6 * p["in"] * CACHE_READ_MULT
        + usage.get("output_tokens", 0) / 1e6 * p["out"], 6)


def parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.removesuffix("```").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(cleaned[start:end + 1])

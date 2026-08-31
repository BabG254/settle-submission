"""Cost estimator.

Builds the exact prompts each target would send, counts them, and prices the
run -- without calling the API. Run this before spending anything.

    python -m settle.estimate
    python -m settle.estimate --cases case01 case05 case12

Token counts are approximate (character-based). They are close enough to plan
with and are always reported as estimates, never as measured cost. The measured
number appears in results/RESULTS.md after a real run.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from .agent import (
    ADJUDICATOR_SYSTEM, ADJUDICATOR_USER, VERIFIER_SYSTEM, VERIFIER_USER,
    AUTO_ACCEPT_NAME, _fmt_candidates, _fmt_memory, _fmt_subsets, load_skill,
)
from .baselines import BASELINE_A_PROMPT, _csv
from .schema import read_case
from .tools import propose_candidates, subset_coherence, subset_solver

CHARS_PER_TOKEN = 3.6      # conservative for English + tabular text


def toks(s: str) -> int:
    return int(len(s) / CHARS_PER_TOKEN)


# Mirrors settle/llm.py: cache writes cost more than a plain input token,
# cache reads far less.
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10
CACHE_WRITES = 8          # two distinct system prompts, refreshed a few times


def _price(pin: int, pout: int, rate_in: float, rate_out: float) -> float:
    return pin / 1e6 * rate_in + pout / 1e6 * rate_out


def _price_cached(pin: int, pout: int, calls: int, cached_prefix: int,
                  rate_in: float, rate_out: float) -> float:
    """Same total tokens, but the identical system prefix is cached.

    The prefix is sent in full a handful of times (cache writes) and read from
    cache on every other call. This is what settle/llm.py actually does, so the
    estimate has to model it or it overstates the bill by roughly half.

    SETTLE_NO_CACHE disables caching in llm.py, so it must disable it here too --
    otherwise the estimate quotes a discount the run will not get.
    """
    if calls == 0 or os.environ.get("SETTLE_NO_CACHE"):
        return _price(pin, pout, rate_in, rate_out)
    writes = min(CACHE_WRITES, calls)
    reads = calls - writes
    cached_written = cached_prefix * writes
    cached_read = cached_prefix * reads
    variable = max(pin - cached_prefix * calls, 0)
    return (variable / 1e6 * rate_in
            + cached_written / 1e6 * rate_in * CACHE_WRITE_MULT
            + cached_read / 1e6 * rate_in * CACHE_READ_MULT
            + pout / 1e6 * rate_out)


def estimate_case(case_dir: Path, skill: str) -> dict:
    case = read_case(case_dir)

    # ---- baseline A: one call, whole statement
    inv_rows = [{"invoice_id": i.invoice_id, "customer_name": i.customer_name,
                 "amount": i.amount, "issue_date": i.issue_date} for i in case.invoices]
    txn_rows = [{"receipt": t.receipt, "datetime": t.datetime, "kind": t.kind,
                 "party_name": t.party_name, "party_phone": t.party_phone,
                 "paid_in": t.paid_in, "fee": t.fee, "withdrawn": t.withdrawn,
                 "narration": t.narration} for t in case.txns]
    a_in = toks(BASELINE_A_PROMPT.format(invoices=_csv(inv_rows),
                                         statement=_csv(txn_rows)))
    a_out = min(8000, 20 * len(case.invoices))

    # ---- Settle: walk every invoice, build the real prompts
    adj_in = adj_out = ver_in = ver_out = 0
    n_adj = n_ver = n_auto = 0
    fullctx_in = 0
    statement_dump = "\n".join(
        f"  {t.receipt} {t.datetime[:16]} {t.party_name[:28]:<28} "
        f"{t.paid_in:>8,} {t.fee:>5,} {t.kind}" for t in case.txns)

    for inv in case.invoices:
        cands = propose_candidates(inv, case.txns, memory=None)
        subsets = subset_solver(inv.amount, cands)
        if not subsets:
            continue
        if len(subsets) == 1:
            coh = subset_coherence(subsets[0], cands)
            if coh["same_payer_name"] and coh["min_name_score"] >= AUTO_ACCEPT_NAME:
                n_auto += 1
                continue                      # deterministic path: no model call

        user = ADJUDICATOR_USER.format(
            inv_id=inv.invoice_id, customer=inv.customer_name,
            cust_id=inv.customer_id, amount=inv.amount, issued=inv.issue_date,
            candidates=_fmt_candidates(cands),
            subsets=_fmt_subsets(subsets, cands),
            memory=_fmt_memory(cands, None))
        n_adj += 1
        adj_in += toks(ADJUDICATOR_SYSTEM.format(skill=skill)) + toks(user)
        adj_out += 180

        fullctx_in += (toks(ADJUDICATOR_SYSTEM.format(skill=skill))
                       + toks(user.replace(_fmt_candidates(cands), statement_dump)))

        # verifier runs on whatever the adjudicator matches; assume it matches
        n_ver += 1
        vuser = VERIFIER_USER.format(
            inv_id=inv.invoice_id, customer=inv.customer_name, amount=inv.amount,
            receipts=", ".join(subsets[0]), identity="X", reasoning="X" * 120,
            confidence=0.9, chosen="X" * 300,
            competing="\n".join("X" * 60 for _ in subsets[:4]))
        ver_in += toks(VERIFIER_SYSTEM.format(skill=skill)) + toks(vuser)
        ver_out += 90

    return {
        "case_id": case.case_id,
        "invoices": len(case.invoices),
        "txns": len(case.txns),
        "auto": n_auto,
        "adj_calls": n_adj, "ver_calls": n_ver,
        "a_in": a_in, "a_out": a_out,
        "adj_in": adj_in, "adj_out": adj_out,
        "ver_in": ver_in, "ver_out": ver_out,
        "fullctx_in": fullctx_in,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Project API cost before spending.")
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--cases", nargs="*", default=None)
    ap.add_argument("--rate-in", type=float,
                    default=float(os.environ.get("SETTLE_PRICE_IN", "3.0")))
    ap.add_argument("--rate-out", type=float,
                    default=float(os.environ.get("SETTLE_PRICE_OUT", "15.0")))
    args = ap.parse_args()

    dirs = sorted(d for d in args.data.iterdir()
                  if d.is_dir() and (d / "truth.json").exists()
                  and not d.name.startswith("month"))
    if args.cases:
        dirs = [d for d in dirs if d.name in args.cases]

    skill = load_skill()
    rows = [estimate_case(d, skill) for d in dirs]

    # The cached prefix is the whole system prompt: instructions + skill.
    prefix = toks(ADJUDICATOR_SYSTEM.format(skill=skill))
    cache_note = ("OFF (SETTLE_NO_CACHE set)" if os.environ.get("SETTLE_NO_CACHE")
                  else "ON")

    print(f"Estimated cost at ${args.rate_in}/M in, ${args.rate_out}/M out")
    print(f"Skill file: {toks(skill):,} tokens. System prefix: {prefix:,} tokens, "
          f"identical on every call.")
    print(f"Prompt caching: {cache_note}\n")
    print(f"  {'case':<9} {'inv':>4} {'txn':>5} {'auto':>5} {'adj':>4} {'ver':>4} "
          f"{'base A':>9} {'agent':>9}")
    tot = {k: 0 for k in ("a_in", "a_out", "adj_in", "adj_out", "ver_in",
                          "ver_out", "fullctx_in", "adj_calls", "ver_calls", "auto")}
    for r in rows:
        for k in tot:
            tot[k] += r[k]
        a = _price(r["a_in"], r["a_out"], args.rate_in, args.rate_out)
        g = _price_cached(r["adj_in"] + r["ver_in"], r["adj_out"] + r["ver_out"],
                          r["adj_calls"] + r["ver_calls"], prefix,
                          args.rate_in, args.rate_out)
        print(f"  {r['case_id']:<9} {r['invoices']:>4} {r['txns']:>5} "
              f"{r['auto']:>5} {r['adj_calls']:>4} {r['ver_calls']:>4} "
              f"${a:>8.3f} ${g:>8.3f}")

    agent_calls = tot["adj_calls"] + tot["ver_calls"]
    base_a = _price(tot["a_in"], tot["a_out"], args.rate_in, args.rate_out)
    agent_raw = _price(tot["adj_in"] + tot["ver_in"], tot["adj_out"] + tot["ver_out"],
                       args.rate_in, args.rate_out)
    agent = _price_cached(tot["adj_in"] + tot["ver_in"],
                          tot["adj_out"] + tot["ver_out"], agent_calls, prefix,
                          args.rate_in, args.rate_out)
    noverify = _price_cached(tot["adj_in"], tot["adj_out"], tot["adj_calls"],
                             prefix, args.rate_in, args.rate_out)
    fullctx = _price_cached(tot["fullctx_in"], tot["adj_out"], tot["adj_calls"],
                            prefix, args.rate_in, args.rate_out)
    ablations = fullctx + noverify + agent

    print(f"\n  {'TARGET':<24} {'calls':>6} {'in tok':>10} {'out tok':>8} {'cost':>9}")
    print(f"  {'baseline-a':<24} {len(rows):>6} {tot['a_in']:>10,} "
          f"{tot['a_out']:>8,} ${base_a:>8.2f}")
    print(f"  {'agent':<24} {tot['adj_calls'] + tot['ver_calls']:>6} "
          f"{tot['adj_in'] + tot['ver_in']:>10,} "
          f"{tot['adj_out'] + tot['ver_out']:>8,} ${agent:>8.2f}")
    print(f"  {'ablations (3 passes)':<24} {'':>6} {'':>10} {'':>8} ${ablations:>8.2f}")
    print(f"    - fullctx (removed exp) {'':>2} {tot['adj_calls']:>6} "
          f"{tot['fullctx_in']:>10,} {tot['adj_out']:>8,} ${fullctx:>8.2f}")
    print(f"    - noverify {'':>13} {tot['adj_calls']:>6} {tot['adj_in']:>10,} "
          f"{tot['adj_out']:>8,} ${noverify:>8.2f}")
    print(f"    - nomem {'':>16} {tot['adj_calls'] + tot['ver_calls']:>6} "
          f"{tot['adj_in'] + tot['ver_in']:>10,} "
          f"{tot['adj_out'] + tot['ver_out']:>8,} ${agent:>8.2f}")
    print(f"\n  {'FULL RUN':<24} {'':>6} {'':>10} {'':>8} "
          f"${base_a + agent + ablations:>8.2f}")
    print(f"  {'MINIMUM VIABLE':<24} {'':>6} {'':>10} {'':>8} "
          f"${base_a + agent:>8.2f}   (baseline-a + agent only)")

    print(f"\n  {tot['auto']} of {sum(r['invoices'] for r in rows)} invoices are "
          f"resolved deterministically and cost nothing.")
    if not os.environ.get("SETTLE_NO_CACHE"):
        print(f"  Caching the {prefix:,}-token system prefix saves "
              f"${agent_raw - agent:.2f} on the agent run "
              f"({(1 - agent / agent_raw) * 100:.0f}%). "
              f"Without it: ${agent_raw:.2f}.")
    print("  Estimates are character-based and approximate. The measured figure "
          "lands in\n  results/RESULTS.md after a real run.")


if __name__ == "__main__":
    main()

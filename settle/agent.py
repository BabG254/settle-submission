"""Settle -- the agent.

Shape of the thing:

    bounded retrieval  ->  subset solver  ->  [adjudicator]  ->  [verifier]
                                                                     |
                                                          ledger gate (hook)
                                                                     |
                                              reconciled.csv + exceptions.csv

The model appears in exactly two places, and in both it is answering the same
question: which human is behind this name. It never sums, never searches, never
decides what "close enough" means. Everything else is a function.

Ablation flags exist for every component so each changelog entry can be
reproduced independently:

    --no-adjudicator   deterministic core only, escalate all ambiguity
    --no-verifier      skip the adversarial second opinion
    --no-memory        run cold, ignore the alias store
    --no-gate          disable the ledger invariant gate (diagnostic only)
    --full-context     removed experiment: give the adjudicator the whole
                       statement instead of the shortlist
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .llm import call_model, parse_json, price, set_trace, trace_event
from .memory import AliasMemory
from .schema import Case, Invoice, Txn, read_case, read_truth
from .tools import (
    Candidate, check_ledger, propose_candidates, subset_coherence, subset_solver,
)

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "mobile-money-forensics" / "SKILL.md"

AUTO_ACCEPT_NAME = 88.0     # above this, with one unique subset, no model needed
MEMORY_WRITE_CONFIDENCE = 0.85


def load_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""


# --------------------------------------------------------------- adjudicator

ADJUDICATOR_SYSTEM = """You adjudicate payment identity for a reconciliation system.

{skill}

You will be given one invoice and a shortlist of candidate transactions, plus
every combination of those transactions that sums EXACTLY to the invoice in
gross terms. The arithmetic is already done and is correct; do not redo it and
do not propose a combination that is not in the list.

Your only judgement is: which of these combinations, if any, was paid by the
customer named on the invoice.

Reply with JSON only, no prose, no fences:
{{"decision": "match" | "escalate",
  "receipts": ["..."],
  "confidence": 0.0-1.0,
  "payer_identity": "the party name you are asserting is this customer, or null",
  "reasoning": "one or two sentences citing the specific evidence you used"}}

Choose "escalate" whenever the evidence separating two combinations is only
timing or amount. Escalation is the correct answer to genuine ambiguity, not a
failure."""

ADJUDICATOR_USER = """INVOICE
  id:       {inv_id}
  customer: {customer} (id {cust_id})
  amount:   KES {amount:,} (gross, inclusive of any transaction fee)
  issued:   {issued}

CANDIDATE TRANSACTIONS
{candidates}

COMBINATIONS THAT SUM EXACTLY TO KES {amount:,}
{subsets}

ALIAS MEMORY
{memory}
"""


def _fmt_candidates(cands: list[Candidate]) -> str:
    if not cands:
        return "  (none)"
    head = ("  receipt      date        party                          "
            "net      fee   gross    name  d+")
    lines = [head]
    for c in cands:
        lines.append(
            f"  {c.receipt:<12} {c.datetime[:10]}  {c.party_name[:28]:<28} "
            f"{c.net:>8,} {c.fee:>5,} {c.gross:>8,}  {c.name_score:>5.0f} "
            f"{c.days_from_issue:>+3d}")
    return "\n".join(lines)


def _fmt_subsets(subsets: list[list[str]], cands: list[Candidate]) -> str:
    if not subsets:
        return "  (no combination sums to the invoice amount)"
    lines = []
    for n, s in enumerate(subsets, 1):
        c = subset_coherence(s, cands)
        lines.append(
            f"  [{n}] {', '.join(s)}\n"
            f"      parts={c['parts']} same_payer_name={c['same_payer_name']} "
            f"same_phone={c['same_payer_phone']} "
            f"name_score={c['min_name_score']}-{c['max_name_score']} "
            f"span={c['span_days']}d")
    return "\n".join(lines)


def _fmt_memory(cands: list[Candidate], memory: AliasMemory | None) -> str:
    if memory is None:
        return "  (memory disabled for this run)"
    rows = []
    for c in cands:
        e = memory.explain(c.party_name)
        if e:
            rows.append(f"  {c.party_name} -> {e['customer_name']} ({e['customer_id']}), "
                        f"approved {e['first_seen'][:10]} via {e['source']}")
    return "\n".join(rows) if rows else "  (no approved alias for any candidate)"


# ------------------------------------------------------------------ verifier

VERIFIER_SYSTEM = """You are a verifier. Your job is to FALSIFY a proposed payment match.

{skill}

You are shown one proposed match and the evidence behind it. Assume it is wrong
and look for the reason. Specifically check:

  - Could the money have come from someone other than the invoiced customer?
  - Is the payer link nothing more than a shared surname or a matching amount?
  - Is there a competing combination that fits the evidence equally well?
  - Does the asserted identity rest on an alias that was never approved?

Do not check arithmetic. It has already been verified by a solver and is correct.

Reply with JSON only:
{{"verdict": "pass" | "reject",
  "objection": "the specific reason this match may be wrong, or null",
  "confidence": 0.0-1.0}}

"pass" means you tried to break it and could not."""

VERIFIER_USER = """PROPOSED MATCH
  invoice:  {inv_id} -- {customer}, KES {amount:,}
  receipts: {receipts}
  asserted payer identity: {identity}
  adjudicator reasoning: {reasoning}
  adjudicator confidence: {confidence}

EVIDENCE FOR THE CHOSEN COMBINATION
{chosen}

COMPETING COMBINATIONS THAT ALSO SUM EXACTLY
{competing}
"""


# ------------------------------------------------------------------ pipeline

class Settle:
    def __init__(self, *, model: str, use_adjudicator: bool = True,
                 use_verifier: bool = True, memory: AliasMemory | None = None,
                 use_gate: bool = True, full_context: bool = False,
                 identity_oracle: dict[str, list[str]] | None = None):
        self.model = model
        self.use_adjudicator = use_adjudicator
        self.use_verifier = use_verifier
        self.memory = memory
        self.use_gate = use_gate
        self.full_context = full_context
        # Ceiling mode. Substitutes a perfect identity judge for the model so
        # the pipeline can be smoke-tested with no API key, and so the report
        # can show how much headroom the adjudicator is actually competing for.
        # It reads truth.json and is therefore NOT a solution -- it is labelled
        # settle_oracle_ceiling everywhere it appears.
        self.identity_oracle = identity_oracle
        self.skill = load_skill()
        self.cost = 0.0
        self.calls = 0

    # -- one invoice ------------------------------------------------------
    def resolve(self, inv: Invoice, txns: list[Txn], used: set[str]) -> dict:
        cands = propose_candidates(inv, txns, memory=self.memory, exclude=used)
        subsets = subset_solver(inv.amount, cands)
        trace_event("retrieval", invoice=inv.invoice_id, statement_rows=len(txns),
                    shortlisted=len(cands), exact_combinations=len(subsets))

        if not subsets:
            return self._escalate(inv, [], cands, subsets,
                                  "no combination of candidate transactions sums "
                                  "to the invoice amount")

        # Deterministic fast path: one combination, one payer, unambiguous name.
        if len(subsets) == 1:
            coh = subset_coherence(subsets[0], cands)
            mem_ok = any(c.memory_hit == inv.customer_id
                         for c in cands if c.receipt in subsets[0])
            if coh["same_payer_name"] and (coh["min_name_score"] >= AUTO_ACCEPT_NAME
                                           or mem_ok):
                trace_event("auto_accept", invoice=inv.invoice_id,
                            receipts=subsets[0],
                            why="unique combination, single coherent payer")
                return {"decision": "match", "receipts": subsets[0],
                        "confidence": 0.97, "route": "deterministic",
                        "reasoning": "Unique exact combination from a single payer "
                                     "with an unambiguous name match.",
                        "payer_identity": next(c.party_name for c in cands
                                               if c.receipt == subsets[0][0])}

        if self.identity_oracle is not None:
            want = set(self.identity_oracle.get(inv.invoice_id, []))
            hit = next((s for s in subsets if set(s) == want), None)
            if hit is None:
                return self._escalate(inv, subsets[0], cands, subsets,
                                      "ceiling: correct combination not reachable "
                                      "from the shortlist")
            return {"decision": "match", "receipts": hit, "confidence": 1.0,
                    "route": "oracle_ceiling",
                    "reasoning": "identity oracle (ceiling run, not a solution)",
                    "payer_identity": next((c.party_name for c in cands
                                            if c.receipt == hit[0]), None)}

        if not self.use_adjudicator:
            return self._escalate(inv, subsets[0] if len(subsets) == 1 else [],
                                  cands, subsets,
                                  "ambiguous payer identity; adjudicator disabled")

        decision = self._adjudicate(inv, cands, subsets, txns)
        if decision.get("decision") != "match" or not decision.get("receipts"):
            return self._escalate(inv, decision.get("receipts") or [], cands, subsets,
                                  decision.get("reasoning", "adjudicator escalated"))

        if decision["receipts"] not in subsets:
            trace_event("gate_reject", invoice=inv.invoice_id,
                        why="adjudicator returned a combination not in the solved set")
            return self._escalate(inv, decision["receipts"], cands, subsets,
                                  "adjudicator proposed an unsolved combination")

        if self.use_verifier:
            verdict = self._verify(inv, decision, cands, subsets)
            if verdict.get("verdict") == "reject":
                trace_event("verifier_reject", invoice=inv.invoice_id,
                            objection=verdict.get("objection"))
                return self._escalate(inv, decision["receipts"], cands, subsets,
                                      f"verifier objection: {verdict.get('objection')}")
            decision["verifier"] = verdict

        decision["route"] = "adjudicated"
        return decision

    def _escalate(self, inv: Invoice, auto_guess: list[str],
                  cands: list[Candidate], subsets: list[list[str]],
                  reason: str) -> dict:
        # An escalation still carries the system's best guess, so a human has
        # something to accept or reject rather than a blank form.
        if not auto_guess and subsets:
            auto_guess = subsets[0]
        return {"decision": "escalate", "receipts": [], "auto_guess": auto_guess,
                "reason": reason, "route": "escalated",
                "candidates": [c.to_dict() for c in cands[:6]],
                "options": subsets[:4]}

    # -- model steps ------------------------------------------------------
    def _adjudicate(self, inv: Invoice, cands: list[Candidate],
                    subsets: list[list[str]], txns: list[Txn]) -> dict:
        if self.full_context:
            # Removed experiment, kept for reproducibility: dump the whole
            # statement instead of the shortlist.
            shown = "\n".join(
                f"  {t.receipt} {t.datetime[:16]} {t.party_name[:28]:<28} "
                f"{t.paid_in:>8,} {t.fee:>5,} {t.kind}"
                for t in txns)
        else:
            shown = _fmt_candidates(cands)

        user = ADJUDICATOR_USER.format(
            inv_id=inv.invoice_id, customer=inv.customer_name,
            cust_id=inv.customer_id, amount=inv.amount, issued=inv.issue_date,
            candidates=shown,
            subsets=_fmt_subsets(subsets, cands),
            memory=_fmt_memory(cands, self.memory))
        text, usage = call_model(
            self.model, ADJUDICATOR_SYSTEM.format(skill=self.skill), user,
            max_tokens=1200, role="adjudicator")
        self.cost += price(self.model, usage)
        self.calls += 1
        try:
            return parse_json(text)
        except Exception as exc:                                # noqa: BLE001
            return {"decision": "escalate",
                    "reasoning": f"adjudicator output unparseable: {exc}"}

    def _verify(self, inv: Invoice, decision: dict, cands: list[Candidate],
                subsets: list[list[str]]) -> dict:
        chosen = subset_coherence(decision["receipts"], cands)
        by_r = {c.receipt: c for c in cands}
        chosen_rows = "\n".join(
            f"  {r}  {by_r[r].party_name}  {by_r[r].party_phone}  "
            f"gross {by_r[r].gross:,}  name_score {by_r[r].name_score:.0f}"
            for r in decision["receipts"] if r in by_r)
        competing = [s for s in subsets if s != decision["receipts"]]
        competing_rows = "\n".join(
            f"  [{i}] {', '.join(s)} -- payers: "
            f"{', '.join(sorted({by_r[r].party_name for r in s if r in by_r}))}"
            for i, s in enumerate(competing[:4], 1)) or "  (none)"

        user = VERIFIER_USER.format(
            inv_id=inv.invoice_id, customer=inv.customer_name, amount=inv.amount,
            receipts=", ".join(decision["receipts"]),
            identity=decision.get("payer_identity"),
            reasoning=decision.get("reasoning"),
            confidence=decision.get("confidence"),
            chosen=chosen_rows + f"\n  structure: {chosen}",
            competing=competing_rows)
        text, usage = call_model(
            self.model, VERIFIER_SYSTEM.format(skill=self.skill), user,
            max_tokens=600, role="verifier")
        self.cost += price(self.model, usage)
        self.calls += 1
        try:
            return parse_json(text)
        except Exception:                                       # noqa: BLE001
            return {"verdict": "reject", "objection": "verifier output unparseable"}

    # -- whole case -------------------------------------------------------
    def run(self, case: Case) -> dict:
        t0 = time.time()
        used: set[str] = set()
        matching: dict[str, list[str]] = {}
        exceptions: list[dict] = []
        routes: dict[str, int] = {}

        # Process least-ambiguous invoices first so confident matches claim
        # their transactions before contested ones do.
        order = sorted(
            case.invoices,
            key=lambda i: len(subset_solver(
                i.amount, propose_candidates(i, case.txns, memory=self.memory))) or 99)

        for inv in order:
            res = self.resolve(inv, case.txns, used)
            routes[res.get("route", "?")] = routes.get(res.get("route", "?"), 0) + 1
            if res["decision"] == "match":
                matching[inv.invoice_id] = res["receipts"]
                used.update(res["receipts"])
                if (self.memory is not None
                        and res.get("payer_identity")
                        and float(res.get("confidence", 0)) >= MEMORY_WRITE_CONFIDENCE):
                    is_new = self.memory.remember(
                        res["payer_identity"], inv.customer_id, inv.customer_name,
                        source="verifier_pass",
                        evidence=f"{inv.invoice_id}: {res.get('reasoning', '')[:200]}")
                    if is_new:
                        trace_event("memory_write", invoice=inv.invoice_id,
                                    alias=res["payer_identity"],
                                    customer=inv.customer_id)
            else:
                exceptions.append({
                    "invoice_id": inv.invoice_id,
                    "customer": inv.customer_name,
                    "amount": inv.amount,
                    "reason": res.get("reason", ""),
                    "auto_guess": res.get("auto_guess", []),
                    "options": res.get("options", []),
                    "candidates": res.get("candidates", []),
                })

        # ---- the gate. Not advice: a run that fails it does not ship.
        ledger_ok = None
        gate_repairs = []
        if self.use_gate:
            report = check_ledger(matching, case.invoices, case.txns)
            if not report.ok:
                # Deterministic repair: withdraw every offending match to the
                # exceptions queue, then re-verify. If it still fails, abort.
                bad = {e.split(":")[0] for e in report.errors}
                for inv_id in bad:
                    if inv_id in matching:
                        exceptions.append({
                            "invoice_id": inv_id,
                            "reason": "withdrawn by ledger gate",
                            "auto_guess": matching.pop(inv_id),
                            "options": [], "candidates": [],
                        })
                        gate_repairs.append(inv_id)
                report = check_ledger(matching, case.invoices, case.txns)
                if not report.ok:
                    raise RuntimeError("ledger gate could not be satisfied:\n"
                                       + report.summary())
            ledger_ok = report.ok
            trace_event("ledger_gate", case=case.case_id, ok=report.ok,
                        withdrawn=gate_repairs, summary=report.summary()[:400])

        return {
            "case_id": case.case_id,
            "system": self._label(),
            "matching": matching,
            "exceptions": exceptions,
            "ledger_ok": ledger_ok,
            "gate_withdrawals": gate_repairs,
            "routes": routes,
            "meta": {"cost_usd": round(self.cost, 4),
                     "wall_s": round(time.time() - t0, 1),
                     "model_calls": self.calls,
                     "model": self.model,
                     "memory_size": self.memory.size() if self.memory else 0},
        }

    def _label(self) -> str:
        if self.identity_oracle is not None:
            return "settle_oracle_ceiling"
        bits = ["settle"]
        if not self.use_adjudicator:
            bits.append("core")
        if not self.use_verifier:
            bits.append("noverify")
        if self.memory is None:
            bits.append("nomem")
        if not self.use_gate:
            bits.append("nogate")
        if self.full_context:
            bits.append("fullctx")
        return "_".join(bits)


# -------------------------------------------------------------------- runner

def write_outputs(pred: dict, case: Case, out_dir: Path) -> None:
    """The artefacts a bookkeeper actually opens."""
    import csv
    by_r = {t.receipt: t for t in case.txns}
    by_i = {i.invoice_id: i for i in case.invoices}
    d = out_dir / case.case_id
    d.mkdir(parents=True, exist_ok=True)

    with (d / "reconciled.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["invoice_id", "customer", "invoice_amount", "receipt",
                    "paid_on", "payer_on_statement", "net_credited", "fee", "gross"])
        for inv_id, receipts in sorted(pred["matching"].items()):
            inv = by_i[inv_id]
            for r in receipts:
                t = by_r[r]
                w.writerow([inv_id, inv.customer_name, inv.amount, r,
                            t.datetime[:10], t.party_name, t.paid_in, t.fee, t.gross])

    with (d / "exceptions.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["invoice_id", "customer", "amount", "reason",
                    "best_guess", "n_options"])
        for e in pred["exceptions"]:
            inv = by_i.get(e["invoice_id"])
            w.writerow([e["invoice_id"], e.get("customer", inv.customer_name if inv else ""),
                        e.get("amount", inv.amount if inv else ""), e["reason"],
                        " + ".join(e.get("auto_guess", [])), len(e.get("options", []))])


def main() -> None:
    from .llm import _load_dotenv
    _load_dotenv()
    ap = argparse.ArgumentParser(description="Run Settle over the corpus.")
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--outputs", type=Path, default=Path("outputs"))
    ap.add_argument("--model", default=os.environ.get("SETTLE_MODEL", "claude-sonnet-4-6"))
    ap.add_argument("--memory-db", type=Path, default=Path("state/aliases.db"))
    ap.add_argument("--cases", nargs="*", default=None)
    ap.add_argument("--no-adjudicator", action="store_true")
    ap.add_argument("--no-verifier", action="store_true")
    ap.add_argument("--no-memory", action="store_true")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--full-context", action="store_true")
    ap.add_argument("--reset-memory", action="store_true")
    ap.add_argument("--identity-oracle", action="store_true",
                    help="ceiling run: substitute a perfect identity judge for the "
                         "model. Reads truth.json. Not a solution -- reported as "
                         "settle_oracle_ceiling.")
    ap.add_argument("--trace", type=Path, default=None)
    ap.add_argument("--resume", action="store_true",
                    help="skip cases whose prediction file already exists, so an "
                         "interrupted run does not pay for completed work twice")
    args = ap.parse_args()

    memory = None if args.no_memory else AliasMemory(args.memory_db)
    if memory and args.reset_memory:
        memory.reset()

    args.out.mkdir(parents=True, exist_ok=True)
    dirs = sorted(d for d in args.data.iterdir()
                  if d.is_dir() and (d / "truth.json").exists())
    if args.cases:
        dirs = [d for d in dirs if d.name in args.cases]

    failures = []
    for d in dirs:
        out_file = args.out / f"{d.name}.json"
        if args.resume and out_file.exists():
            print(f"  {d.name}: already done, skipping (--resume)")
            continue
        case = read_case(d)
        set_trace(args.trace / f"{case.case_id}.jsonl" if args.trace else None)
        oracle = read_truth(d) if args.identity_oracle else None
        engine = Settle(model=args.model,
                        identity_oracle=oracle,
                        use_adjudicator=not args.no_adjudicator,
                        use_verifier=not args.no_verifier,
                        memory=memory,
                        use_gate=not args.no_gate,
                        full_context=args.full_context)
        try:
            pred = engine.run(case)
        except Exception as exc:                                # noqa: BLE001
            # One bad case must not discard the cases already paid for.
            failures.append((case.case_id, f"{type(exc).__name__}: {exc}"))
            print(f"  {case.case_id}: FAILED -- {type(exc).__name__}: {exc}")
            continue
        out_file.write_text(json.dumps(pred, indent=2), encoding="utf-8")
        write_outputs(pred, case, args.outputs)
        print(f"  {case.case_id}: matched {len(pred['matching'])}/{len(case.invoices)}, "
              f"escalated {len(pred['exceptions'])}, "
              f"gate {'OK' if pred['ledger_ok'] else pred['ledger_ok']}, "
              f"calls {pred['meta']['model_calls']}, "
              f"${pred['meta']['cost_usd']}")

    if failures:
        print(f"\n  {len(failures)} case(s) failed; the rest were written. "
              f"Re-run with --resume to retry only these:")
        for cid, err in failures:
            print(f"    {cid}: {err}")


if __name__ == "__main__":
    main()

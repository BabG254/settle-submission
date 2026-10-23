"""The deterministic tool layer.

Design rule for this file: nothing in here may guess. Every function is either
exact (arithmetic, set logic, subset search) or an explicitly-scored heuristic
whose output is a *ranked shortlist*, never a decision. Decisions about
identity are the agent's job; everything else is code's job.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from rapidfuzz import fuzz

from .schema import Invoice, Txn

# Words that carry no identifying signal for a Kenyan SME customer base.
STOPWORDS = {
    "LTD", "LIMITED", "ENTERPRISES", "ENTERPRISE", "SUPPLIES", "SUPPLY",
    "TRADERS", "STORES", "STORE", "GENERAL", "COMPANY", "CO", "AND", "THE",
    "SERVICES", "HOLDINGS", "GROUP", "AGENCIES", "CENTRE", "CENTER",
}

CANDIDATE_K = 14          # hard ceiling on shortlist size sent to the model
DATE_BEFORE_DAYS = 3      # customers occasionally pay before the invoice lands
DATE_AFTER_DAYS = 28
MAX_SUBSETS = 8           # ambiguity above this is escalated, not resolved
MAX_SUBSET_PARTS = 5


# ------------------------------------------------------------ name handling

def normalise(name: str) -> str:
    s = re.sub(r"[^A-Za-z ]", " ", (name or "").upper())
    toks = [t for t in s.split() if t and t not in STOPWORDS]
    return " ".join(toks)


def name_score(invoice_name: str, party_name: str) -> float:
    """0-100. Deliberately a *shortlist* score, not a decision threshold.

    token_set_ratio handles reordering and extra middle names. It does not
    handle initialised surnames, trading names, or a relative paying on the
    customer's behalf -- those are the cases that need judgment.
    """
    a, b = normalise(invoice_name), normalise(party_name)
    if not a or not b:
        return 0.0
    return max(fuzz.token_set_ratio(a, b), fuzz.partial_ratio(a, b) * 0.85)


def phone_tail(masked: str) -> str:
    return (masked or "")[-3:]


# ------------------------------------------------------------------ reversals

def reversal_pairs(txns: list[Txn]) -> set[str]:
    """Receipts that must never be matched: the reversed credit and its reversal.

    A reversed payment nets to zero. Matching it to an invoice reports revenue
    that was never received -- the single most expensive error in this domain.
    """
    dead: set[str] = set()
    for t in txns:
        if t.kind == "reversal" and t.reverses:
            dead.add(t.receipt)
            dead.add(t.reverses)
    return dead


# ---------------------------------------------------------------- candidates

@dataclass
class Candidate:
    receipt: str
    datetime: str
    party_name: str
    party_phone: str
    net: int
    fee: int
    gross: int
    name_score: float
    memory_hit: str | None
    days_from_issue: int

    def to_dict(self) -> dict:
        return {
            "receipt": self.receipt, "datetime": self.datetime,
            "party_name": self.party_name, "party_phone": self.party_phone,
            "net_credited": self.net, "fee": self.fee, "gross": self.gross,
            "name_score": round(self.name_score, 1),
            "memory_hit": self.memory_hit,
            "days_after_invoice": self.days_from_issue,
        }


def propose_candidates(invoice: Invoice, txns: list[Txn], *,
                       memory=None, k: int = CANDIDATE_K,
                       exclude: set[str] | None = None) -> list[Candidate]:
    """Bounded retrieval. Returns at most `k` transactions worth considering.

    This is the tool that keeps the statement out of the context window. On the
    largest case it reduces a 220-row statement to 14 rows per invoice.
    """
    exclude = (exclude or set()) | reversal_pairs(txns)
    issue = date.fromisoformat(invoice.issue_date)
    lo = issue - timedelta(days=DATE_BEFORE_DAYS)
    hi = issue + timedelta(days=DATE_AFTER_DAYS)

    out: list[Candidate] = []
    for t in txns:
        if t.kind != "pay_bill" or t.receipt in exclude:
            continue
        when = datetime.fromisoformat(t.datetime).date()
        if not (lo <= when <= hi):
            continue
        if t.gross > invoice.amount:          # a single part never exceeds the whole
            continue
        ns = name_score(invoice.customer_name, t.party_name)
        hit = memory.lookup(t.party_name) if memory else None
        out.append(Candidate(
            receipt=t.receipt, datetime=t.datetime, party_name=t.party_name,
            party_phone=t.party_phone, net=t.paid_in, fee=t.fee, gross=t.gross,
            name_score=ns,
            memory_hit=hit if hit else None,
            days_from_issue=(when - issue).days,
        ))

    def rank(c: Candidate) -> tuple:
        mem_bonus = 40.0 if c.memory_hit == invoice.customer_id else 0.0
        exact = 25.0 if c.gross == invoice.amount else 0.0
        return -(c.name_score + mem_bonus + exact), abs(c.days_from_issue)

    out.sort(key=rank)
    return out[:k]


# -------------------------------------------------------------- subset solver

def subset_solver(target: int, candidates: list[Candidate], *,
                  max_parts: int = MAX_SUBSET_PARTS,
                  max_results: int = MAX_SUBSETS) -> list[list[str]]:
    """All subsets of `candidates` whose gross sums exactly to `target`.

    Meet-in-the-middle. This is the half of the problem a language model cannot
    do: with 14 candidates there are 16,383 non-empty subsets, and a model asked
    to "find the ones that add up" will assert an answer without summing it.

    Returns receipt lists, shortest first. More than one result means the data
    is genuinely ambiguous on amount alone -- that is what the agent is for.
    """
    n = len(candidates)
    if n == 0:
        return []
    half = n // 2
    left, right = candidates[:half], candidates[half:]

    def enumerate_half(items: list[Candidate]) -> dict[int, list[tuple[int, ...]]]:
        table: dict[int, list[tuple[int, ...]]] = {}
        for r in range(0, min(len(items), max_parts) + 1):
            for combo in itertools.combinations(range(len(items)), r):
                s = sum(items[i].gross for i in combo)
                if s <= target:
                    table.setdefault(s, []).append(combo)
        return table

    lt = enumerate_half(left)
    rt = enumerate_half(right)

    results: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for s, lcombos in lt.items():
        rem = target - s
        if rem not in rt:
            continue
        for lc in lcombos:
            for rc in rt[rem]:
                if not lc and not rc:
                    continue
                if len(lc) + len(rc) > max_parts:
                    continue
                receipts = tuple(sorted(
                    [left[i].receipt for i in lc] + [right[j].receipt for j in rc]))
                if receipts in seen:
                    continue
                seen.add(receipts)
                results.append(list(receipts))

    results.sort(key=lambda r: (len(r), r))
    return results[:max_results]


def subset_coherence(receipts: list[str], candidates: list[Candidate]) -> dict:
    """Cheap structural summary of a candidate subset, for the model to weigh."""
    by_r = {c.receipt: c for c in candidates}
    picked = [by_r[r] for r in receipts if r in by_r]
    if not picked:
        return {"parts": 0}
    names = {normalise(c.party_name) for c in picked}
    phones = {c.party_phone for c in picked}
    return {
        "parts": len(picked),
        "same_payer_name": len(names) == 1,
        "same_payer_phone": len(phones) == 1,
        "min_name_score": round(min(c.name_score for c in picked), 1),
        "max_name_score": round(max(c.name_score for c in picked), 1),
        "span_days": max(c.days_from_issue for c in picked)
                     - min(c.days_from_issue for c in picked),
        "gross_total": sum(c.gross for c in picked),
    }


# ------------------------------------------------------------- ledger checker

@dataclass
class LedgerReport:
    ok: bool
    errors: list[str]
    checked: int

    def summary(self) -> str:
        if self.ok:
            return f"LEDGER OK - {self.checked} matched invoices, all invariants hold"
        return (f"LEDGER FAILED - {len(self.errors)} violation(s):\n  "
                + "\n  ".join(self.errors[:20]))


def check_ledger(matching: dict[str, list[str]], invoices: list[Invoice],
                 txns: list[Txn]) -> LedgerReport:
    """Hard invariants. This runs as a gate, not as advice.

    A run that fails this cannot be marked complete, regardless of how confident
    the model is. It is the reason the system cannot emit an unbalanced ledger.
    """
    errors: list[str] = []
    by_receipt = {t.receipt: t for t in txns}
    by_invoice = {i.invoice_id: i for i in invoices}
    dead = reversal_pairs(txns)

    seen: dict[str, str] = {}
    for inv_id, receipts in matching.items():
        if inv_id not in by_invoice:
            errors.append(f"{inv_id}: unknown invoice id")
            continue
        inv = by_invoice[inv_id]
        if not receipts:
            errors.append(f"{inv_id}: matched to zero transactions")
            continue
        total = 0
        for r in receipts:
            if r not in by_receipt:
                errors.append(f"{inv_id}: receipt {r} is not in the statement")
                continue
            if r in dead:
                errors.append(f"{inv_id}: receipt {r} was reversed - never received")
                continue
            if by_receipt[r].kind != "pay_bill":
                errors.append(f"{inv_id}: receipt {r} is not a pay_bill transaction")
                continue
            if r in seen:
                errors.append(f"{inv_id}: receipt {r} already used by {seen[r]}")
                continue
            seen[r] = inv_id
            total += by_receipt[r].gross
        if total != inv.amount:
            errors.append(
                f"{inv_id}: parts sum to {total:,} but invoice is {inv.amount:,} "
                f"(difference {total - inv.amount:+,})")

    return LedgerReport(ok=not errors, errors=errors, checked=len(matching))

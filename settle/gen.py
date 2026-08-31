"""Seeded synthetic case generator.

Every case ships with its own exact ground-truth matching, which is what makes
the evaluation free, deterministic and free of personal data. Nothing here is
sampled from a real statement; the customer roster is invented.

    python -m settle.gen --seed 42 --out data/

Re-running with the same seed reproduces the corpus byte for byte.
"""
from __future__ import annotations

import argparse
import random
import string
from datetime import date, datetime, timedelta
from pathlib import Path

from .fees import TXN_CAP, fee_for
from .schema import BankLine, Case, Invoice, Txn, write_case

# --------------------------------------------------------------------- roster

# Each entry declares how this customer's name shows up on a statement.
#   plain     -> uppercased full name; fuzzy matching handles it
#   initials  -> middle name spelled out, surname reduced to an initial
#   trade     -> business trading name, no overlap with the registered name
#   proxy     -> a different human pays on their behalf
ROSTER = [
    dict(id="C101", name="Grace Njeri Mwangi", phone="254722104881",
         plain="GRACE NJERI MWANGI", initials="G N MWANGI", trade=None, proxy=None),
    dict(id="C102", name="Peter Otieno Ochieng", phone="254733205119",
         plain="PETER OTIENO OCHIENG", initials="P O OCHIENG", trade=None,
         proxy=("BEATRICE ADHIAMBO", "254722889014")),
    dict(id="C103", name="Mary W. Kariuki", phone="254720114553",
         plain="MARY WANJIKU KARIUKI", initials="MARY WANJIKU K", trade=None,
         proxy=("JOSEPH KARIUKI", "254733991204")),
    dict(id="C104", name="Njeri Wambui Enterprises", phone="254711330462",
         plain="NJERI WAMBUI ENTERPRISES", initials="N W ENTERPRISES",
         trade="MAMA NJERI GROCERS", proxy=None),
    dict(id="C105", name="Samuel Kiprotich Rono", phone="254701447720",
         plain="SAMUEL KIPROTICH RONO", initials="S K RONO", trade=None, proxy=None),
    dict(id="C106", name="Fatuma Abdi Hassan", phone="254729118305",
         plain="FATUMA ABDI HASSAN", initials="F A HASSAN", trade=None, proxy=None),
    dict(id="C107", name="Kilimo Fresh Produce Ltd", phone="254705662218",
         plain="KILIMO FRESH PRODUCE LTD", initials="KILIMO FRESH P LTD",
         trade="KILIMO DEPOT", proxy=None),
    dict(id="C108", name="Anne Chepkoech Bett", phone="254715880347",
         plain="ANNE CHEPKOECH BETT", initials="A C BETT", trade=None,
         proxy=("DANIEL BETT", "254738220991")),
    dict(id="C109", name="Ibrahim Mohamed Noor", phone="254726443015",
         plain="IBRAHIM MOHAMED NOOR", initials="I M NOOR", trade=None, proxy=None),
    dict(id="C110", name="Wanjiku Hardware Supplies", phone="254712007739",
         plain="WANJIKU HARDWARE SUPPLIES", initials="W HARDWARE S",
         trade="JUJA BUILDERS CENTRE", proxy=None),
    dict(id="C111", name="David Mutiso Kilonzo", phone="254707551208",
         plain="DAVID MUTISO KILONZO", initials="D M KILONZO", trade=None, proxy=None),
    dict(id="C112", name="Esther Akinyi Owuor", phone="254736119842",
         plain="ESTHER AKINYI OWUOR", initials="E A OWUOR", trade=None,
         proxy=("MILLICENT OWUOR", "254721664330")),
]

# People who appear in the statement but never owe an invoice -- background
# traffic, and the source of decoy amounts.
STRANGERS = [
    ("JOHN MAINA GITHINJI", "254722551100"), ("ROSE NASIMIYU WAFULA", "254733664112"),
    ("HASSAN OMAR JUMA", "254711220453"), ("LUCY MUTHONI NDUNG'U", "254705887321"),
    ("KEVIN ODHIAMBO ONYANGO", "254729004417"), ("SARAH JEPKOSGEI KOECH", "254715339028"),
    ("MOSES WEKESA BARASA", "254701772634"), ("ZAINAB ALI SALIM", "254726118990"),
]

# ------------------------------------------------------------------ case plan

# p_* are probabilities applied per invoice. Cases escalate in difficulty.
CASE_PLAN = [
    dict(id="case01", n=8,  p_fee=0.0, p_split=0.0, p_alias=0.0, p_proxy=0.0,
         p_trade=0.0, n_reversals=0, n_decoys=0, noise=6,   bank=False,
         features=["clean 1:1"]),
    dict(id="case02", n=10, p_fee=0.0, p_split=0.0, p_alias=0.0, p_proxy=0.0,
         p_trade=0.0, n_reversals=0, n_decoys=0, noise=20,  bank=False,
         features=["clean 1:1", "background traffic"]),
    dict(id="case03", n=10, p_fee=1.0, p_split=0.0, p_alias=0.0, p_proxy=0.0,
         p_trade=0.0, n_reversals=0, n_decoys=0, noise=20,  bank=False,
         features=["fees: net != invoiced"]),
    dict(id="case04", n=10, p_fee=1.0, p_split=0.0, p_alias=0.35, p_proxy=0.0,
         p_trade=0.0, n_reversals=0, n_decoys=0, noise=20,  bank=False,
         features=["fees", "initialised surnames"]),
    dict(id="case05", n=12, p_fee=0.0, p_split=0.5, p_alias=0.0, p_proxy=0.0,
         p_trade=0.0, n_reversals=0, n_decoys=0, noise=24,  bank=False,
         features=["split payments"]),
    dict(id="case06", n=12, p_fee=1.0, p_split=0.5, p_alias=0.0, p_proxy=0.0,
         p_trade=0.0, n_reversals=0, n_decoys=0, noise=24,  bank=False,
         features=["split payments", "fees"]),
    dict(id="case07", n=12, p_fee=1.0, p_split=0.3, p_alias=0.6, p_proxy=0.0,
         p_trade=0.4, n_reversals=0, n_decoys=0, noise=24,  bank=False,
         features=["hard aliases", "trade names"]),
    dict(id="case08", n=12, p_fee=1.0, p_split=0.3, p_alias=0.3, p_proxy=0.5,
         p_trade=0.0, n_reversals=0, n_decoys=0, noise=24,  bank=False,
         features=["proxy payers"]),
    dict(id="case09", n=14, p_fee=1.0, p_split=0.3, p_alias=0.3, p_proxy=0.2,
         p_trade=0.2, n_reversals=4, n_decoys=0, noise=28,  bank=False,
         features=["reversals"]),
    dict(id="case10", n=14, p_fee=1.0, p_split=0.3, p_alias=0.3, p_proxy=0.2,
         p_trade=0.2, n_reversals=2, n_decoys=5, noise=28,  bank=False,
         features=["identical-amount decoys"]),
    dict(id="case11", n=40, p_fee=1.0, p_split=0.35, p_alias=0.3, p_proxy=0.2,
         p_trade=0.2, n_reversals=4, n_decoys=6, noise=140, bank=True,
         features=["volume", "bank aggregation at T+1"]),
    dict(id="case12", n=16, p_fee=1.0, p_split=0.6, p_alias=0.7, p_proxy=0.4,
         p_trade=0.4, n_reversals=4, n_decoys=6, noise=40,  bank=True,
         features=["adversarial: split + reversal + decoy + alias-only + proxy"]),
]

MONTH_START = date(2026, 5, 1)


# ---------------------------------------------------------------- generation

def _receipt(rng: random.Random) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "T" + "".join(rng.choice(alphabet) for _ in range(9))


def _mask(phone: str) -> str:
    return phone[:4] + "*" * 5 + phone[-3:]


def _statement_name(cust: dict, rng: random.Random, p_alias: float,
                    p_trade: float, p_proxy: float) -> tuple[str, str, str]:
    """Return (printed_name, printed_phone, alias_kind)."""
    if cust["proxy"] and rng.random() < p_proxy:
        name, phone = cust["proxy"]
        return name, phone, "proxy"
    if cust["trade"] and rng.random() < p_trade:
        return cust["trade"], cust["phone"], "trade"
    if rng.random() < p_alias:
        return cust["initials"], cust["phone"], "initials"
    return cust["plain"], cust["phone"], "plain"


def _split_amounts(total: int, parts: int, rng: random.Random) -> list[int]:
    """Split `total` into `parts` positive, non-round chunks."""
    if parts == 1:
        return [total]
    cuts = sorted(rng.sample(range(1, total), parts - 1)) if total > parts else []
    if not cuts:
        return [total]
    out, prev = [], 0
    for c in cuts:
        out.append(c - prev)
        prev = c
    out.append(total - prev)
    # nudge away from degenerate tiny parts
    if min(out) < 500:
        base = total // parts
        out = [base] * (parts - 1) + [total - base * (parts - 1)]
    return out


def build_case(plan: dict, seed: int, start: date = MONTH_START,
               month_tag: str = "") -> tuple[Case, dict[str, list[str]]]:
    rng = random.Random(seed)
    invoices: list[Invoice] = []
    txns: list[Txn] = []
    truth: dict[str, list[str]] = {}
    used_receipts: set[str] = set()

    def new_receipt() -> str:
        while True:
            r = _receipt(rng)
            if r not in used_receipts:
                used_receipts.add(r)
                return r

    def add_payment(name: str, phone: str, gross: int, when: datetime,
                    charge_fee: bool) -> Txn:
        fee = fee_for(gross) if charge_fee else 0
        t = Txn(
            receipt=new_receipt(),
            datetime=when.isoformat(timespec="seconds"),
            kind="pay_bill",
            party_name=name,
            party_phone=_mask(phone),
            paid_in=gross - fee,
            fee=fee,
            withdrawn=0,
            narration=f"Pay Bill from {name} {_mask(phone)}",
        )
        txns.append(t)
        return t

    roster = ROSTER[:]
    rng.shuffle(roster)

    # ---- invoices and their payments
    for i in range(plan["n"]):
        cust = roster[i % len(roster)]
        amount = rng.choice([1_200, 3_400, 4_750, 8_900, 12_500, 18_400,
                             24_000, 31_250, 48_000, 63_500, 92_000, 175_000])
        inv_id = f"{plan['id']}{month_tag}-INV{i + 1:03d}"
        issue = start + timedelta(days=rng.randint(0, 6))
        invoices.append(Invoice(
            invoice_id=inv_id, customer_id=cust["id"], customer_name=cust["name"],
            amount=amount, issue_date=issue.isoformat(),
            due_date=(issue + timedelta(days=14)).isoformat(),
        ))

        parts = 1
        if amount > TXN_CAP:                       # mandatory: above the cap
            parts = amount // TXN_CAP + 1
        elif rng.random() < plan["p_split"]:       # voluntary: customer cashflow
            parts = rng.choice([2, 2, 3, 4])
        chunks = _split_amounts(amount, parts, rng)

        name, phone, _kind = _statement_name(
            cust, rng, plan["p_alias"], plan["p_trade"], plan["p_proxy"])
        charge_fee = rng.random() < plan["p_fee"]

        receipts = []
        for c in chunks:
            when = datetime.combine(
                issue + timedelta(days=rng.randint(1, 12)),
                datetime.min.time()) + timedelta(
                hours=rng.randint(7, 20), minutes=rng.randint(0, 59))
            receipts.append(add_payment(name, phone, c, when, charge_fee).receipt)
        truth[inv_id] = receipts

    # ---- reversals: a payment that failed, then the real one (already above)
    reversible = [t for t in txns if t.kind == "pay_bill"]
    rng.shuffle(reversible)
    for t in reversible[: plan["n_reversals"]]:
        when = datetime.fromisoformat(t.datetime) + timedelta(hours=rng.randint(2, 30))
        ghost = Txn(
            receipt=new_receipt(),
            datetime=(datetime.fromisoformat(t.datetime)
                      - timedelta(hours=rng.randint(1, 20))).isoformat(timespec="seconds"),
            kind="pay_bill",
            party_name=t.party_name, party_phone=t.party_phone,
            paid_in=t.paid_in, fee=t.fee, withdrawn=0,
            narration=f"Pay Bill from {t.party_name} {t.party_phone}",
        )
        txns.append(ghost)
        txns.append(Txn(
            receipt=new_receipt(),
            datetime=when.isoformat(timespec="seconds"),
            kind="reversal",
            party_name=t.party_name, party_phone=t.party_phone,
            paid_in=0, fee=0, withdrawn=ghost.paid_in,
            narration=f"Reversal of {ghost.receipt}",
            reverses=ghost.receipt,
        ))
        # ghost + its reversal belong to no invoice: net zero, must be excluded

    # ---- decoys: a stranger pays exactly what some invoice is worth
    for k in range(plan["n_decoys"]):
        inv = invoices[rng.randrange(len(invoices))]
        name, phone = STRANGERS[rng.randrange(len(STRANGERS))]
        when = datetime.combine(date.fromisoformat(inv.issue_date)
                                + timedelta(days=rng.randint(1, 12)),
                                datetime.min.time()) + timedelta(hours=rng.randint(7, 20))
        add_payment(name, phone, inv.amount, when, charge_fee=plan["p_fee"] > 0)

    # ---- background traffic
    for _ in range(plan["noise"]):
        name, phone = STRANGERS[rng.randrange(len(STRANGERS))]
        amount = rng.randrange(200, 40_000, 50)
        when = datetime.combine(start + timedelta(days=rng.randint(0, 27)),
                                datetime.min.time()) + timedelta(
            hours=rng.randint(6, 21), minutes=rng.randint(0, 59))
        add_payment(name, phone, amount, when, charge_fee=plan["p_fee"] > 0)

    txns.sort(key=lambda t: t.datetime)

    # ---- bank: daily net settlement at T+1
    bank: list[BankLine] = []
    if plan["bank"]:
        by_day: dict[date, list[Txn]] = {}
        for t in txns:
            by_day.setdefault(datetime.fromisoformat(t.datetime).date(), []).append(t)
        for n, (day, group) in enumerate(sorted(by_day.items()), start=1):
            net = sum(t.paid_in for t in group) - sum(t.withdrawn for t in group)
            if net == 0:
                continue
            bank.append(BankLine(
                ref=f"STL{n:04d}", date=(day + timedelta(days=1)).isoformat(),
                description=f"MOBILE MONEY SETTLEMENT {day.isoformat()}",
                amount=net, settles=[t.receipt for t in group],
            ))

    case = Case(case_id=plan["id"] + month_tag, invoices=invoices, txns=txns,
                bank=bank, features=plan["features"])
    return case, truth


def build_memory_months(seed: int, months: int = 3) -> list[tuple[Case, dict]]:
    """Three consecutive months over the SAME customers, alias-heavy.

    Used for the memory demonstration: names that must be escalated in month 1
    are resolvable from the alias store by month 3.
    """
    plan = dict(id="month", n=10, p_fee=1.0, p_split=0.3, p_alias=0.8,
                p_proxy=0.5, p_trade=0.6, n_reversals=1, n_decoys=2, noise=20,
                bank=False, features=["alias-heavy", "repeat customers"])
    out = []
    for m in range(months):
        start = date(2026, 5 + m, 1)
        case, truth = build_case(plan, seed=seed * 100 + m, start=start,
                                 month_tag=f"{m + 1:02d}")
        out.append((case, truth))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the Settle evaluation corpus.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--cases", type=int, default=len(CASE_PLAN))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for idx, plan in enumerate(CASE_PLAN[: args.cases]):
        case, truth = build_case(plan, seed=args.seed * 1000 + idx)
        write_case(case, args.out, truth)
        print(f"{case.case_id:10s} invoices={len(case.invoices):3d} "
              f"txns={len(case.txns):4d} bank={len(case.bank):3d}  "
              f"{', '.join(case.features)}")

    demo_dir = args.out / "memory_demo"
    for case, truth in build_memory_months(args.seed):
        write_case(case, demo_dir, truth)
        print(f"{case.case_id:10s} invoices={len(case.invoices):3d} "
              f"txns={len(case.txns):4d}  (memory demo)")


if __name__ == "__main__":
    main()

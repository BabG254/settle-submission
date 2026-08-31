"""Canonical schema for Settle.

Everything downstream (tools, baselines, agent, scorer) speaks these three
record types. Parsers are the only place that knows about raw file layouts.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


@dataclass
class Invoice:
    invoice_id: str
    customer_id: str
    customer_name: str          # name as it appears on the invoice (canonical)
    amount: int                 # KES, integer minor-unit-free (whole shillings)
    issue_date: str             # ISO date
    due_date: str

    @property
    def key(self) -> str:
        return self.invoice_id


@dataclass
class Txn:
    """One line of a mobile-money statement."""
    receipt: str                # e.g. TFA4X9K2LM - unique
    datetime: str               # ISO datetime
    kind: str                   # pay_bill | customer_transfer | reversal | charge
    party_name: str             # raw name string as printed by the operator
    party_phone: str            # masked, e.g. 2547*****553
    paid_in: int                # net credited to the merchant (0 for debits)
    fee: int                    # transaction cost borne by the merchant
    withdrawn: int              # debits (reversals, charges)
    narration: str
    reverses: str | None = None  # receipt of the txn this reverses

    @property
    def gross(self) -> int:
        """Amount the customer actually parted with = net credited + fee.

        This gross-up is the reason a naive amount match on `paid_in` fails:
        an invoice is for the gross, the statement shows the net.
        """
        return self.paid_in + self.fee


@dataclass
class BankLine:
    ref: str
    date: str
    description: str
    amount: int
    settles: list[str] = field(default_factory=list)  # receipts batched into this line


@dataclass
class Case:
    case_id: str
    invoices: list[Invoice]
    txns: list[Txn]
    bank: list[BankLine]
    features: list[str]


# --------------------------------------------------------------------------- IO

def write_case(case: Case, out_dir: Path, truth: dict[str, list[str]]) -> None:
    d = out_dir / case.case_id
    d.mkdir(parents=True, exist_ok=True)

    _write_csv(d / "invoices.csv", [asdict(i) for i in case.invoices])
    _write_csv(d / "mpesa_statement.csv", [asdict(t) for t in case.txns])
    _write_csv(
        d / "bank_statement.csv",
        [{**asdict(b), "settles": "|".join(b.settles)} for b in case.bank],
    )
    (d / "truth.json").write_text(
        json.dumps({"case_id": case.case_id, "features": case.features,
                    "matching": truth}, indent=2), encoding="utf-8"
    )


def read_case(d: Path) -> Case:
    invoices = [Invoice(**_coerce(r, {"amount": int})) for r in _read_csv(d / "invoices.csv")]
    txns = [
        Txn(**_coerce(r, {"paid_in": int, "fee": int, "withdrawn": int},
                      nullable={"reverses"}))
        for r in _read_csv(d / "mpesa_statement.csv")
    ]
    bank = []
    for r in _read_csv(d / "bank_statement.csv"):
        r = dict(r)
        r["settles"] = [s for s in r.get("settles", "").split("|") if s]
        r["amount"] = int(r["amount"])
        bank.append(BankLine(**r))
    truth_path = d / "truth.json"
    features = json.loads(truth_path.read_text(encoding="utf-8"))["features"] if truth_path.exists() else []
    return Case(case_id=d.name, invoices=invoices, txns=txns, bank=bank, features=features)


def read_truth(d: Path) -> dict[str, list[str]]:
    return json.loads((d / "truth.json").read_text(encoding="utf-8"))["matching"]


def _coerce(row: dict[str, str], casts: dict[str, Any], nullable: set[str] = frozenset()):
    out = dict(row)
    for k, fn in casts.items():
        out[k] = fn(out[k])
    for k in nullable:
        if out.get(k) == "":
            out[k] = None
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

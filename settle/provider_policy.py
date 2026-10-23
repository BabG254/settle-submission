"""Provider-policy settlement checks for explicitly linked, synthetic batches."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from .schema import BankLine, Txn
from .tools import reversal_pairs

@dataclass(frozen=True)
class SettlementPolicy:
    name: str
    max_lag_days: int = 3
    fixed_batch_adjustment: int = 0

def verify_provider_batch(line: BankLine, txns: list[Txn], policy: SettlementPolicy) -> list[str]:
    """Check known links and a policy-defined adjustment; never infer identities."""
    errors = []
    if not line.settles:
        return [f"{line.ref}: receipt links are required"]
    by_receipt = {t.receipt: t for t in txns}
    if len(by_receipt) != len(txns):
        errors.append("duplicate transaction IDs")
    invalid = reversal_pairs(txns)
    seen = set()
    net = 0
    for receipt in line.settles:
        if receipt in seen:
            errors.append(f"{line.ref}: repeated receipt {receipt}")
            continue
        seen.add(receipt)
        tx = by_receipt.get(receipt)
        if not tx or tx.kind != "pay_bill" or receipt in invalid:
            errors.append(f"{line.ref}: ineligible receipt {receipt}")
            continue
        lag = (date.fromisoformat(line.date) - datetime.fromisoformat(tx.datetime).date()).days
        if not 0 <= lag <= policy.max_lag_days:
            errors.append(f"{line.ref}: settlement delay out of policy")
        net += tx.paid_in
    expected = net - policy.fixed_batch_adjustment
    if expected != line.amount:
        errors.append(f"{line.ref}: bank amount {line.amount} != expected {expected}")
    return errors

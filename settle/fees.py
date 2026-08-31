"""Synthetic tariff model.

IMPORTANT: this is an *illustrative* fee schedule, not a published operator
tariff. It reproduces the shape that matters for reconciliation -- a stepped
band table plus an ad-valorem duty on the fee itself -- so that the net amount
credited never equals the amount invoiced. No real tariff is claimed or used.
"""
from __future__ import annotations

# (upper_bound_inclusive, base_fee)
BANDS: list[tuple[int, int]] = [
    (100, 0),
    (500, 7),
    (1_000, 13),
    (1_500, 23),
    (2_500, 33),
    (3_500, 53),
    (5_000, 57),
    (7_500, 78),
    (10_000, 90),
    (15_000, 100),
    (20_000, 105),
    (35_000, 108),
    (50_000, 108),
    (250_000, 108),
]

DUTY_RATE = 0.15          # duty charged on the fee, not on the principal
TXN_CAP = 150_000         # single-transaction ceiling -> forces mandatory splits
SETTLEMENT_LAG_DAYS = 1   # operator settles to bank at T+1


def fee_for(gross: int) -> int:
    """Total transaction cost for a payment of `gross` shillings."""
    for upper, base in BANDS:
        if gross <= upper:
            return base + round(base * DUTY_RATE)
    upper, base = BANDS[-1]
    return base + round(base * DUTY_RATE)


def max_fee_upto(gross: int) -> int:
    """Ceiling on the fee for any payment at or below `gross`.

    Used to size the amount-band when searching for candidates: a payment of
    net N corresponds to a gross somewhere in [N, N + max_fee_upto(N + slack)].
    """
    return max(fee_for(min(upper, gross)) for upper, _ in BANDS if True)

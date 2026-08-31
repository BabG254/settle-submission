---
name: mobile-money-forensics
description: How to read a mobile-money merchant statement when reconciling it against invoices. Load when deciding whether a transaction, or a set of transactions, paid a given invoice.
---

# Mobile-money forensics

Domain rules for adjudicating payments against invoices. These are facts about
the medium, not about any one business.

## The amount is never the amount

The statement records the **net** credited to the merchant. The customer parted
with the **gross**. `gross = net_credited + fee`. Always reconcile against
gross. An invoice for 24,000 will appear as a credit of 23,876 with a fee of
124 beside it.

The fee is banded, not proportional, so two payments of very different sizes can
carry the same fee. Never infer the principal from the fee.

## Payments split for structural reasons

A single invoice frequently arrives as several transfers:

- **Mandatory splits** — any amount above the single-transaction ceiling must be
  broken up. An invoice of 175,000 cannot arrive as one payment.
- **Cashflow splits** — a customer pays what they have, when they have it. Parts
  are usually uneven and non-round, and may span two weeks.

Consequences: the parts of a split sum **exactly** to the invoice in gross
terms. If a proposed set is off by any amount, it is the wrong set. Do not
"round to the nearest plausible". A near-miss is a decisive signal that at least
one part is wrong or missing.

## Reversals net to zero

A reversed payment appears twice: the original credit, and a debit reversing it.
The money was never received. **Neither receipt may be matched to any invoice.**
Matching a reversed credit reports revenue that does not exist, which is the
most expensive error available in this task — worse than leaving the invoice
unmatched, because an unmatched invoice gets chased and a falsely matched one
does not.

A customer whose payment was reversed will usually pay again. The later, good
payment is the match.

## Settlement lags the payment

Money reaches the bank at T+1 and arrives batched: one bank line is the day's
net of many transactions minus charges. A bank line therefore has no single
counterparty and cannot be matched to an invoice directly. Reconcile invoices
against the mobile-money statement; reconcile the mobile-money statement against
the bank in aggregate.

## Who actually paid

The printed party name is whatever the payer's SIM is registered as. It carries
four common distortions:

1. **Reordering and middle names.** `GRACE NJERI MWANGI` for Grace Njeri Mwangi.
   Fuzzy matching handles this. It is not ambiguity.
2. **Initialised names.** `M W KARIUKI`, `G N MWANGI`. The surname may be the
   only surviving token, and it may not be the surname on the invoice.
3. **Trading names.** `MAMA NJERI GROCERS` paying an invoice raised to Njeri
   Wambui Enterprises. There may be zero token overlap. The registered name and
   the name over the door are routinely different.
4. **Proxy payers.** A spouse, adult child or employee pays from their own line.
   `JOSEPH KARIUKI` pays Mary W. Kariuki's invoice. Shared surname is weak
   evidence; a shared phone tail is stronger; a prior approved match is
   strongest.

## What counts as evidence, in order of strength

1. A previously approved alias for this exact party name.
2. An exact gross sum with a single payer across all parts.
3. Phone number tail matching a known number for the customer.
4. Strong name overlap.
5. Timing shortly after the invoice date.

Timing alone is never sufficient. Amount alone is never sufficient — an
identical amount from a different customer is a routine occurrence in a business
with a standard price list.

## When to escalate rather than decide

Escalate when any of these hold:

- More than one candidate set sums exactly to the invoice and the payer evidence
  does not separate them.
- No set sums exactly and the shortfall is not explained by a fee.
- The best available payer evidence is a shared surname alone.
- The only candidate is an amount match from a party with no other link.

Escalation is cheap and reversible. A wrong posting is neither. An escalation
that a human clears once becomes an alias, and the same name resolves
automatically thereafter.

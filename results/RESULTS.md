# Results

12 seeded synthetic cases, generated with `--seed 42`. Ground truth is
exact; no LLM judge is used anywhere in scoring. Primary metric is
**value-weighted reconciliation F1** over (invoice, receipt) pairs,
weighted by the gross amount of each transaction.

| System | Cases | Value F1 | Precision | Recall | Invoices exact | Misposted KES | Escalations /100 | Escalation precision | Ledger OK | $/case |
|---|---|---|---|---|---|---|---|---|---|---|
| B. Script matcher (no LLM) | 12 | **0.6863** | 0.9724 | 0.5906 | 63.0% | 168,900 | 0.0 | -- | 83.3% | 0.0 |
| Settle: tools only, no model | 12 | **0.3691** | 0.8333 | 0.2808 | 19.1% | 0 | 80.9 | 0.5302 | 100.0% | 0.0 |
| Ceiling: perfect identity judge | 12 | **1.0** | 1.0 | 1.0 | 100.0% | 0 | 0.0 | -- | 100.0% | 0.0 |

### What each row is

- **B. Script matcher (no LLM)** -- Fuzzy name + amount, greedy 1:1
- **Settle: tools only, no model** -- Retrieval + solver + gate, escalate all ambiguity
- **Ceiling: perfect identity judge** -- Not a solution -- measures headroom in the tool layer

### Reading the table

`Misposted KES` is the value of transactions attached to the wrong
invoice. In this domain it is the error that matters most: an unmatched
invoice gets chased, a falsely matched one is silently written off.

`Escalation precision` is the fraction of queued exceptions where the
system's own unassisted best guess would have been wrong. A system that
escalates everything scores well on mispostings and badly here.

Per-case detail is in the `score_*.json` files beside this one.

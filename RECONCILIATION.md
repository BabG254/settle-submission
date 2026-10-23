# Reconciliation correctness extensions

These APIs are deterministic building blocks for further product integration,
not a claim that Settle is certified accounting or payment software.

## Global assignment

`settle.reconcile.unique_global_matches(invoices, txns)` considers conflicting
invoice-to-receipt choices jointly. It only returns assignments shared by
**every maximum-cardinality feasible solution**. Ambiguous assignments are left
unresolved, not guessed. It uses bounded backtracking and fails closed when
the node limit is reached. The integrated offline command is `python -m settle.reconcile --case data/case01 --out outputs/global-case01.json` after `make data`. It reports ambiguous invoices as exceptions, verifies global ledger constraints and checks linked bank settlement batches. It does not replace the existing AI-assisted `settle.agent` command; its standalone path is deliberately conservative. Benchmarking performance remains future work.

## Bank settlement checks

`settle.reconcile.verify_settlements(bank, txns)` verifies receipt-linked
batch totals against **net credited** amounts, rejects reversed and non-payment
rows, duplicate allocations, invalid dates and unlinked bank lines.
No inferred bank links, provider fee adjustments or settlement completeness
are claimed. In particular, a bank line with no explicit links is unverified,
not automatically reconciled. Future provider adapters must specify the
reconciliation basis, fees and permitted settlement windows.

## Human approvals

`settle.approval_safety.validate_approval` prepares an approval without mutating
the original prediction and rejects duplicate, missing or reused receipts.
The CLI now persists validated JSON with an atomic file replacement before
learning payer aliases. SQLite alias updates and the JSON file are still
separate data stores, so a crash between the two may omit alias learning;
the durable match remains the source of truth. Multi-process file locking
and a shared transactional datastore remain future work.

## Verification

Run `python -m unittest discover -s tests -v` to execute the regression suite.
The existing synthetic benchmark is separate; production deployment remains
out of scope until external reconciliation fixtures and privacy/security
reviews are available.

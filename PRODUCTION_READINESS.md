# Production hardening review

This work adds safeguards, **not certification for production financial use**.

## Recovery after interrupted approvals

An approved invoice is committed to the prediction JSON before writing SQLite
alias memory. If the process crashes between those operations, run:

```shell
python -m settle.recovery --pred results/pred_demo/month01.json \
    --data data/memory_demo --memory-db state/aliases.db
```

Only approvals that remain present in a ledger-valid saved prediction are
replayed. Existing conflicting aliases require manual review. Recovery is
idempotent and serializes against approval writes using the same file lock.
The prediction file must be trusted and access-controlled.

## Windows and Linux locking

`settle.locking.file_lock` supports Windows (`msvcrt`) and POSIX (`fcntl`)
advisory file locking. Every participating process must use the same lock
file. Locks are local filesystem primitives; they are not distributed locks
and are not suitable for multi-host shared storage. The `approve` CLI
holds a lock across its read, validate, atomic write, and alias update.
Windows behavior needs independent Windows-runner CI before claiming verified
cross-platform deployment.

## Global matching performance

```shell
python -m settle.benchmark --invoices 10 --nodes 100000
python -m settle.benchmark --invoices 16 --nodes 100000
```

The exact global search is exponential. To avoid unbounded workloads it
returns **no auto-approved matches** when more than 16 invoices are supplied
or the 100,000-node budget is reached. The benchmark reports elapsed time,
input count and matched count. This is a correctness-first guardrail, not
evidence of viable throughput at enterprise scale. Implement connected
component decomposition and a scalable matching algorithm before larger
production workloads.

## Settlement policy and external validation

`settle.provider_policy` accepts an explicit, versionable
`SettlementPolicy`. The supplied tests contain invented anonymized examples
with synthetic fees and settlement timing, not bank/operator-certified rules.

For genuine provider validation:
1. Obtain operator settlement rules and lawful, de-identified examples.
2. Document payment gross/net semantics, fee source, reversal timing,
   timezone, batch adjustment, maximum delay and currency units.
3. Keep source evidence and approval date alongside fixture metadata.
4. Add pass and fail fixtures independently checked by a qualified accountant.
5. Never place live transaction details, customer identities or secrets in
   a public repository.

## Sensitive data and operational access

JSONL traces now apply best-effort redaction for common emails, Kenyan phone
numbers and known key patterns. **This is not comprehensive anonymization.**
Model prompts, names, addresses, unusual phone formats and free-form
transaction narratives can still contain personal data. Disable tracing
when using real financial information and do not send sensitive identifiers
to a model provider without a lawful basis, consent where required, and
a data-processing/security review.

Minimum controls before any real deployment: least-privilege user accounts,
authenticated approvals, encrypted storage and backups, retention limits,
structured audit logs, secret scanning, private deployments, monitoring,
incident procedures, and applicable privacy/compliance review.

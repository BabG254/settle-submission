# Engineering verification and provenance

This project was initially developed for the micro1 Frontier Engineering Challenge 2026.
The repository's original commit history is preserved. Subsequent improvements are
ordinary, attributable engineering work; no artificial historical activity is claimed.

## Verify from a clean clone

Prerequisites: Python 3.10+, pip, and optionally Docker.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
make offline
docker build -t settle .
```

The test suite uses standard-library unittest, requiring no additional test package.
The offline evaluation generates synthetic data and requires no model API key.
Do not commit real payment data, real API keys, private model traces or SQLite state.

## Scope and limitations

- The synthetic fee schedule is illustrative, not an official M-Pesa tariff.
- The ledger gate validates invoice-to-receipt arithmetic and uniqueness; it
  does not certify bank settlement reconciliation or accounting compliance.
- A perfect-identity oracle benchmark is an upper-bound diagnostic, not real
  model accuracy.
- Matching data is synthetic; production financial use requires additional
  validations, audits, security review and externally sourced evidence.
- No payment, licensing offer or buyer eligibility is implied by these changes.
- Challenge terms, contribution provenance and third-party usage rights must
  be verified before any dataset licensing agreement.

## Future implementation work

1. Test and stage alias writes so rejected matches never enter memory.
2. Define duplicate receipt and malformed input policies.
3. Introduce global assignment for shared/competing receipt candidates.
4. Add independently verified bank settlement reconciliation.
5. Harden approvals with atomic writes, replay prevention and audit trails.
6. Add privacy-safe telemetry and real-world integration acceptance tests.

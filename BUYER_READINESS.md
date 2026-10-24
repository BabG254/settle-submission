# Independent engineering verification and buyer eligibility

## Project classification

Settle is a **Python application / command-line reconciliation toolkit**, not
infrastructure as code. It has no Terraform, Pulumi, Ansible or Helm components.
Adding an artificial IaC directory would misrepresent the product.

## Check from a new clone

```sh
python -m venv .venv
# Activate the virtual environment appropriate for your operating system
python -m pip install -e ".[dev]"
python -m pytest -q
python -m unittest discover -s tests -v
python -m settle.gen --seed 42 --out data
python -m settle.reconcile --case data/case01
```

CI executes pytest, the standard library regression suite, the offline
evaluation and a Docker build. The project includes synthetic financial data
only. Synthetic correctness checks do not prove real-world accuracy.

## Data ownership and buyer criteria

This repository was initially created for the micro1 Frontier Engineering
Challenge 2026 and published publicly. Verify the original challenge agreement,
authorship, third-party rights and whether the proposed data buyer accepts
public/challenge-origin contributions **before** submitting for licensing.
Technical scoring does not constitute a purchase offer.

## Maintain meaningful engineering history

Future feature work should use reviewable pull requests with accompanying tests
for the actual behavior that changed. Never fabricate contributors, backdate
commits, manufacture failing tests or insert irrelevant infrastructure to
increase a machine-generated score. A legitimate development history grows
through sustained real work and review over time.

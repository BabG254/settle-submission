# Settle

**A reconciliation agent for mobile-money payments.**

Built for the micro1 Frontier Engineering Challenge 2026.

---

## The user and the bottleneck

The user is whoever does the books at a small business in a mobile-money
economy — a shop, a wholesaler, a services firm in Nairobi, Dhaka or Manila.

At the end of every month they have three artefacts that do not line up:

- a list of **invoices** raised to customers,
- a **mobile-money statement** with hundreds to thousands of rows,
- a **bank statement** that receives the money a day late, in batches.

They reconcile them by hand. It is slow, and it is slow for reasons that do not
automate away:

| What goes wrong | Why a matcher breaks on it |
|---|---|
| **The amount is never the amount** | The statement shows the net credited; the invoice is for the gross. `gross = net + fee`, and the fee is banded, not proportional. |
| **Payments arrive in pieces** | Above the transaction ceiling a split is mandatory. Below it, customers pay what they have when they have it. Parts are uneven and can span two weeks. |
| **Reversals net to zero** | A reversed payment appears twice, as a credit and a debit. The money never arrived. Matching it reports revenue that does not exist. |
| **Names are not names** | `M W KARIUKI` for Mary W. Kariuki. `MAMA NJERI GROCERS` for Njeri Wambui Enterprises. A husband paying from his own line. |
| **Amounts collide** | A business with a price list has many customers paying the identical figure in the same week. |
| **Settlement lags and aggregates** | One bank line is a whole day's transactions, netted, at T+1. It has no single counterparty. |

The cost is hours a month, revenue mis-stated at filing time, and customers
chased for money they have already paid.

## Why this needs an agent — and where the agent must not be trusted

The problem has two halves that need opposite tools.

**The combinatorial half.** Which subset of these fourteen candidate
transactions sums to exactly 48,000 in gross terms? With fourteen candidates
there are 16,383 non-empty subsets. A language model asked to find the ones that
add up will assert an answer without summing it. This half needs a solver.

**The semantic half.** Is `MAMA NJERI GROCERS` the same commercial entity as
Njeri Wambui Enterprises? There is no token overlap, no shared phone, nothing to
compute. This half needs judgement.

Settle splits the work along that seam. Deterministic tools do retrieval,
arithmetic and search. The model answers exactly one question — *which human is
behind this name* — and a deterministic gate checks its work before anything is
posted.

There is a measurement behind that claim rather than an argument. Running the
whole pipeline with a **perfect identity judge** substituted for the model
scores **value-F1 1.000 on all twelve cases**. The tool layer never loses the
correct answer. So 100% of the remaining error is identity judgement, which is
precisely what the model is asked to do and nothing else.

---

## Design

```
  invoices.csv  ─┐
  mpesa.csv     ─┼─▶  propose_candidates ──▶ subset_solver ──▶ ADJUDICATOR ──▶ VERIFIER
  bank.csv      ─┘    bounded shortlist      exact subsets     (identity)      (falsify)
                      220 rows → 14          meet-in-the-middle    │               │
                                                                   ▼               ▼
                                          alias memory (SQLite) ◀──┴──────▶  ledger gate
                                                                                   │
                                                        reconciled.csv + exceptions.csv
```

| Component | File | Why it is there |
|---|---|---|
| **Bounded retrieval** | `settle/tools.py::propose_candidates` | Keeps the statement out of the context window. On the largest case it reduces 220 rows to at most 14 per invoice, ranked by amount band, date window, fuzzy name, phone tail and memory hit. |
| **Subset solver** | `settle/tools.py::subset_solver` | Meet-in-the-middle enumeration of every combination summing *exactly* to the invoice. Returns all of them, shortest first. More than one result means the data is genuinely ambiguous on amount alone. |
| **Skill** | `skills/mobile-money-forensics/SKILL.md` | The domain knowledge: fee gross-up, split semantics, reversal handling, T+1 settlement, the four ways a payer name gets distorted, and the rules for when to escalate rather than decide. |
| **Adjudicator** | `settle/agent.py::_adjudicate` | Sees one invoice, a shortlist, and the pre-solved combinations. Chooses one or escalates. Explicitly told the arithmetic is already correct and not to redo it. |
| **Verifier subagent** | `settle/agent.py::_verify` | A separate call with an adversarial system prompt and its own context. It sees only the proposal and its evidence, and is told to assume the match is wrong. Explicitly told *not* to check arithmetic. |
| **Ledger gate** | `settle/tools.py::check_ledger` | A hook, not advice. No receipt used twice, no reversed receipt used, parts sum exactly to the invoice. A run that fails cannot complete: offending matches are withdrawn to the exception queue and the gate re-runs. |
| **Alias memory** | `settle/memory.py` | The only thing worth carrying between runs is who is behind a spelling. Written on human approval or high-confidence verifier pass, with the evidence attached. |
| **Human checkpoint** | `settle/approve.py` | Exceptions carry the system's own best guess plus the competing options, so a person accepts or rejects rather than starting from a blank form. Approvals go through the same ledger gate. |

**Nothing is auto-posted.** Low-confidence matches go to `exceptions.csv` with
their evidence. That is the ground-rule 04/05 human control point.

**Processing order matters.** Invoices are resolved least-ambiguous-first, so
confident matches claim their transactions before contested ones compete for
them.

---

## Which model produced these numbers

The model rows below were produced with **`openai/gpt-oss-120b`, served by Groq**
through its OpenAI-compatible endpoint, on the free tier.

Settle is provider-agnostic by construction: the adjudicator and verifier each
ask for one small JSON object, so any chat endpoint serves. `SETTLE_PROVIDER`
selects between the Anthropic API and any OpenAI-compatible URL. **Baseline A
and Settle were run on the same model**, which is what makes the comparison
fair.

### The free tier imposed one real constraint, and it is worth recording

Groq's free tier caps throughput at **8,000 tokens per minute** — a budget for a
whole minute, not per request. **Baseline A does not fit inside it.** Its entire
design is to put the full statement in one prompt, which for these cases is
18,000 to 30,000 tokens. The API rejects the request outright, before any
inference happens:

```
HTTP 413: Request too large ... on tokens per minute (TPM):
Limit 8000, Requested 30574
```

No retry or backoff helps, because the request is structurally too big. Baseline
A therefore ran only on the three smallest cases — `case01`, `case04`, `case09`
— while every other system ran on all twelve.

This is less a gap in the evaluation than a property of the baseline. "Put
everything in the context window" is the approach that stops being deployable
first: it is the only one here whose cost per case scales with statement size
rather than with ambiguity. Settle's bounded retrieval sends at most ~1,800
tokens per invoice whether the statement has 14 rows or 220, which is why it
runs on a tier the baseline cannot.

To keep the comparison honest, results are reported twice: on the full corpus,
and on the three-case subset where every system ran.

---

## Results

12 seeded synthetic cases. Ground truth is exact because the corpus is
generated, so **no LLM judge is used anywhere in scoring**, and the corpus
contains no personal data by construction.

Primary metric: **value-weighted reconciliation F1** over (invoice, receipt)
pairs, weighted by the gross amount of each transaction. Value-weighted rather
than row-weighted because getting a KES 175,000 invoice wrong is not the same
size of mistake as a KES 1,200 one.

The generated table lives in [`results/RESULTS.md`](results/RESULTS.md) and is
regenerated by `make report`. It carries a `Cases` column and flags any row
scored on fewer cases than the rest.

### Full corpus — 12 cases

| System | Value F1 | Precision | Recall | Invoices exact | Misposted KES | Escalations /100 | Ledger OK |
|---|---|---|---|---|---|---|---|
| B. Script matcher (no LLM) | 0.686 | 0.972 | 0.591 | 63.0% | **168,900** | 0.0 | 83.3% |
| Settle: tools only, no model | 0.369 | 0.833 | 0.281 | 19.1% | **0** | 80.9 | 100% |
| **Settle: full** | **[X]** | [X] | [X] | [X] | **[X]** | [X] | [X] |
| Ceiling: perfect identity judge | 1.000 | 1.000 | 1.000 | 100% | 0 | 0.0 | 100% |

### Matched subset — the 3 cases every system could run

| System | Value F1 | Invoices exact | Misposted KES | Escalations /100 |
|---|---|---|---|---|
| A. One direct prompt | 0.667 | 66.7% | 0 | 0.0 |
| B. Script matcher (no LLM) | [X] | [X] | [X] | 0.0 |
| Settle: tools only, no model | 0.270 | 14.9% | 0 | 85.1 |
| **Settle: full** | **[X]** | [X] | [X] | [X] |

Four things to read out of these.

1. **The script baseline is not a straw man.** It gets the fee gross-up right,
   uses the same fuzzy matcher, and reaches 0.686. What it cannot do is search
   combinations or pair reversals — so on the reversal cases it posts KES 29,750
   of revenue that was refunded, and its output fails the ledger gate on 2 of 12
   cases.
2. **The one-shot prompt does not fail by scoring badly — it fails by not
   running.** On the three cases it could execute it reaches 0.667, respectably
   close to the script. On the other nine it never got as far as an answer.
3. **The tool layer alone is safe and useless.** Zero mispostings, but it hands
   81 of every 100 invoices back to the human, and roughly half of those
   escalations were unnecessary. Safety without judgement is just a queue.
4. **The headroom is entirely identity.** The ceiling run proves retrieval and
   search never lose the answer, on any case including the adversarial one.

---

## Running it

```bash
pip install -r requirements.txt

make offline        # corpus + the three runs that need no credentials + report

cp .env.example .env && $EDITOR .env
make estimate       # projected token cost, no API calls
make doctor         # one small call: verifies provider, key and model
make all            # adds baseline A, full Settle, ablations, trajectories
```

On Windows use `.\run.ps1 <target>` instead of `make <target>`; see
[`WINDOWS.md`](WINDOWS.md).

### Reproducing the exact rows above

```bash
SETTLE_PROVIDER=openai \
SETTLE_BASE_URL=https://api.groq.com/openai/v1 \
SETTLE_API_KEY=... \
SETTLE_MODEL=openai/gpt-oss-120b \
SETTLE_TPM=8000 \
SETTLE_REASONING_EFFORT=low \
make agent
```

`SETTLE_TPM` queues requests to stay inside a per-minute token budget, and a
request larger than the whole budget fails immediately rather than retrying. On
this tier the full agent run takes 60-90 minutes; on a paid tier with no
per-minute cap, about 20.

The matched-subset rows come from the same prediction files:

```bash
python -m settle.score --pred-dir results/pred_settle_full --data data \
  --cases case01 case04 case09 --out results/score_settle_subset.json
```

Full instructions, including Docker and expected runtimes, are in
[`REPRODUCE.md`](REPRODUCE.md).

---

## Prior work disclosure

I have previously built graded datasets for settlement reconciliation on another
platform, which is why I chose this problem — I already knew its shape and knew
what a fair grader for it looks like. **All code in this repository was written
from scratch during the competition window.** No prior repository, dataset or
generator was copied in.

Third-party dependencies: `rapidfuzz` (string similarity) and `anthropic` (used
only when `SETTLE_PROVIDER=anthropic`; the OpenAI-compatible path uses the
standard library). Both under their own licences.

## Data and safety

- The customer roster in `settle/gen.py` is invented. No real statement, name,
  phone number or business appears anywhere in this repository.
- Phone numbers in the generated statements are masked in the same shape an
  operator masks them, and are not real subscriber numbers.
- The fee schedule in `settle/fees.py` is an illustrative band table, not a
  published operator tariff. It reproduces the *shape* that matters for
  reconciliation; no real tariff is claimed.
- Because the corpus is synthetic, running it against a third-party free tier
  submits nothing confidential.
- Settle posts nothing anywhere. Its outputs are two CSV files for a human to
  review. There is no write path to any accounting system, by design.
- No credentials are stored in the repository. `.env` is gitignored.

## Failure mode and hot take

See the end of [`CHANGELOG.md`](CHANGELOG.md).
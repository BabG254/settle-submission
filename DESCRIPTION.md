# Description — sized for the 10,000 character limit

Your last paste was 9,100 characters of markdown and the form rejected it, so
the editor is counting more than the raw text — probably the HTML it converts
to. Both versions below are shorter. Use **Version A** first; if it is still
rejected, paste **Version B**.

Paste only what is between the rules. Do not include these instructions.

## Before you paste

The rich-text box may not convert markdown tables. Paste, then check the results
table rendered as a table. If you see literal `|` characters instead, delete it
and use this bullet form, which is 40 characters shorter and always renders:

- **A. One direct prompt** — F1 [X], [X] exact, [X] misposted, ledger OK [X]
- **B. Script matcher, no LLM** — F1 0.686, 63.0% exact, KES 168,900 misposted, ledger OK 83.3%
- **Settle: tools only, no model** — F1 0.369, 19.1% exact, KES 0 misposted, 80.9 escalations/100, ledger OK 100%
- **Settle: full** — F1 [X], [X] exact, [X] misposted, [X] escalations/100, ledger OK [X]
- **Ceiling: perfect identity judge** — F1 1.000, 100% exact, KES 0 misposted, ledger OK 100%

Filling the six `[X]` values adds roughly 60 characters. Both versions have room.

---

# Version A — 8,319 characters

Full version. Everything from the original, with the design table converted to
bullets and the failure-mode section tightened.

---

### The user and the bottleneck

The user is whoever does the books at a small business in a mobile-money economy — a shop, a wholesaler, a services firm in Nairobi, Dhaka or Manila. Every month they hold three artefacts that do not line up: a list of invoices, a mobile-money statement of hundreds to thousands of rows, and a bank statement that receives the money a day late, in batches. They reconcile them by hand.

It resists automation because the failure modes are structural, not cosmetic:

- **The amount is never the amount.** The statement shows the net credited; the invoice is for the gross, and the fee is banded, not proportional.
- **Payments arrive in pieces.** Above the transaction ceiling a split is mandatory; below it, customers pay what they have when they have it.
- **Reversals net to zero.** A refunded payment appears twice, as a credit and a debit. Matching it reports revenue that does not exist.
- **Names are not names.** `M W KARIUKI` for Mary W. Kariuki. `MAMA NJERI GROCERS` for Njeri Wambui Enterprises. A husband paying from his own line.
- **Amounts collide.** A business with a price list has many customers paying the identical figure in the same week.

The cost is hours a month, revenue mis-stated at filing time, and customers chased for money they have already paid.

### Why this needs an agent, and where the agent must not be trusted

The problem has two halves that need opposite tools.

The **combinatorial half**: which subset of fourteen candidate transactions sums to exactly 48,000 in gross terms? Fourteen candidates give 16,383 non-empty subsets. A model asked to find the ones that add up will assert an answer without summing it.

The **semantic half**: is `MAMA NJERI GROCERS` the same commercial entity as Njeri Wambui Enterprises? No token overlap, no shared phone, nothing to compute.

Settle splits the work along that seam. Deterministic tools do retrieval, arithmetic and search. The model answers exactly one question — *which human is behind this name* — and a deterministic gate checks its work before anything is posted.

**There is a measurement behind that claim rather than an argument.** Running the whole pipeline with a perfect identity judge substituted for the model scores **value-F1 1.000 on all twelve cases**. The tool layer never loses the correct answer, so 100% of remaining error is identity judgement. That measurement decided where the model budget went.

### Design

- **Bounded retrieval** — keeps the statement out of the context window. 220 rows become at most 14 per invoice, ranked by amount band, date window, fuzzy name, phone tail and memory hit.
- **Subset solver** — meet-in-the-middle enumeration of every combination summing *exactly* to the invoice. More than one result means the data is genuinely ambiguous on amount alone: that is the signal to involve the model.
- **Skill** (`mobile-money-forensics`) — fee gross-up, split semantics, reversal handling, T+1 settlement, the four ways a payer name gets distorted, and when to escalate rather than decide.
- **Adjudicator + adversarial verifier** — the adjudicator sees one invoice, the shortlist and the pre-solved combinations, and is told the arithmetic is already correct. The verifier is a separate call in its own context, told to assume the match is wrong and find the reason, and told explicitly *not* to check arithmetic.
- **Ledger gate** — a hook, not advice. No receipt used twice, no reversed receipt used, parts sum exactly. A failing run withdraws the offending matches to the exception queue and re-runs. Settle structurally cannot emit an unbalanced ledger.
- **Alias memory** — the only thing worth carrying between runs is who is behind a spelling. Written on human approval or high-confidence verifier pass, with the evidence attached.
- **Human checkpoint** — nothing is auto-posted. Exceptions carry the system's own best guess plus the competing options, so a person accepts or rejects rather than starting from a blank form. Approvals pass the same gate.

### Evaluation

Twelve seeded synthetic cases with exact ground truth, so **no LLM judge is used anywhere in scoring** and the corpus contains **no personal data by construction**. Difficulty escalates from clean 1:1 through fees, splits, hard aliases, proxy payers, reversals, identical-amount decoys and 220-row volume, to an adversarial case combining all of them.

Primary metric: **value-weighted reconciliation F1**, weighted by transaction value, because getting a KES 175,000 invoice wrong is not the same size of mistake as a KES 1,200 one.

Two baselines on identical cases. Baseline A is the obvious agentic approach: whole statement in context, one call. Baseline B is a competent script — same fuzzy matcher, correct fee gross-up, greedy 1:1 — because *"couldn't you have just written a script?"* is the right question to ask, so I measured it instead of arguing with it.

| System | Value F1 | Invoices exact | Misposted KES | Escalations /100 | Ledger OK |
|---|---|---|---|---|---|
| A. One direct prompt | [X] | [X] | [X] | 0 | [X] |
| B. Script matcher, no LLM | 0.686 | 63.0% | 168,900 | 0 | 83.3% |
| Settle: tools only, no model | 0.369 | 19.1% | 0 | 80.9 | 100% |
| **Settle: full** | [X] | [X] | [X] | [X] | [X] |
| Ceiling: perfect identity judge | 1.000 | 100% | 0 | 0 | 100% |

The script baseline is not a straw man — it reaches 0.686. But it cannot search combinations or pair reversals, so it posts **KES 29,750 of revenue that was refunded**, and its output fails the ledger gate on 2 of 12 cases. The tool layer without the model is the opposite failure: zero mispostings, but it hands 81 of every 100 invoices back to the human at an escalation precision of 0.53. Safety without judgement is just a queue.

### Improvement changelog

Full table with a reproducible command per row in `CHANGELOG.md`. Largest single contributor: [X]. Removed experiment: giving the adjudicator the whole statement instead of the 14-row shortlist — [X].

### Reproduction

`make offline` builds the corpus and runs the three credential-free rows; `make all` adds the model runs. `docker build -t settle . && docker run --rm settle make report` reproduces the credential-free numbers exactly — the build runs `make offline` as a self-test, so a broken image fails at build time rather than in front of a judge. Model versions, runtimes and measured cost-per-case are in `REPRODUCE.md`. Every number above traces to a file in `results/`.

### Main failure mode

**Shared-surname proxy payments.** `JOSEPH KARIUKI` pays Mary W. Kariuki's invoice from his own line. The evidence is real — surname, timing, exact amount — and still insufficient, because a relative settling a different invoice looks identical. A model reading it in isolation over-trusts the surname: surname overlap plus a correct amount *feels* like convergent evidence when it is one weak signal counted twice. Three defences, in the order added: the skill states that a shared surname alone is weak; the verifier is asked specifically whether the payer link is nothing more than a shared surname; and once a human approves one, the alias store makes it a matter of record rather than judgement.

### Hot take

Every failure mode I removed came from letting the model do something a function could do. The ceiling run put a number on it: with arithmetic and search handled in code, a perfect identity judge scores 1.000 — so there was never any accuracy hiding in "let the model reason over the raw data". There was only accuracy hiding in *which human is behind this name*, which is the one thing code genuinely cannot do.

The lever was not a better prompt. It was shrinking the agent's job description until only the ambiguous part was left, then putting a gate behind it that the model cannot argue with. Next time I would measure that ceiling first: it costs an hour and tells you how much of your error budget is retrieval and how much is judgement. I built the adjudicator before I knew the split.

### Prior work disclosure

Prior experience building graded datasets for settlement reconciliation on another platform, which is why I chose this problem. All code here was written from scratch during the competition window. Dependencies: `anthropic` and `rapidfuzz`; everything else is standard library.

---

# Version B — 7,627 characters

Fallback if A is still rejected. Same structure; the changelog paragraph is
folded into Evaluation, and the failure mode and hot take share one section. It
loses no scored content — all six judging dimensions are still present.

---

### The user and the bottleneck

Whoever does the books at a small business in a mobile-money economy — a shop, a wholesaler, a services firm in Nairobi, Dhaka or Manila. Every month they hold three artefacts that do not line up: a list of invoices, a mobile-money statement of hundreds to thousands of rows, and a bank statement that receives the money a day late, in batches. They reconcile them by hand.

It resists automation because the failure modes are structural:

- **The amount is never the amount.** The statement shows the net credited; the invoice is for the gross, and the fee is banded, not proportional.
- **Payments arrive in pieces.** Above the transaction ceiling a split is mandatory; below it, customers pay what they have when they have it.
- **Reversals net to zero.** A refunded payment appears twice, as a credit and a debit. Matching it reports revenue that does not exist.
- **Names are not names.** `M W KARIUKI` for Mary W. Kariuki. `MAMA NJERI GROCERS` for Njeri Wambui Enterprises. A husband paying from his own line.
- **Amounts collide.** A business with a price list has many customers paying the identical figure in the same week.

The cost is hours a month, revenue mis-stated at filing time, and customers chased for money they have already paid.

### Why this needs an agent, and where the agent must not be trusted

Two halves that need opposite tools. The **combinatorial half**: which subset of fourteen candidates sums to exactly 48,000 in gross terms? Fourteen candidates give 16,383 non-empty subsets, and a model asked to find the ones that add up will assert an answer without summing it. The **semantic half**: is `MAMA NJERI GROCERS` the same entity as Njeri Wambui Enterprises? No token overlap, no shared phone, nothing to compute.

Settle splits the work along that seam. Deterministic tools do retrieval, arithmetic and search. The model answers one question — *which human is behind this name* — and a deterministic gate checks its work before anything is posted.

**There is a measurement behind that rather than an argument.** Running the whole pipeline with a perfect identity judge substituted for the model scores **value-F1 1.000 on all twelve cases**. The tool layer never loses the correct answer, so 100% of remaining error is identity judgement. That decided where the model budget went.

### Design

- **Bounded retrieval** — keeps the statement out of the context window: 220 rows become at most 14 per invoice, ranked by amount band, date window, fuzzy name, phone tail and memory hit.
- **Subset solver** — meet-in-the-middle enumeration of every combination summing *exactly* to the invoice. More than one result means genuine ambiguity on amount alone: the signal to involve the model.
- **Skill** (`mobile-money-forensics`) — fee gross-up, split semantics, reversal handling, T+1 settlement, the four ways a payer name gets distorted, and when to escalate rather than decide.
- **Adjudicator + adversarial verifier** — the adjudicator sees one invoice, the shortlist and the pre-solved combinations, and is told the arithmetic is already correct. The verifier is a separate call in its own context, told to assume the match is wrong and told explicitly *not* to check arithmetic.
- **Ledger gate** — a hook, not advice. No receipt twice, no reversed receipt, parts sum exactly. A failing run withdraws the offending matches to the exception queue and re-runs. Settle structurally cannot emit an unbalanced ledger.
- **Alias memory** — the only thing worth carrying between runs is who is behind a spelling. Written on human approval or high-confidence verifier pass, with evidence attached.
- **Human checkpoint** — nothing is auto-posted. Exceptions carry the system's own best guess plus the competing options, so a person accepts or rejects rather than starting from a blank form.

### Evaluation

Twelve seeded synthetic cases with exact ground truth, so **no LLM judge is used anywhere in scoring** and the corpus contains **no personal data by construction**. Difficulty escalates from clean 1:1 through fees, splits, hard aliases, proxy payers, reversals, identical-amount decoys and 220-row volume, to an adversarial case combining all of them.

Primary metric: **value-weighted reconciliation F1**, weighted by transaction value. Two baselines on identical cases: one direct prompt with the whole statement in context, and a competent script — same fuzzy matcher, correct fee gross-up, greedy 1:1 — because *"couldn't you have just written a script?"* is the right question to ask, so I measured it instead of arguing with it.

| System | Value F1 | Invoices exact | Misposted KES | Escalations /100 | Ledger OK |
|---|---|---|---|---|---|
| A. One direct prompt | [X] | [X] | [X] | 0 | [X] |
| B. Script matcher, no LLM | 0.686 | 63.0% | 168,900 | 0 | 83.3% |
| Settle: tools only, no model | 0.369 | 19.1% | 0 | 80.9 | 100% |
| **Settle: full** | [X] | [X] | [X] | [X] | [X] |
| Ceiling: perfect identity judge | 1.000 | 100% | 0 | 0 | 100% |

The script baseline is not a straw man — it reaches 0.686. But it cannot search combinations or pair reversals, so it posts **KES 29,750 of revenue that was refunded** and fails the ledger gate on 2 of 12 cases. The tool layer without the model is the opposite failure: zero mispostings, but 81 of every 100 invoices go back to the human at an escalation precision of 0.53. Safety without judgement is just a queue.

Full changelog with a reproducible command per row in `CHANGELOG.md`. Largest single contributor: [X]. Removed experiment: giving the adjudicator the whole statement instead of the 14-row shortlist — [X].

### Reproduction

`make offline` builds the corpus and runs the three credential-free rows; `make all` adds the model runs. `docker build -t settle . && docker run --rm settle make report` reproduces the credential-free numbers exactly — the build runs `make offline` as a self-test, so a broken image fails at build time rather than in front of a judge. Versions, runtimes and measured cost-per-case are in `REPRODUCE.md`. Every number above traces to a file in `results/`.

### Main failure mode and hot take

**Shared-surname proxy payments.** `JOSEPH KARIUKI` pays Mary W. Kariuki's invoice from his own line. The evidence is real — surname, timing, exact amount — and still insufficient, because a relative settling a different invoice looks identical. A model reading it in isolation over-trusts the surname: surname overlap plus a correct amount *feels* like convergent evidence when it is one weak signal counted twice.

Every failure mode I removed came from letting the model do something a function could do. The ceiling run put a number on it: with arithmetic and search handled in code, a perfect identity judge scores 1.000 — so there was never any accuracy hiding in "let the model reason over the raw data". There was only accuracy hiding in *which human is behind this name*, which is the one thing code genuinely cannot do. The lever was not a better prompt; it was shrinking the agent's job description until only the ambiguous part was left, then putting a gate behind it that the model cannot argue with. Next time I would measure that ceiling first — it costs an hour and tells you how much of your error budget is retrieval and how much is judgement.

### Prior work disclosure

Prior experience building graded datasets for settlement reconciliation on another platform, which is why I chose this problem. All code here was written from scratch during the competition window. Dependencies: `anthropic` and `rapidfuzz`; everything else is standard library.

---

## If B is somehow still too long

Cut in this order:

1. The last bullet under Design, "Human checkpoint" (−300). Mention it in the video instead.
2. The "Amounts collide" and "Payments arrive in pieces" bullets in the problem list (−290). The other three carry the argument.
3. The last sentence of the hot take, "Next time I would measure that ceiling first…" (−200).

Do **not** cut the ceiling-measurement paragraph, the ledger gate bullet, the
results table, or the prior work disclosure. Those are load-bearing — the first
three for scoring, the last for ground rule 02.

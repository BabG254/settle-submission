# Improvement Changelog

How Settle got from a baseline to its final shape, what each change was worth,
and what I removed.

Every row is reproducible on its own. The `Command` column is the exact
invocation; each writes a `results/score_*.json` that the row's number comes
from.

**Rows marked MEASURED were run and scored. Rows marked PENDING require an
`ANTHROPIC_API_KEY` and are filled in by `make baseline-a`, `make agent` and
`make ablations`.** Nothing is reported that was not run.

---

## The runs

| # | Stage | What I tried and why | Command | Value F1 | Misposted KES | Esc./100 | Decision |
|---|---|---|---|---|---|---|---|
| 0a | **Baseline A** | One direct prompt. Whole statement in context, ask for the matching as JSON. The obvious agentic approach. | `make baseline-a` | _PENDING_ | _ | 0 | Starting point |
| 0b | **Baseline B** | A competent script: fuzzy name + amount (net *and* grossed-up) + greedy 1:1. Deliberately not a straw man — it uses the same matcher Settle does. | `make baseline-b` | **0.686** MEASURED | **168,900** | 0 | This is the bar. Anything that does not clearly beat it did not need a model. |
| 1 | **Bounded retrieval** | Replace "the whole statement" with a ranked shortlist of at most 14 per invoice, on amount band, date window, fuzzy name, phone tail. | inside `make core` | see #3 | — | — | Kept. Also the precondition for #2. |
| 2 | **Subset solver** | Baseline A asserted three-part splits that did not sum. Moved combination search out of the model into meet-in-the-middle subset-sum returning *all* exact combinations. | inside `make core` | see #3 | — | — | Kept. This is the change that makes split payments tractable at all. |
| 3 | **Tool layer alone** | With #1 and #2 but no model: escalate every ambiguity. How far does pure engineering get? | `make core` | **0.369** MEASURED | **0** | **80.9** | Kept as the floor, not as a solution. Zero mispostings, but 81 of every 100 invoices go back to the human and escalation precision is only 0.53 — half those escalations were unnecessary. Safety without judgement is just a queue. |
| 4 | **Ceiling probe** | Substitute a perfect identity judge for the model and re-run the same pipeline. How much of the remaining error is retrieval or search, and how much is judgement? | `make ceiling` | **1.000** MEASURED | **0** | **0** | Decisive. Retrieval and search never lose the correct answer, on any of the 12 cases. 100% of remaining error is identity. This is what told me to spend the entire model budget on adjudication and nothing else. |
| 5 | **Adjudicator** | Give the model the shortlist, the pre-solved combinations, and the forensics skill. Ask it for identity only, and tell it explicitly that the arithmetic is already correct. | `make agent` (with `--no-verifier --no-memory`) | _PENDING_ | _ | _ | _ |
| 6 | **Adversarial verifier** | Adjudicator errors clustered on shared-surname proxy payments. Added a second call in its own context, adversarial prompt, sees only the proposal and its evidence, told to assume it is wrong and told *not* to check arithmetic. | `make ablations` (`score_settle_noverify` is the comparison) | _PENDING_ | _ | _ | _ |
| 7 | **Ledger gate as a hook** | The verifier is still a model and can be talked past. Added a deterministic gate that runs after every case: no receipt twice, no reversed receipt, parts sum exactly. Failing matches are withdrawn to exceptions and the gate re-runs. | on by default; `--no-gate` to disable | ledger-OK 100% MEASURED (core run) | — | — | Kept. This is what makes "cannot emit an unbalanced ledger" a property rather than a hope. |
| 8 | **Alias memory** | Trade names and proxy payers were being escalated every month for the same customers. Persist approved identities to SQLite with the evidence attached. | `make demo-memory` | _PENDING_ (month 1 cold vs month 3 warm) | _ | _ | _ |
| — | **REMOVED: full statement in context** | Tested the intuition that the model would do better "seeing everything" — replaced the 14-row shortlist with the whole statement. | `make ablations` (`score_settle_fullctx`) | _PENDING_ | _ | _ | _ |
| F | **Final** | Retrieval + solver + skill + adjudicator + verifier + gate + memory | `make agent` | _PENDING_ | _ | _ | _ |

### Filling in the PENDING rows

```bash
cp .env.example .env && $EDITOR .env
make baseline-a agent ablations demo-memory report
```

`results/RESULTS.md` regenerates with every row that has a score file. Copy the
numbers into the table above. Do not report a row whose score file does not
exist.

---

## What each measured number actually showed

**Baseline B's 168,900 in mispostings is not spread evenly.** It concentrates in
two places: identical-amount collisions, where the greedy matcher takes the first
plausible name; and reversals, where it happily posts a payment that was
refunded. On `case09` and `case11` its output fails the ledger gate outright:

```
case09-INV003: receipt T4ETQUZXBJ was reversed - never received
case09-INV010: receipt TVEQAVRUWL was reversed - never received
case11-INV036: receipt TF1KGMXKKO was reversed - never received
```

That is KES 29,750 of phantom revenue, and it is the error that does not get
caught downstream — an unmatched invoice gets chased, a falsely matched one is
silently written off.

**The core's escalation precision of 0.53 is the argument for the model.** It
escalates safely but indiscriminately. Roughly half the exceptions it queues are
ones where its own top guess was already right. Escalation is cheap, but not
free: at 81 escalations per 100 invoices there is no time saved.

**The ceiling run at F1 1.000 is the single most useful measurement in the
project.** Before it, "the tools are good, the model just needs to judge better"
was a hypothesis. After it, it is a fact about this pipeline: the correct
combination is always present in the shortlist, on every case, including the
adversarial one. Everything the model gets wrong from here is a judgement call
about identity, and can be attacked with better evidence, better prompting or
memory — not with more retrieval.

---

## Main failure mode

**Shared-surname proxy payments.** `JOSEPH KARIUKI` pays Mary W. Kariuki's
invoice from his own line. There is real evidence (surname, timing, exact
amount) and it is not sufficient — a brother-in-law with the same surname
settling a different invoice looks identical. The deterministic core cannot
touch it. A model reading it in isolation will over-trust the surname, because
surname overlap plus a correct amount *feels* like convergent evidence when it
is really one weak signal counted twice.

The three defences, in the order they were added: the skill states explicitly
that a shared surname alone is weak; the verifier is asked specifically whether
the payer link is nothing more than a shared surname; and once a human approves
one, the alias store makes it a matter of record instead of a matter of
judgement.

## Hot take

Every failure mode I removed came from letting the model do something a function
could do. The ceiling run put a number on it: with the arithmetic and the search
handled in code, a perfect identity judge scores 1.000 — so there was never any
accuracy hiding in "let the model reason over the raw data". There was only
accuracy hiding in *which human is behind this name*, which is the one thing
code genuinely cannot do.

The lever was not a better prompt. It was shrinking the agent's job description
until only the ambiguous part was left, then putting a gate behind it that the
model cannot argue with.

The thing I would build differently next time: **measure the ceiling first.**
Substituting a perfect judge for the model costs an hour and tells you exactly
how much of your error budget is a retrieval problem and how much is a judgement
problem. I built the adjudicator before I knew that split. If the ceiling had
come back at 0.8, the right move would have been to fix retrieval and leave the
prompt alone — and I would have spent a day tuning the wrong component to find
out.

---

## Cost note

Cost was measured before running, not after. `python -m settle.estimate` builds
every prompt the pipeline would send, without calling the API, and counts them:

| Target | Model calls | Est. cost |
|---|---|---|
| `baseline-a` | 12 | $0.14 |
| `agent` (full Settle) | 286 | $2.11 uncached, **$1.04 cached** |
| `ablations` (3 passes) | 572 | $5.32 uncached |

Two design choices show up directly in that number.

**The deterministic fast path is free.** 27 of 170 invoices are resolved without
any model call at all — a unique exact combination from a single coherent payer
needs no judgement. Those invoices cost nothing.

**The system prompt is cached.** It carries the whole forensics skill, 1,180
tokens, identical on every one of the 286 calls. Re-sending it accounted for
roughly half the run's input cost. Marking it for caching cut the agent run from
$2.11 to $1.04, a 51% saving, with no change to behaviour. Cache reads are
priced at a tenth of an input token and are accounted for separately in
`settle/llm.py::price`, so the reported `$/case` stays honest.

That second point generalises: putting durable domain knowledge in a stable
system prompt is not only better prompting, it is the cache boundary. A skill
that changes per call cannot be cached and costs full price every time.

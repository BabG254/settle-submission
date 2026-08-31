# Submission pack

Everything below is ready to paste. Numbers in **bold** are measured and already
in the repo. Numbers in `[BRACKETS]` come from the runs that need your API key —
run `make baseline-a agent ablations report` and fill them in before submitting.

---

# 1. Title

```
Settle — a mobile-money reconciliation agent that cannot post an unbalanced ledger
```

Alternates if you want it shorter:

- `Settle: bounded agents for mobile-money reconciliation`
- `Settle — matching payments a script can't identify and a prompt can't count`

---

# 2. Description

*(Paste into the rich-text box. Headings are H3, the tables are real tables —
the editor's table button handles them. Keep the structure; judges skim.)*

---

### The user and the bottleneck

The user is whoever does the books at a small business in a mobile-money economy
— a shop, a wholesaler, a services firm in Nairobi, Dhaka or Manila. Every month
they hold three artefacts that do not line up: a list of invoices, a
mobile-money statement of hundreds to thousands of rows, and a bank statement
that receives the money a day late, in batches. They reconcile them by hand.

It resists automation because the failure modes are structural, not cosmetic:

- **The amount is never the amount.** The statement shows the net credited; the
  invoice is for the gross. The fee is banded, not proportional.
- **Payments arrive in pieces.** Above the transaction ceiling a split is
  mandatory; below it, customers pay what they have when they have it. Parts are
  uneven and span weeks.
- **Reversals net to zero.** A refunded payment appears twice, as a credit and a
  debit. Matching it reports revenue that does not exist.
- **Names are not names.** `M W KARIUKI` for Mary W. Kariuki. `MAMA NJERI
  GROCERS` for Njeri Wambui Enterprises. A husband paying from his own line.
- **Amounts collide.** A business with a price list has many customers paying the
  identical figure in the same week.

The cost is hours a month, revenue mis-stated at filing time, and customers
chased for money they have already paid.

### Why this needs an agent, and where the agent must not be trusted

The problem has two halves that need opposite tools.

The **combinatorial half**: which subset of fourteen candidate transactions sums
to exactly 48,000 in gross terms? Fourteen candidates give 16,383 non-empty
subsets. A model asked to find the ones that add up will assert an answer
without summing it.

The **semantic half**: is `MAMA NJERI GROCERS` the same commercial entity as
Njeri Wambui Enterprises? No token overlap, no shared phone, nothing to compute.

Settle splits the work along that seam. Deterministic tools do retrieval,
arithmetic and search. The model answers exactly one question — *which human is
behind this name* — and a deterministic gate checks its work before anything is
posted.

**There is a measurement behind that claim rather than an argument.** Running the
whole pipeline with a perfect identity judge substituted for the model scores
**value-F1 1.000 on all twelve cases**. The tool layer never loses the correct
answer, so 100% of the remaining error is identity judgement. That measurement
is what decided where the model budget went.

### Design

| Component | Why it is there |
|---|---|
| **Bounded retrieval** | Keeps the statement out of the context window. On the largest case, 220 rows become at most 14 per invoice, ranked by amount band, date window, fuzzy name, phone tail and memory hit. |
| **Subset solver** | Meet-in-the-middle enumeration of every combination summing *exactly* to the invoice, shortest first. More than one result means the data is genuinely ambiguous on amount alone — which is the signal to involve the model. |
| **Skill** (`mobile-money-forensics`) | Fee gross-up, split semantics, reversal handling, T+1 settlement, the four ways a payer name gets distorted, and explicit rules for when to escalate rather than decide. |
| **Adjudicator** | Sees one invoice, the shortlist and the pre-solved combinations. Told explicitly that the arithmetic is already correct and not to redo it. Chooses one combination or escalates. |
| **Adversarial verifier subagent** | A separate call in its own context, told to assume the match is wrong and to look for the reason. Told explicitly *not* to check arithmetic. |
| **Ledger gate** | A hook, not advice. No receipt used twice, no reversed receipt used, parts sum exactly. A run that fails withdraws the offending matches to the exception queue and re-runs the gate. Settle structurally cannot emit an unbalanced ledger. |
| **Alias memory** | The only thing worth carrying between runs is who is behind a spelling. Written on human approval or high-confidence verifier pass, with the evidence attached. |
| **Human checkpoint** | Nothing is auto-posted. Exceptions carry the system's own best guess plus competing options, so a person accepts or rejects rather than starting from a blank form. Approvals go through the same gate. |

### Evaluation

Twelve seeded synthetic cases with exact ground truth, so **no LLM judge is used
anywhere in scoring** and the corpus contains **no personal data by
construction**. Difficulty escalates from clean 1:1 through fees, splits, hard
aliases, proxy payers, reversals, identical-amount decoys and 220-row volume, to
an adversarial case combining all of them.

Primary metric is **value-weighted reconciliation F1** — weighted by transaction
value, because getting a KES 175,000 invoice wrong is not the same size of
mistake as a KES 1,200 one.

Two baselines, on identical cases. Baseline A is the obvious agentic approach:
whole statement in context, one call. Baseline B is a competent script — same
fuzzy matcher, correct fee gross-up, greedy 1:1 — because *"couldn't you have
just written a script?"* is the right question to ask, so I measured it.

| System | Value F1 | Invoices exact | Misposted KES | Escalations /100 | Ledger OK |
|---|---|---|---|---|---|
| A. One direct prompt | `[X]` | `[X]` | `[X]` | 0 | `[X]` |
| B. Script matcher, no LLM | **0.686** | **63.0%** | **168,900** | 0 | **83.3%** |
| Settle: tools only, no model | **0.369** | **19.1%** | **0** | **80.9** | **100%** |
| **Settle: full** | `[X]` | `[X]` | `[X]` | `[X]` | `[X]` |
| Ceiling: perfect identity judge | **1.000** | **100%** | **0** | **0** | **100%** |

Three findings from the rows that need no API key:

1. **The script baseline is not a straw man** — it reaches 0.686. But it cannot
   search combinations or pair reversals, so it posts **KES 29,750 of revenue
   that was refunded**, and its output fails the ledger gate on 2 of 12 cases.
2. **The tool layer alone is safe and useless** — zero mispostings, but it hands
   81 of every 100 invoices back to the human, and its escalation precision is
   only 0.53. Safety without judgement is just a queue.
3. **The headroom is entirely identity** — the ceiling run proves retrieval and
   search never lose the answer, on any case including the adversarial one.

### Improvement changelog

Full table with per-row commands in `CHANGELOG.md`. Largest single contributor:
`[X]`. Removed experiment: giving the adjudicator the whole statement instead of
the 14-row shortlist — `[X]`.

### Reproduction

```
make offline    # corpus + three runs, no credentials needed
make all        # adds the model runs
```

`docker build -t settle . && docker run --rm settle make report` reproduces the
three credential-free rows exactly; the build runs `make offline` as a self-test,
so a broken image fails at build time. Model versions, runtimes and measured
cost-per-case are in `REPRODUCE.md`. Every number in this description traces to a
file in `results/`.

### Main failure mode

**Shared-surname proxy payments.** `JOSEPH KARIUKI` pays Mary W. Kariuki's
invoice from his own line. There is real evidence — surname, timing, exact
amount — and it is not sufficient, because a relative settling a different
invoice looks identical. A model reading it in isolation over-trusts the
surname, since surname overlap plus a correct amount *feels* like convergent
evidence when it is one weak signal counted twice. Three defences, in the order
added: the skill says a shared surname alone is weak; the verifier is asked
specifically whether the payer link is nothing more than a shared surname; and
once a human approves one, the alias store makes it a matter of record rather
than a matter of judgement.

### Hot take

Every failure mode I removed came from letting the model do something a function
could do. The ceiling run put a number on it: with arithmetic and search handled
in code, a perfect identity judge scores 1.000 — so there was never any accuracy
hiding in "let the model reason over the raw data". There was only accuracy
hiding in *which human is behind this name*, which is the one thing code
genuinely cannot do.

The lever was not a better prompt. It was shrinking the agent's job description
until only the ambiguous part was left, then putting a gate behind it that the
model cannot argue with.

What I would do differently: **measure the ceiling first.** Substituting a
perfect judge for the model costs an hour and tells you exactly how much of your
error budget is a retrieval problem and how much is a judgement problem. I built
the adjudicator before I knew that split. If the ceiling had come back at 0.8,
the right move would have been to fix retrieval and leave the prompt alone.

### Prior work disclosure

I have previously built graded datasets for settlement reconciliation on another
platform, which is why I chose this problem — I already knew its shape and what a
fair grader for it looks like. All code in this repository was written from
scratch during the competition window. Dependencies: `anthropic` and
`rapidfuzz`. Everything else is standard library.

---

# 3. Video script

Record at 5:00 or under. Terminal at a large font — judges may watch on a phone.

**Before you record**, run this so every command below returns instantly:

```bash
make offline
cp .env.example .env && $EDITOR .env
make baseline-a agent report
rm -f state/demo.db
python3 -m settle.agent --data data/memory_demo --cases month01 \
  --out results/pred_demo --outputs outputs/demo --memory-db state/demo.db
```

Open four terminal tabs: (1) data, (2) baselines, (3) Settle, (4) the memory
demo. Switching tabs is faster and calmer on camera than re-typing.

---

### [0:00 – 0:35] The problem

*Tab 1. `column -s, -t < data/case12/mpesa_statement.csv | less` — scroll it.
Let it feel long.*

> This is a month of mobile-money transactions for a small business. Eighty-eight
> rows here, two hundred and twenty in the big case. Next to it sits a list of
> invoices, and a bank statement that settles a day late.
>
> Somebody reconciles these by hand every month, and it's slow for reasons that
> don't automate away. The statement shows the net credited — the invoice is for
> the gross, so the amounts never match. One invoice arrives as three separate
> transfers. Payments that were refunded still sit in the statement. And the
> customer's name is `M W KARIUKI`, or their husband's name, or their shop's name.
>
> The cost isn't just hours. It's revenue mis-stated at filing, and customers
> chased for money they already paid.

### [0:35 – 1:20] The baselines, and why the script one matters

*Tab 2. `make baseline-b`, then show the result line.*

> Two baselines. The first is the obvious one: put the whole statement in the
> context window and ask a model for the matching in one call.
>
> The second is the one I think matters more — a competent script. Same fuzzy
> matcher I use, correct fee gross-up, greedy one-to-one. Because "couldn't you
> have just written a script" is the right question to ask, so I measured it
> instead of arguing with it.
>
> It gets value-weighted F1 of **0.686**. That's not a straw man. But look at
> what it costs:

*Run:*
```bash
python3 -c "import json;d=json.load(open('results/pred_baseline_b/case09.json'));[print(' ',e) for e in d['ledger_errors'][:4]]"
```

> It posted three payments that were **reversed**. That money was refunded. It's
> reporting revenue that doesn't exist — twenty-nine thousand seven hundred and
> fifty shillings of it — and its output fails a ledger check on two of the
> twelve cases. An unmatched invoice gets chased. A falsely matched one is
> silently written off.

### [1:20 – 3:05] One real execution

*Tab 3. `make agent` or a pre-recorded run. Narrate over the live output.*

> Settle splits the problem along the line where models are actually reliable.
>
> **First, bounded retrieval.** For each invoice, a ranked shortlist — amount
> band, date window, fuzzy name, phone tail. Two hundred and twenty rows become
> fourteen. The full statement never enters the context window, and I'll come
> back to why.
>
> **Second, the arithmetic.** Which of these fourteen sum to exactly the invoice?
> That's subset-sum, so it's a solver — meet-in-the-middle — not a prompt. It
> returns *every* exact combination, not one.

*Switch to the exception queue and show this specific invoice:*

```bash
python3 -m settle.approve --pred results/pred_demo/month01.json \
  --data data/memory_demo --invoice x --list
```

> And here's the whole thesis in one screen. This invoice is forty-eight
> thousand. **Three** different combinations sum to exactly forty-eight
> thousand. One from `MILLICENT OWUOR`. One from `BEATRICE ADHIAMBO`, in two
> parts. One from three complete strangers who happen to add up.
>
> Amount tells you nothing here. Timing tells you nothing. The customer is Esther
> Akinyi Owuor — and the only thing that separates these is judgement about who
> `MILLICENT OWUOR` is.
>
> **That's the third step, and it's the only thing I ask the model to do.** It
> gets the shortlist, the pre-solved combinations, and a skill file with the
> domain rules. It's told the arithmetic is already correct and not to redo it.
>
> **Fourth, a verifier in a separate context.** Adversarial prompt: assume this
> match is wrong, find the reason. Is the payer link nothing more than a shared
> surname? It's told explicitly *not* to check arithmetic.
>
> **And then the gate.**

*Point at the ledger gate line in the output.*

> This is a hook, not a prompt. No receipt used twice, no reversed receipt used,
> parts sum exactly. If it fails, the run doesn't complete — the offending
> matches get withdrawn to the exceptions queue and it re-runs. Settle cannot
> emit an unbalanced ledger, no matter what the model believes.
>
> Output is two files a bookkeeper opens: a reconciled ledger, and an exceptions
> queue with the evidence attached to every row.

### [3:05 – 3:40] Memory

*Tab 4.*

> One more thing. Month one, cold memory. It escalates this name — correctly, it
> doesn't know yet. I clear it, the way a bookkeeper would:

```bash
python3 -m settle.approve --pred results/pred_demo/month01.json \
  --data data/memory_demo --invoice month01-INV006 --option 1 \
  --memory-db state/demo.db
```

*Read the output aloud — it prints the learned alias.*

> That approval went through the same ledger gate, and it wrote one row: `DANIEL
> BETT` is Anne Chepkoech Bett. Now month three — same customers, same messy
> names.

*Run month03. Show the lower exception count.*

> Fewer escalations. **No code changed between those two runs.** The system got
> better because it was used.

### [3:40 – 4:25] The numbers, and the measurement I'm proudest of

*Show `results/RESULTS.md`.*

> Twelve seeded cases, exact ground truth, no LLM judge anywhere in the scoring.
>
> Script alone: **0.686**, with a hundred and sixty-eight thousand shillings
> mis-posted. One-shot prompt: `[X]`. Settle: `[X]`.
>
> But the row I care about most is the last one. I ran the whole pipeline with a
> **perfect identity judge** swapped in for the model — a ceiling probe. It
> scores **1.000 on all twelve cases**, including the adversarial one.
>
> That's not a result, it's a diagnosis. It means retrieval and the solver never
> lose the correct answer. So a hundred percent of my remaining error is identity
> judgement — and that told me exactly where to spend the model budget, and where
> not to.

### [4:25 – 4:50] Changelog

> The biggest single gain was `[X]`.
>
> The experiment I removed: I gave the adjudicator the whole statement instead of
> the fourteen-row shortlist, on the theory it would do better seeing everything.
> It got **worse** — `[X]`. More context, less precision. That's in the changelog
> with its own reproducible command.
>
> There's also a row that looks like a failure and isn't: the tool layer with the
> model removed scores only **0.369** — but zero mis-postings. It escalates
> eighty-one invoices in every hundred. Safe, and useless. That gap is the case
> for the agent.

### [4:50 – 5:00] Close

> My takeaway: every failure I removed came from letting the model do something a
> function could do. The lever wasn't a better prompt — it was shrinking the
> agent's job until only the ambiguous part was left, and putting a gate behind
> it the model can't argue with.
>
> And if I built this again I'd measure the ceiling first. `docker build` and
> `make offline` reproduces the credential-free numbers exactly. Thanks for
> watching.

---

### Recording notes

- **Don't narrate architecture over a static diagram.** Narrate it over the thing
  running.
- The three-combinations screen at 2:10 and the reversal errors at 1:05 are the
  two moments that carry the submission. If you cut for time, cut elsewhere.
- If a live run is slow, pre-record and speed up the dull middle — but never cut
  the gate output or the verifier catch.
- 5:00 is a ceiling, not a target. 4:15 tight beats 4:59 padded.

---

# 4. Submission checklist

- [ ] `make baseline-a agent ablations report` run, `[X]` placeholders filled in
      **in both `CHANGELOG.md` and the description above**
- [ ] Re-zip after filling in the numbers
- [ ] Video uploaded, link is public, under 5:00
- [ ] Draft saved on the form *before* you need it
- [ ] `results/RESULTS.md` matches every number you claim in the description

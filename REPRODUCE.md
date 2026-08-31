# Reproduction guide

Written for someone starting from nothing.

## What you need

| | |
|---|---|
| Python | 3.10 or newer (developed on 3.12.3) |
| Disk | under 20 MB |
| Network | PyPI, and `api.anthropic.com` for the model runs only |
| Credentials | an `ANTHROPIC_API_KEY`, **only** for the runs marked "needs key" |

Three of the runs — the script baseline, the tool-layer ablation and the ceiling
probe — need no credentials at all. Start there; if they reproduce, the
environment is correct.

## Option 1 — Docker (recommended)

```bash
docker build -t settle .
docker run --rm settle make report
```

The build runs `make offline` as its final step, so a broken image fails at
build time rather than in front of you. To include the model runs:

```bash
docker run --rm -e ANTHROPIC_API_KEY=sk-ant-... settle make all
```

To keep the outputs:

```bash
docker run --rm -v "$PWD/out:/app/results" -e ANTHROPIC_API_KEY=sk-ant-... settle make all
```

## Option 2 — Windows

`make` is not available on Windows and PowerShell 5.1 has no `&&`. Use the
included `run.ps1`, which has the same target names:

```powershell
python -m pip install -r requirements.txt
.\run.ps1 offline
Copy-Item .env.example .env      # then paste your key into it
.\run.ps1 all
```

Details, including the execution-policy note, are in [`WINDOWS.md`](WINDOWS.md).

## Option 3 — local (macOS / Linux)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make offline
```

## The commands, one at a time

```bash
# 1. Generate the corpus. Deterministic: same seed, same bytes.
make data                 # or: python3 -m settle.gen --seed 42 --out data

# 2. Baseline B -- a competent script, no model.            [no key]
make baseline-b

# 3. Settle's tool layer with the model removed.            [no key]
make core

# 4. Ceiling probe: perfect identity judge, same pipeline.  [no key]
make ceiling

# 5. Baseline A -- one direct prompt.                       [needs key]
make baseline-a

# 6. Full Settle.                                           [needs key]
make agent

# 7. Ablations behind the changelog.                        [needs key]
make ablations

# 8. Rebuild the comparison table.
make report               # writes results/RESULTS.md
```

`make offline` is steps 1–4 and 8. `make all` is everything.

## Expected output

After `make offline`, `results/RESULTS.md` contains exactly:

| System | Value F1 | Precision | Recall | Invoices exact | Misposted KES | Esc./100 | Ledger OK |
|---|---|---|---|---|---|---|---|
| B. Script matcher (no LLM) | 0.6863 | 0.9724 | 0.5906 | 63.0% | 168,900 | 0.0 | 83.3% |
| Settle: tools only, no model | 0.3691 | 0.8333 | 0.2808 | 19.1% | 0 | 80.9 | 100.0% |
| Ceiling: perfect identity judge | 1.0 | 1.0 | 1.0 | 100.0% | 0 | 0.0 | 100.0% |

**These three rows are fully deterministic.** If your numbers differ, the corpus
differs — check that `make data` ran with `SEED=42`.

The model rows are not bit-reproducible (sampling), but the ranking and the
order of magnitude are stable across runs at temperature 0.

You will also get:

- `data/case01 … case12/` — invoices, statements and `truth.json` per case
- `data/memory_demo/month01…03/` — three months over the same customers
- `outputs/<run>/<case>/reconciled.csv` and `exceptions.csv` — what a bookkeeper opens
- `results/score_*.json` — per-case metrics
- `trajectories/*/*.jsonl` — every model call and tool step, and `make trajectories` renders them to markdown

## Runtime and cost

| Step | Time | Cost |
|---|---|---|
| `make data` | ~1 s | 0 |
| `make baseline-b` | ~2 s | 0 |
| `make core` | ~15 s | 0 |
| `make ceiling` | ~15 s | 0 |
| `make baseline-a` | ~2–4 min | 12 model calls, one per case |
| `make agent` | ~10–20 min | 1–2 calls per ambiguous invoice; the deterministic fast path skips the model entirely on unambiguous ones |
| `make ablations` | ~30–45 min | three further full passes |

To see the cost **before** committing to a run:

```bash
python -m settle.estimate
```

That builds every prompt the pipeline would send, without calling the API, and
prints projected tokens and cost per target. Budget roughly $0.14 for
`baseline-a` and $1.04 for `agent` with caching on.

Exact cost per case is measured, not estimated from a rule of thumb: every call
goes through `settle/llm.py`, which records token usage -- including cache reads
and writes, priced separately -- and prices it. The
`$/case` column in `RESULTS.md` is that number. Override the price assumptions
with `SETTLE_PRICE_IN` / `SETTLE_PRICE_OUT` if yours differ.

## Model selection

Set `SETTLE_MODEL` in `.env` to any model your key can reach:

```bash
SETTLE_MODEL=claude-sonnet-4-6 make agent
```

The adjudicator and verifier prompts are model-agnostic — they ask for a small
JSON object and nothing else.

## The three-month memory demonstration

This is the sequence shown in the video.

```bash
rm -f state/demo.db

# Month 1, cold. Alias-heavy customers; hard names get escalated.
python3 -m settle.agent --data data/memory_demo --cases month01 \
  --out results/pred_demo --outputs outputs/demo \
  --memory-db state/demo.db --trace trajectories/demo

# Look at what it refused to guess, and why.
python3 -m settle.approve --pred results/pred_demo/month01.json \
  --data data/memory_demo --invoice x --list

# Clear one, as a bookkeeper would. This writes the alias.
python3 -m settle.approve --pred results/pred_demo/month01.json \
  --data data/memory_demo --invoice <INVOICE_ID> --option 1 \
  --memory-db state/demo.db

# Month 3, warm. Same customers, same messy names, no code changed.
python3 -m settle.agent --data data/memory_demo --cases month03 \
  --out results/pred_demo --outputs outputs/demo \
  --memory-db state/demo.db --trace trajectories/demo
```

Compare the exception counts. The approval in month 1 is why month 3 needs fewer.

## Check credentials before a paid run

```bash
make doctor
```

One 8-token call that prints the model, workspace and organisation it resolved
to. Run it before `make agent`; without it, a misconfigured key is discovered
twelve cases into a paid pass.

## Troubleshooting

**`ANTHROPIC_API_KEY is not set`** — expected for the model runs. `make offline`
needs no key.

**`anthropic-workspace-id is required`** — your key spans multiple workspaces,
so each request must name the one it acts in. Either set
`ANTHROPIC_WORKSPACE_ID` in `.env` from Settings → Workspaces, or create a key
scoped to a single workspace, which needs no header at all.

**`Workspace ... not found`** — the ID is well-formed but does not resolve to a
workspace the key can act in: wrong organization, or your account is not a
member. Confirm membership in the Console, or use a single-workspace key.

Nothing is charged for either of these; they are rejected before inference.

**Numbers differ from the table** — regenerate the corpus: `make clean && make offline`.

**`ledger gate could not be satisfied`** — a genuine abort, by design. The gate
refuses to emit an unbalanced ledger rather than emitting one with a warning.
The exception text names the invoices; they are in `outputs/<run>/<case>/exceptions.csv`.

**A model run died partway** — re-run the same target. Paid runs support
`--resume`, which skips cases whose prediction file already exists, so an
interrupted run is never paid for twice. A single failing case is isolated and
reported at the end rather than aborting the whole pass.

**Docker build fails at `make offline`** — that is the build-time self-test
doing its job. The error above it is the real failure.

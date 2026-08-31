# Running on Windows

`make` is not a Windows command, and PowerShell 5.1 does not support `&&`.
Use `run.ps1`, which has the same target names as the Makefile.

## One-time setup

```powershell
cd $HOME\OneDrive\Desktop\settle-project

python --version          # need 3.10 or newer
python -m pip install -r requirements.txt

Copy-Item .env.example .env
code .env                 # paste your key, save
```

If `python` is not recognised, try `py --version`. If neither works, install
from python.org and tick **Add python.exe to PATH** during setup.

If PowerShell refuses to run the script ("running scripts is disabled"):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

That lasts for the current window only and changes nothing permanently.

## Targets

```powershell
.\run.ps1 offline                              # no API key needed
.\run.ps1 baseline-a agent ablations report    # the model runs
.\run.ps1 all
.\run.ps1                                      # help, plus what it detected
```

Several targets in one call run in order and stop on the first failure. That is
the PowerShell replacement for chaining with `&&`.

| Makefile | PowerShell |
|---|---|
| `make offline` | `.\run.ps1 offline` |
| `make agent` | `.\run.ps1 agent` |
| `make baseline-a agent report` | `.\run.ps1 baseline-a agent report` |
| `python3 -m settle.show ...` | `python -m settle.show ...` |

## Other differences

- `python3` on Linux and macOS is `python` on Windows. `run.ps1` detects this;
  for direct module calls, type `python`.
- Paths use `\` rather than `/`. Python accepts both, so either works in
  arguments.
- To set the key for one session without editing `.env`:
  `$env:ANTHROPIC_API_KEY = "sk-ant-..."`

## Interrupted runs

The paid targets resume by default. If a run dies partway, re-running the same
target skips every case whose prediction file already exists, so you never pay
twice for completed work:

```powershell
.\run.ps1 agent          # picks up where it stopped
```

To force a clean re-run of everything:

```powershell
$env:SETTLE_FRESH = '1'
.\run.ps1 agent
$env:SETTLE_FRESH = ''
```

A single failing case no longer aborts the whole target. Failures are listed at
the end; re-run the target to retry only those.

## Multi-workspace API keys

If a run fails with `anthropic-workspace-id is required`, your key is linked to
more than one workspace and every request must name the one it acts in.

**Simplest fix:** create an API key scoped to a *single* workspace at
<https://platform.claude.com/settings/keys>. Single-workspace keys always run in
the workspace they were created for, so no header is needed and
`ANTHROPIC_WORKSPACE_ID` stays commented out.

**Otherwise**, copy the ID from **Settings -> Workspaces**
(<https://platform.claude.com/settings/workspaces>). It looks like
`wrkspc_01JwQvzr7rXLA5AGx3HKfFUJ`. Add it to `.env`:

```
ANTHROPIC_WORKSPACE_ID=wrkspc_...
```

If you get `Workspace ... not found`, the ID is well-formed but does not resolve
to a workspace your key can act in — wrong organization, or your account is not
a member of it. Confirm membership in the Console, or fall back to the
single-workspace key above.

Then check it before spending anything:

```powershell
.\run.ps1 doctor
```

`doctor` makes one 8-token call and prints the model, workspace and organisation
it resolved to. Always run it before `agent` or `ablations`.

## Running on a free provider

Any OpenAI-compatible endpoint works. Groq's free tier needs no credit card and
is fast enough for the ~286 calls the agent run makes.

`.env`:

```
SETTLE_PROVIDER=openai
SETTLE_BASE_URL=https://api.groq.com/openai/v1
SETTLE_API_KEY=gsk_...
SETTLE_MODEL=<from .\run.ps1 models>
SETTLE_PRICE_IN=0
SETTLE_PRICE_OUT=0
SETTLE_MIN_INTERVAL=2.0
SETTLE_REASONING_EFFORT=low
SETTLE_TPM=8000
```

`SETTLE_TPM` is the tokens-per-minute cap for your tier. Requests are queued to
stay under it. This makes the agent run slow (an hour or more on a small free
tier) but it stops the 429 storms.

One thing no setting can fix: **baseline A cannot run on a small TPM tier.** Its
whole design is to put the entire statement in one prompt, which is 18,000 to
30,000 tokens -- larger than a free minute's entire budget. It fails immediately
with a clear message rather than retrying. On a free tier you can only run
baseline A on the smaller cases:

```powershell
python -m settle.baselines --which a --data data --out results\pred_baseline_a `
  --cases case01 case04 case09 --model $env:SETTLE_MODEL
```

Any row scored on fewer cases than the rest is flagged as incomplete in
`results\RESULTS.md`, so the comparison stays honest.

`SETTLE_REASONING_EFFORT=low` matters for gpt-oss-style reasoning models: they
think before answering, and with a tight budget the visible reply comes back
empty. These calls need no deep reasoning anyway -- the solver has already done
the arithmetic, so the model only has to pick a payer.

Then:

```powershell
.\run.ps1 models     # lists what your key can actually use
.\run.ps1 doctor     # one call, confirms it works
```

`SETTLE_MIN_INTERVAL` spaces requests so a per-minute cap is not tripped. At
2.0s, the agent run takes roughly 10 minutes. Lower it if your tier allows more;
429s are retried with backoff either way.

Two conditions keep the evaluation honest when swapping providers:

- Run **baseline A and Settle on the same model**, or the comparison is not fair.
- **Name the model in the README.** Judges need to know what produced the
  numbers.

The corpus is fully synthetic, so no free tier's data-use terms are a problem
here -- there is nothing confidential to submit.

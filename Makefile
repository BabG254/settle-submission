PY      ?= python3
SEED    ?= 42
DATA    ?= data
RES     ?= results
MODEL   ?= $(or $(SETTLE_MODEL),claude-sonnet-4-6)
# Paid targets resume by default; RESUME= forces a full re-run.
RESUME  ?= --resume

.PHONY: help doctor models estimate data offline all baseline-a baseline-b core ceiling agent \
        ablations eval report demo-memory trajectories clean

help:
	@echo "Settle -- mobile-money reconciliation agent"
	@echo ""
	@echo "  make offline      data + the two runs that need no API key + report"
	@echo "  make all          everything, including the model runs (needs a key)"
	@echo ""
	@echo "  make estimate     project the cost before running anything"
	@echo "  make doctor       check key, workspace and model before paying"
	@echo "  make data         regenerate the corpus from SEED=$(SEED)"
	@echo "  make baseline-b   deterministic script matcher      (no key)"
	@echo "  make core         Settle tool layer, no model       (no key)"
	@echo "  make ceiling      perfect-identity headroom run     (no key)"
	@echo "  make baseline-a   one direct prompt                 (needs key)"
	@echo "  make agent        full Settle                       (needs key)"
	@echo "  make ablations    the changelog runs                (needs key)"
	@echo "  make demo-memory  three-month alias memory demo     (needs key)"
	@echo "  make report       rebuild results/RESULTS.md"

estimate:
	$(PY) -m settle.estimate

doctor:
	$(PY) -m settle.doctor

models:
	$(PY) -m settle.doctor --list-models

# ---------------------------------------------------------------- corpus
data:
	$(PY) -m settle.gen --seed $(SEED) --out $(DATA)

# ------------------------------------------------------- runs without a key
baseline-b:
	$(PY) -m settle.baselines --which b --data $(DATA) --out $(RES)/pred_baseline_b
	$(PY) -m settle.score --pred-dir $(RES)/pred_baseline_b --data $(DATA) \
		--out $(RES)/score_baseline_b.json

core:
	$(PY) -m settle.agent --data $(DATA) --out $(RES)/pred_settle_core \
		--outputs outputs/core --no-adjudicator --no-memory --trace trajectories/core
	$(PY) -m settle.score --pred-dir $(RES)/pred_settle_core --data $(DATA) \
		--out $(RES)/score_settle_core.json

ceiling:
	$(PY) -m settle.agent --data $(DATA) --out $(RES)/pred_settle_ceiling \
		--outputs outputs/ceiling --identity-oracle --no-memory
	$(PY) -m settle.score --pred-dir $(RES)/pred_settle_ceiling --data $(DATA) \
		--out $(RES)/score_settle_ceiling.json

# ---------------------------------------------------------- runs with a key
baseline-a:
	$(PY) -m settle.baselines --which a --data $(DATA) --out $(RES)/pred_baseline_a \
		--model $(MODEL) $(RESUME)
	$(PY) -m settle.score --pred-dir $(RES)/pred_baseline_a --data $(DATA) \
		--out $(RES)/score_baseline_a.json

agent:
	$(PY) -m settle.agent --data $(DATA) --out $(RES)/pred_settle_full \
		--outputs outputs/full --model $(MODEL) --reset-memory $(RESUME) \
		--trace trajectories/full
	$(PY) -m settle.score --pred-dir $(RES)/pred_settle_full --data $(DATA) \
		--out $(RES)/score_settle_full.json

ablations:
	$(PY) -m settle.agent --data $(DATA) --out $(RES)/pred_settle_fullctx \
		--outputs outputs/fullctx --model $(MODEL) --full-context --no-memory $(RESUME)
	$(PY) -m settle.score --pred-dir $(RES)/pred_settle_fullctx --data $(DATA) \
		--out $(RES)/score_settle_fullctx.json
	$(PY) -m settle.agent --data $(DATA) --out $(RES)/pred_settle_noverify \
		--outputs outputs/noverify --model $(MODEL) --no-verifier --no-memory $(RESUME)
	$(PY) -m settle.score --pred-dir $(RES)/pred_settle_noverify --data $(DATA) \
		--out $(RES)/score_settle_noverify.json
	$(PY) -m settle.agent --data $(DATA) --out $(RES)/pred_settle_nomem \
		--outputs outputs/nomem --model $(MODEL) --no-memory $(RESUME)
	$(PY) -m settle.score --pred-dir $(RES)/pred_settle_nomem --data $(DATA) \
		--out $(RES)/score_settle_nomem.json

# ---- three-month memory demonstration (this is the sequence shown on video)
demo-memory:
	rm -f state/demo.db
	$(PY) -m settle.agent --data $(DATA)/memory_demo --cases month01 \
		--out $(RES)/pred_demo --outputs outputs/demo --model $(MODEL) \
		--memory-db state/demo.db --trace trajectories/demo
	@echo "--- month 01 exception queue (cold memory) ---"
	$(PY) -m settle.show queue --pred $(RES)/pred_demo/month01.json \
		--data $(DATA)/memory_demo

trajectories:
	$(PY) -m settle.trajectory --in trajectories/full --out trajectories/rendered || true
	$(PY) -m settle.trajectory --in trajectories/core --out trajectories/rendered || true
	$(PY) -m settle.trajectory --in trajectories/demo --out trajectories/rendered || true

report:
	$(PY) -m settle.report --results $(RES) --out $(RES)/RESULTS.md

eval: report

offline: data baseline-b core ceiling report

all: data baseline-b core ceiling doctor baseline-a agent ablations trajectories report

clean:
	rm -rf $(DATA) $(RES)/pred_* $(RES)/score_*.json outputs state trajectories/*.jsonl \
		trajectories/core trajectories/full trajectories/demo trajectories/rendered

"""Scoring.

The primary metric is value-weighted, not row-weighted. Getting a KES 175,000
invoice wrong is not the same size of mistake as getting a KES 1,200 one wrong,
and a row-weighted score hides exactly the errors a business cares about.

There is no LLM judge anywhere in this file. Ground truth is exact because the
corpus is generated, so scoring is set arithmetic.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schema import read_case, read_truth


def _pairs(matching: dict[str, list[str]]) -> set[tuple[str, str]]:
    return {(inv, r) for inv, rs in matching.items() for r in rs}


def score_prediction(pred: dict, case_dir: Path) -> dict:
    case = read_case(case_dir)
    truth = read_truth(case_dir)
    weight = {t.receipt: max(t.gross, 1) for t in case.txns}

    tp_pairs = _pairs(pred.get("matching", {})) & _pairs(truth)
    fp_pairs = _pairs(pred.get("matching", {})) - _pairs(truth)
    fn_pairs = _pairs(truth) - _pairs(pred.get("matching", {}))

    tp = sum(weight.get(r, 1) for _, r in tp_pairs)
    fp = sum(weight.get(r, 1) for _, r in fp_pairs)
    fn = sum(weight.get(r, 1) for _, r in fn_pairs)

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    # Invoice-level exactness: the invoice is fully and only correctly matched.
    exact = sum(1 for inv in truth
                if set(pred.get("matching", {}).get(inv, [])) == set(truth[inv]))

    # Escalation quality: an exception is *justified* if the system's own
    # unassisted best guess for that invoice would have been wrong.
    exceptions = pred.get("exceptions", [])
    justified = 0
    for e in exceptions:
        inv = e.get("invoice_id")
        guess = set(e.get("auto_guess") or [])
        if inv in truth and guess != set(truth[inv]):
            justified += 1
    esc_precision = justified / len(exceptions) if exceptions else None

    n_inv = len(case.invoices)
    return {
        "case_id": case.case_id,
        "system": pred.get("system"),
        "invoices": n_inv,
        "txns": len(case.txns),
        "value_precision": round(precision, 4),
        "value_recall": round(recall, 4),
        "value_f1": round(f1, 4),
        "invoice_exact_rate": round(exact / n_inv, 4) if n_inv else 0.0,
        "misposted_value": fp,
        "exceptions": len(exceptions),
        "escalation_precision": (round(esc_precision, 4)
                                 if esc_precision is not None else None),
        "human_touch_per_100": round(100 * len(exceptions) / n_inv, 1) if n_inv else 0.0,
        "ledger_ok": pred.get("ledger_ok"),
        "wall_s": pred.get("meta", {}).get("wall_s"),
        "cost_usd": pred.get("meta", {}).get("cost_usd"),
    }


def aggregate(rows: list[dict]) -> dict:
    def wsum(key: str) -> float:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    walls = [r["wall_s"] for r in rows if r.get("wall_s") is not None]
    escs = [r["escalation_precision"] for r in rows
            if r.get("escalation_precision") is not None]
    return {
        "system": rows[0]["system"] if rows else None,
        "cases": len(rows),
        "value_f1": round(wsum("value_f1"), 4),
        "value_precision": round(wsum("value_precision"), 4),
        "value_recall": round(wsum("value_recall"), 4),
        "invoice_exact_rate": round(wsum("invoice_exact_rate"), 4),
        "misposted_value": int(sum(r["misposted_value"] for r in rows)),
        "escalation_precision": round(sum(escs) / len(escs), 4) if escs else None,
        "human_touch_per_100": round(wsum("human_touch_per_100"), 1),
        "ledger_ok_rate": (None if all(r.get("ledger_ok") is None for r in rows)
                           else round(sum(1 for r in rows if r.get("ledger_ok"))
                                      / len(rows), 4)),
        "cost_usd_per_case": round(sum(costs) / len(costs), 4) if costs else 0.0,
        "wall_s_per_case": round(sum(walls) / len(walls), 1) if walls else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Score prediction files against truth.")
    ap.add_argument("--pred-dir", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows = []
    for pf in sorted(args.pred_dir.glob("*.json")):
        pred = json.loads(pf.read_text(encoding="utf-8"))
        case_dir = args.data / pred["case_id"]
        if not case_dir.exists():
            continue
        rows.append(score_prediction(pred, case_dir))

    if not rows:
        print(f"nothing to score: no prediction files in {args.pred_dir}\n"
              f"  The run that should have written them did not produce any output.\n"
              f"  Fix that first -- this is not a scoring problem.")
        return

    summary = {"per_case": rows, "aggregate": aggregate(rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    agg = summary["aggregate"]
    print(f"{agg.get('system')}: value-F1 {agg.get('value_f1')}  "
          f"exact {agg.get('invoice_exact_rate')}  "
          f"misposted KES {agg.get('misposted_value', 0):,}  "
          f"human-touch/100 {agg.get('human_touch_per_100')}")


if __name__ == "__main__":
    main()

"""Deterministic stress harness; no real customer records."""
from __future__ import annotations
import argparse
import json
import time
from .reconcile import unique_global_matches
from .schema import Invoice, Txn


def benchmark(count: int, max_nodes: int = 100_000) -> dict:
    if not 1 <= count <= 5000:
        raise ValueError("count must be 1..5000")
    invoices = [Invoice(f"I{i}", f"C{i}", f"Customer {i}", 100 + i,
                        "2026-01-01", "2026-01-15") for i in range(count)]
    txns = [Txn(f"R{i}", "2026-01-02T10:00:00", "pay_bill",
                f"Customer {i}", "", 100 + i, 0, 0, "") for i in range(count)]
    start = time.perf_counter()
    matches = unique_global_matches(invoices, txns, maximum_nodes=max_nodes)
    elapsed = time.perf_counter() - start
    return {"invoices": count, "matched": len(matches),
            "seconds": round(elapsed, 5), "node_budget": max_nodes,
            "fail_closed": len(matches) != count}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoices", type=int, default=100)
    parser.add_argument("--nodes", type=int, default=100_000)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.invoices, args.nodes), indent=2))


if __name__ == "__main__":
    main()

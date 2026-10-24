"""Small independent smoke checks for a clean checkout."""
from settle.reconcile import unique_global_matches
from settle.schema import Invoice, Txn


def test_package_import_and_exact_match():
    invoice = Invoice("I", "C", "Customer", 100, "2026-01-01", "2026-01-10")
    payment = Txn("R", "2026-01-02T09:00:00", "pay_bill",
                  "Customer", "", 100, 0, 0, "")
    assert unique_global_matches([invoice], [payment]) == {"I": ["R"]}

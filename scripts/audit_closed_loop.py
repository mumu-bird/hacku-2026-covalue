"""Reconcile completed browser scenarios against independent SQLite snapshots."""

import json
import sqlite3
from collections import Counter
from pathlib import Path

from backend.app.config import POLICY

RESULT_PATH = Path("artifacts/browser/closed-loop/result.json")
report = json.loads(RESULT_PATH.read_text())
assert report.get("passed"), "Browser loops have not all passed"
results = []
for scenario in report["scenarios"]:
    db = sqlite3.connect(scenario["database"])
    db.row_factory = sqlite3.Row
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    accounts = {r["user_id"]: r for r in db.execute("SELECT * FROM accounts")}
    payments = {r["id"]: r for r in db.execute("SELECT * FROM payment_intents")}
    ledger = list(db.execute("SELECT * FROM ledger"))
    agreements = list(db.execute("SELECT * FROM agreements"))
    opening = {u: POLICY["initial_balance"] for u in accounts}
    reserved = dict.fromkeys(accounts, 0)
    actions = Counter()
    keys = set()
    for row in ledger:
        assert row["business_key"] not in keys
        keys.add(row["business_key"])
        payment = payments[row["payment_id"]]
        payer, payee = payment["payer_id"], payment["payee_id"]
        amount = row["amount"]
        assert amount >= 0
        actions[(row["payment_id"], row["action"])] += amount
        if row["action"] == "RESERVE":
            assert row["source"] == "available:" + payer
            assert row["destination"] == "reserved:" + payment["id"]
            opening[payer] -= amount
            reserved[payer] += amount
        else:
            assert row["action"] in ("RELEASE", "REFUND")
            target = payee if row["action"] == "RELEASE" else payer
            assert row["source"] == "reserved:" + payment["id"]
            assert row["destination"] == "available:" + target
            reserved[payer] -= amount
            opening[target] += amount
    for user, account in accounts.items():
        assert account["available"] == opening[user], (
            scenario["name"],
            user,
            "available",
        )
        assert account["reserved"] == reserved[user], (
            scenario["name"],
            user,
            "reserved",
        )
        assert account["available"] >= 0 and account["reserved"] >= 0
    total = sum(a["available"] + a["reserved"] for a in accounts.values())
    assert total == len(accounts) * POLICY["initial_balance"]
    for payment in payments.values():
        for action, field in [
            ("RESERVE", "reserved"),
            ("RELEASE", "released"),
            ("REFUND", "refunded"),
        ]:
            assert payment[field] == actions[(payment["id"], action)]
        assert payment["reserved"] >= payment["released"] + payment["refunded"]
    for agreement in agreements:
        assert agreement["status"] in ("COMPLETED", "CANCELLED"), (
            scenario["name"],
            agreement["status"],
        )
        assert not db.execute(
            "SELECT * FROM bookings WHERE agreement_id=?", (agreement["id"],)
        ).fetchall()
        assert not db.execute(
            "SELECT * FROM obligations WHERE agreement_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
            (agreement["id"],),
        ).fetchall()
        assert not db.execute(
            "SELECT * FROM disputes WHERE agreement_id=? AND status='OPEN'",
            (agreement["id"],),
        ).fetchall()
        assert all(
            p["reserved"] == p["released"] + p["refunded"]
            for p in payments.values()
            if p["agreement_id"] == agreement["id"]
        )
        history = list(
            db.execute(
                "SELECT * FROM evidence WHERE agreement_id=?", (agreement["id"],)
            )
        )
        if agreement["status"] == "CANCELLED":
            assert not history, (
                "Cancelled partial orders must not masquerade as completed capability history"
            )
        else:
            providers = db.execute(
                "SELECT DISTINCT provider_id FROM obligations WHERE agreement_id=?",
                (agreement["id"],),
            ).fetchall()
            assert len(history) == len(providers)
            for evidence in history:
                entries = list(
                    db.execute(
                        "SELECT t.minutes,t.component FROM time_entries t JOIN obligations o ON o.id=t.obligation_id WHERE o.agreement_id=? AND o.provider_id=? AND t.status='CONFIRMED'",
                        (agreement["id"], evidence["owner_id"]),
                    )
                )
                assert json.loads(evidence["data"])["confirmed_minutes"] == sum(
                    t["minutes"] for t in entries if t["component"] == "EXECUTION"
                )
    assert not db.execute(
        "SELECT t.id FROM time_entries t JOIN obligations o ON o.id=t.obligation_id WHERE t.status='CONFIRMED' AND o.status!='ACCEPTED'"
    ).fetchall()
    results.append(
        {
            "name": scenario["name"],
            "passed": True,
            "orders": len(agreements),
            "ledger_entries": len(ledger),
            "total_funds": total,
            "remaining_reserved": sum(a["reserved"] for a in accounts.values()),
            "pending_obligations": 0,
            "bookings": 0,
        }
    )
    db.close()
output = {
    "passed": True,
    "scenarios": results,
    "checks": [
        "SQLite integrity",
        "foreign keys",
        "per-account ledger reconstruction",
        "payment conservation",
        "unique ledger commands",
        "terminal order state",
        "original obligations settled",
        "no open dispute",
        "bookings released",
        "whole-order capability history",
        "confirmed-time ownership",
    ],
}
Path("artifacts/browser/closed-loop/audit.json").write_text(
    json.dumps(output, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(output, ensure_ascii=False, indent=2))

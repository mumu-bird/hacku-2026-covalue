import json

from backend.app import domain as d
from backend.app.db import dump, unpack

from .conftest import cmd, draft, login, ok, proposal


def scope(s, category="spreadsheet"):
    return d.get(s, "listings", "request-main")["data"] | {"category": category}


def test_estimates_exist_before_personal_judgment_and_do_not_change_terms(client):
    login(client, "zao", "barter")
    p = proposal(client)
    result = ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))
    assert result["views"] == []
    assert len(result["estimates"]) == 2
    assert {x["valuation"]["suggested_amount"] for x in result["estimates"]} == {15000}
    assert all(x["source"] == "CURRENT_EVIDENCE" for x in result["estimates"])
    assert ok(client.get(f"/api/v1/proposals/{p['id']}")) == p
    assert "body" not in json.dumps(result)


def test_fixed_duration_and_agreed_overhead_are_exact_fees_are_counted_once(app):
    with app.state.registry.get("cash").tx() as s:
        task = scope(s, "tutoring") | {
            "duration": 60,
            "preparation": 20,
            "include_preparation": True,
            "travel": 10,
            "include_travel": False,
            "material_amount": 700,
            "transport_amount": 300,
        }
        estimate = d.evaluate(s, "lin", task)["value_estimate"]
        assert estimate["recognized_minutes"] == 80
        assert estimate["minutes_range"] == [80, 80]
        assert estimate["time_amount"] == 20000
        assert estimate["suggested_amount"] == 21000
        assert estimate["amount_range"] == [17000, 25000]
        assert estimate["travel_minutes"] == 0
        assert (
            d.evaluate(s, "lin", task | {"include_preparation": False})[
                "value_estimate"
            ]["suggested_amount"]
            == 16000
        )


def test_history_variability_widens_range_without_double_pricing_efficiency(app):
    with app.state.registry.get("cash").tx() as s:
        task = scope(s)
        stable = d.evaluate(s, "lin", task)["value_estimate"]
        for n, minutes in enumerate([30, 60, 90]):
            row = d.get(s, "evidence", f"ev-lin-spreadsheet-{n}")
            row["data"]["confirmed_minutes"] = minutes
            s.execute(
                "UPDATE evidence SET data=? WHERE id=?", (dump(row["data"]), row["id"])
            )
        varied = d.evaluate(s, "lin", task)["value_estimate"]
        assert stable["execution_range"] == [24, 36]
        assert varied["execution_range"] == [30, 90]
        assert varied["duration_mad_minutes"] == 30
        assert varied["duration_sample_count"] == 3
        assert varied["hourly_rate"] == stable["hourly_rate"]
        assert varied["suggested_amount"] == 2 * stable["suggested_amount"]
        assert (
            varied["amount_range"][1] - varied["amount_range"][0]
            > stable["amount_range"][1] - stable["amount_range"][0]
        )


def test_unmatched_workload_uses_template_and_excludes_artwork_times(app):
    with app.state.registry.get("cash").tx() as s:
        task = scope(s) | {"workload": "large"}
        s.insert(
            "evidence",
            id="reviewed-time",
            owner_id="lin",
            category="spreadsheet",
            kind="WORK",
            quality=96,
            status="APPROVED",
            created=d.now(),
            data=dump(
                {
                    "difficulty": "basic",
                    "workload": "large",
                    "confirmed_minutes": 1,
                    "skills": ["資料清理", "公式"],
                }
            ),
        )
        v = d.evaluate(s, "lin", task)["value_estimate"]
        assert v["duration_sample_count"] == 0 and v["duration_mad_minutes"] is None
        assert v["execution_minutes"] == 120
        assert v["execution_range"] == [72, 168]
        assert "模板" in v["duration_source"]


def test_unknown_and_ineligible_ability_have_no_actionable_estimate(app):
    with app.state.registry.get("cash").tx() as s:
        unknown = d.evaluate(
            s, "peer4", scope(s) | {"required_skills": [], "preferred_skills": []}
        )["value_estimate"]
        assert unknown["status"] == "TEMPLATE_ONLY" and unknown["quality"] is None
        assert unknown["suggested_amount"] is None and unknown["amount_range"] is None
        assert unknown["quality_coefficient"] == 1
        s.execute("UPDATE evidence SET quality=40 WHERE owner_id='lin'")
        low = d.evaluate(s, "lin", scope(s))["value_estimate"]
        assert low["status"] == "NOT_ELIGIBLE" and low["suggested_amount"] is None


def test_changed_reverse_quantity_recalculates_proactive_estimate(client):
    login(client, "zao", "barter")
    p = proposal(client)
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "reverse_minutes": 60},
        )
    )
    estimates = ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))["estimates"]
    reverse = next(x for x in estimates if x["user_id"] == "lin")
    assert reverse["platform_minutes"] == 60
    assert reverse["valuation"]["suggested_amount"] == 10000


def test_existing_agreement_uses_snapshot_after_capability_changes(client, app):
    login(client, "zao", "barter")
    p = proposal(client)
    a = draft(client, p)
    before = ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))["estimates"]
    with app.state.registry.get("barter").tx() as s:
        s.execute("UPDATE evidence SET quality=75 WHERE owner_id='lin'")
    after = ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))["estimates"]
    assert before == after
    assert all(
        x["source"] == "AGREEMENT_SNAPSHOT" and x["agreement_id"] == a["id"]
        for x in after
    )
    assert ok(client.get(f"/api/v1/agreements/{a['id']}"))["data"] == a["data"]


def test_legacy_agreement_does_not_invent_new_bounds_or_reprice(client, app):
    login(client, "zao", "barter")
    p = proposal(client)
    a = draft(client, p)
    with app.state.registry.get("barter").tx() as s:
        old = unpack(s.one("SELECT * FROM agreements WHERE id=?", (a["id"],)))["data"]
        for side in ["main_estimate", "reverse_estimate"]:
            old[side].pop("value_estimate")
        s.execute("UPDATE agreements SET data=? WHERE id=?", (dump(old), a["id"]))
        s.execute("UPDATE evidence SET quality=75 WHERE owner_id='lin'")
    estimates = ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))["estimates"]
    assert all(
        x["valuation"]["algorithm_version"] == "legacy-snapshot" for x in estimates
    )
    assert all(
        x["valuation"]["suggested_amount"] == 15000
        and x["valuation"]["amount_range"] is None
        for x in estimates
    )

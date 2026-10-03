import json

from backend.app.db import dump
from backend.app.mechanism import VALUE_DEFAULTS, simulate_value
from backend.app.value_model import nash_candidates, recipient_benefit

from .conftest import cmd, draft, login, ok, proposal


def context(p, **changes):
    return {
        "expected_version": p["version"],
        "scope_version": p["scope_version"],
        "target_minutes": 60,
        "swing_fit": 40,
        "swing_quality": 40,
        "swing_quantity": 20,
    } | changes


def test_more_time_increases_reference_but_not_benefit_after_target():
    a = simulate_value(VALUE_DEFAULTS | {"received_minutes": 60})
    b = simulate_value(VALUE_DEFAULTS | {"received_minutes": 90})
    c = simulate_value(VALUE_DEFAULTS | {"received_minutes": 120})
    assert (
        a["reference"]["reference_amount"]
        < b["reference"]["reference_amount"]
        < c["reference"]["reference_amount"]
    )
    assert (
        a["benefit"]["score"] == b["benefit"]["score"] == c["benefit"]["score"] == 89.6
    )
    assert b["benefit"]["extra_minutes_after_target"] == 30
    assert not b["benefit"]["actual_outcome_measured"]


def test_same_service_has_different_help_when_goal_differs():
    short = simulate_value(VALUE_DEFAULTS | {"target_minutes": 30})
    long = simulate_value(VALUE_DEFAULTS | {"target_minutes": 120})
    assert short["reference"] == long["reference"]
    assert short["benefit"]["score"] > long["benefit"]["score"]
    assert long["benefit"]["components"]["quantity"] == 75


def test_weights_are_normalized_sensitivity_is_bounded_and_unknown_is_not_zero():
    a = {
        "execution_minutes": 60,
        "fit": 80,
        "quality": 90,
        "eligible": True,
        "evidence_score": 20,
    }
    b = recipient_benefit(
        a, "english", 120, {"fit": 30, "quality": 70, "quantity": 0}, True
    )
    assert sum(b["weights"].values()) == 1
    assert b["score"] == 87
    assert (
        0 <= b["sensitivity_range"][0] <= b["score"] <= b["sensitivity_range"][1] <= 100
    )
    assert recipient_benefit(a | {"quality": None}, "english", 120)["score"] is None
    assert recipient_benefit(a | {"eligible": False}, "english", 120)["score"] is None


def test_context_is_private_and_does_not_change_quote_or_acceptance(client, app):
    login(client, "zao", "barter")
    p = proposal(client)
    peer_before = ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))
    login(client, "lin", "barter")
    own = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/value-context",
            context(
                p, target_minutes=129, swing_fit=17, swing_quality=83, swing_quantity=0
            ),
            method="PUT",
        )
    )
    assert own["own_context"]["target_minutes"] == 129
    benefit = next(x["benefit"] for x in own["estimates"] if x["user_id"] == "lin")
    assert benefit["preference_source"] == "USER_CONFIRMED_SWINGS"
    assert ok(client.get(f"/api/v1/proposals/{p['id']}")) == p
    with app.state.registry.get("barter").read() as s:
        event = s.one("SELECT data FROM events WHERE action='VALUE_CONTEXT_CONFIRMED'")
        assert json.loads(event["data"]) == {}
        assert s.all("SELECT * FROM preferences") == []
    login(client, "zao", "barter")
    assert ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives")) == peer_before


def test_goal_plan_changes_quantity_and_cash_direction_atomically_and_idempotently(
    client,
):
    login(client, "lin", "barter")
    p = proposal(client)
    body = context(p)
    q = ok(cmd(client, f"/proposals/{p['id']}/apply-value-plan", body, key="same-goal"))
    assert q["mode"] == "HYBRID" and q["data"]["reverse_minutes"] == 60
    assert q["data"]["amount"] == 5000
    assert q["data"]["payer_id"] == "zao" and q["data"]["payee_id"] == "lin"
    assert q == ok(
        cmd(client, f"/proposals/{p['id']}/apply-value-plan", body, key="same-goal")
    )
    values = ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))
    assert values["own_context"]["target_minutes"] == 60 and values["goal_plan"] is None
    assert client.get("/api/v1/me/orders").json() == []
    assert ok(client.get("/api/v1/me/mock-account"))["reserved"] == 0


def test_goal_change_expires_with_scope_and_outsider_and_zero_weights_rejected(client):
    login(client, "lin", "barter")
    p = proposal(client)
    path = f"/proposals/{p['id']}/value-context"
    assert (
        cmd(
            client,
            path,
            context(p, swing_fit=0, swing_quality=0, swing_quantity=0),
            method="PUT",
        ).status_code
        == 422
    )
    ok(cmd(client, path, context(p), method="PUT"))
    changed = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "reverse_minutes": 60},
        )
    )
    assert (
        ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))["own_context"]
        is None
    )
    assert (
        cmd(
            client,
            path,
            context(p) | {"expected_version": changed["version"]},
            method="PUT",
        ).status_code
        == 409
    )
    login(client, "mei", "barter")
    assert cmd(client, path, context(changed), method="PUT").status_code == 403
    assert (
        cmd(
            client, f"/proposals/{p['id']}/apply-value-plan", context(changed)
        ).status_code
        == 403
    )


def test_goal_plan_cannot_change_existing_agreement_or_disallowed_mode(client, app):
    login(client, "zao", "barter")
    p = proposal(client)
    a = draft(client, p)
    login(client, "lin", "barter")
    assert (
        cmd(client, f"/proposals/{p['id']}/apply-value-plan", context(p)).status_code
        == 422
    )
    assert ok(client.get(f"/api/v1/agreements/{a['id']}"))["data"] == a["data"]
    with app.state.registry.get("barter").tx() as s:
        s.execute("UPDATE agreements SET status='CANCELLED' WHERE id=?", (a["id"],))
        data = p["data"]
        data["scope"]["accepted_modes"] = ["BARTER"]
        s.execute("UPDATE proposals SET data=? WHERE id=?", (dump(data), p["id"]))
    assert (
        ok(client.get(f"/api/v1/proposals/{p['id']}/perspectives"))["goal_plan"] is None
    )


def test_nash_discrete_candidates_maximize_product_and_handle_point_agreement():
    candidates = [60, 75, 90, 105, 120]
    assert nash_candidates(candidates, 60, 120) == [90]
    assert nash_candidates(candidates[:-1], 60, 105) == [75, 90]
    assert nash_candidates([60], 60, 60) == [60]
    shifted = nash_candidates([x + 100 for x in candidates], 160, 220)
    assert shifted == [190]


def test_pareto_frontier_respects_cost_quality_and_time_filters(client):
    m = ok(client.get("/api/v1/listings/request-main/matches"))
    assert m["benefit_frontier_ids"] == ["lin"]
    assert all(
        c["benefit"]["score"] is not None
        for c in m["candidates"]
        if c["quality"] is not None
    )


def test_missing_evidence_cannot_be_replaced_by_goal_scores_or_create_plan(client, app):
    login(client, "lin", "barter")
    p = proposal(client)
    with app.state.registry.get("barter").tx() as s:
        s.execute("DELETE FROM evidence WHERE owner_id='zao' AND category='english'")
    r = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/value-context",
            context(p, swing_quality=100),
            method="PUT",
        )
    )
    assert r["goal_plan"] is None
    assert (
        next(x["benefit"] for x in r["estimates"] if x["user_id"] == "lin")["score"]
        is None
    )
    assert (
        cmd(client, f"/proposals/{p['id']}/apply-value-plan", context(p)).status_code
        == 422
    )
    assert ok(client.get(f"/api/v1/proposals/{p['id']}")) == p

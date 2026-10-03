from backend.app import domain as d
from backend.app.db import dump
from backend.app.mechanism import DEFAULTS, report, simulate

from .conftest import cmd, login, ok, proposal


def test_missing_verified_evidence_pauses_advice_without_calling_person_low_ability(
    client, app
):
    login(client, "zao", "barter")
    p = proposal(client)
    with app.state.registry.get("barter").tx() as s:
        s.execute("DELETE FROM evidence WHERE owner_id='lin' AND category='tutoring'")
        data = p["data"]
        data["scope"].update(required_skills=[], preferred_skills=[])
        s.execute("UPDATE proposals SET data=? WHERE id=?", (dump(data), p["id"]))
        assessment = d.evaluate(s, "lin", data["scope"])
        assert assessment["eligible"] and assessment["quality"] is None
    rejected = cmd(
        client, f"/proposals/{p['id']}/recommend", {"expected_version": p["version"]}
    )
    assert (
        rejected.status_code == 422
        and rejected.json()["code"] == "INSUFFICIENT_EVIDENCE"
    )
    assert client.get("/api/v1/me/orders").json() == []


def test_perspectives_require_consent_hide_private_view_and_expire_with_scope(client):
    login(client, "lin", "barter")
    p = proposal(client)
    body = {
        "expected_version": p["version"],
        "scope_version": p["scope_version"],
        "received_value": 8000,
        "reason": "額外英語交流對本次練習的幫助有限",
        "shared": False,
    }
    ok(cmd(client, f"/proposals/{p['id']}/perspectives", body, method="PUT"))
    login(client, "zao", "barter")
    assert client.get(f"/api/v1/proposals/{p['id']}/perspectives").json()["views"] == []
    login(client, "lin", "barter")
    own = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/perspectives",
            body | {"shared": True},
            method="PUT",
        )
    )
    assert own["views"][0]["platform_value"] == 15000
    login(client, "zao", "barter")
    visible = client.get(f"/api/v1/proposals/{p['id']}/perspectives").json()["views"]
    assert len(visible) == 1 and visible[0]["received_value"] == 8000
    unchanged = client.get(f"/api/v1/proposals/{p['id']}").json()
    assert unchanged["data"] == p["data"] and unchanged["version"] == p["version"]
    revised = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "reverse_minutes": 60},
        )
    )
    assert client.get(f"/api/v1/proposals/{p['id']}/perspectives").json()["views"] == []
    login(client, "lin", "barter")
    stale = cmd(
        client,
        f"/proposals/{p['id']}/perspectives",
        body | {"expected_version": revised["version"]},
        method="PUT",
    )
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"


def test_outsider_cannot_read_or_write_perspective_or_reveal_private_bounds(client):
    login(client, "zao", "barter")
    p = proposal(client)
    login(client, "mei", "barter")
    assert client.get(f"/api/v1/proposals/{p['id']}/perspectives").status_code == 403
    assert (
        cmd(
            client,
            f"/proposals/{p['id']}/perspectives",
            {
                "expected_version": p["version"],
                "scope_version": p["scope_version"],
                "received_value": 8000,
                "reason": "不得冒充本單參與者的价值判断",
                "shared": True,
            },
            method="PUT",
        ).status_code
        == 403
    )


def test_same_reference_can_have_acceptance_or_refusal_and_constraints_are_real():
    accepted = simulate(DEFAULTS | {"lower": 60, "upper": 60})
    refused = simulate(DEFAULTS | {"lower": 90, "upper": 60})
    assert (
        accepted["recommendation"]["reverse_minutes"]
        == refused["recommendation"]["reverse_minutes"]
        == 90
    )
    assert accepted["negotiation"]["candidates"] == [60]
    assert refused["status"] == "NO_DEAL"
    assert (
        simulate(DEFAULTS | {"preparation": 31})["failure"]["code"]
        == "NO_FEASIBLE_PLAN"
    )
    assert (
        simulate(DEFAULTS | {"evidence_mode": "MISSING"})["failure"]["code"]
        == "INSUFFICIENT_EVIDENCE"
    )


def test_recommending_new_quantity_requires_new_personal_value_judgment(client):
    login(client, "zao", "barter")
    p = proposal(client)
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "reverse_minutes": 60},
        )
    )
    ok(
        cmd(
            client,
            f"/proposals/{p['id']}/perspectives",
            {
                "expected_version": p["version"],
                "scope_version": p["scope_version"],
                "received_value": 20000,
                "reason": "我對本單六十分鐘輔導的价值判断",
                "shared": True,
            },
            method="PUT",
        )
    )
    recommended = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": p["version"]},
        )
    )
    assert recommended["data"]["reverse_minutes"] == 90
    assert client.get(f"/api/v1/proposals/{p['id']}/perspectives").json()["views"] == []


def test_report_exposes_coefficient_boundary_and_operation_cost_not_user_outcome():
    r = report()
    cases = {x["label"]: x for x in r["experiments"]}
    assert (
        cases["quality=80"]["main"]["hourly_rate"]
        == 1.25 * cases["quality=79"]["main"]["hourly_rate"]
    )
    strict, permissive = r["tradeoffs"]
    assert strict["first_unreturned_minutes"] < permissive["first_unreturned_minutes"]
    assert strict["workflow_commands"] > permissive["workflow_commands"]
    assert r["is_demo"] and len(r["experiments"]) == 18

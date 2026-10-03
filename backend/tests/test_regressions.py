from backend.app import domain as d
from backend.app.config import POLICY
from backend.app.db import dump

from .conftest import accept_ob, activate, cmd, draft, login, ok, order, proposal


def test_public_rule_weights_are_executable(monkeypatch, app):
    monkeypatch.setitem(POLICY, "quality_weights", [20, 30, 50])
    assert d.quality({"correctness": 100, "completeness": 50, "independence": 0}) == 35
    monkeypatch.setitem(POLICY, "ranking_weights", [0, 100, 0])
    with app.state.registry.get("cash").read() as s:
        result = d.evaluate(
            s,
            "lin",
            d.get(s, "listings", "request-main")["data"] | {"category": "spreadsheet"},
        )
    assert result["recommendation_score"] == result["quality"] == 96


def test_provider_history_does_not_upgrade_requester_role(client):
    provider = ok(client.get("/api/v1/users/lin/credit?role=PROVIDER"))
    requester = ok(client.get("/api/v1/users/lin/credit?role=REQUESTER"))
    assert provider["policy"]["limit"] == 2 and provider["completed_orders"] == 3
    assert requester["policy"]["limit"] == 1 and requester["completed_orders"] == 0
    assert requester["independent_peers"] == 0


def test_two_independent_samples_use_template_not_false_precision(client, app):
    with app.state.registry.get("cash").tx() as s:
        s.execute("DELETE FROM evidence WHERE id='ev-lin-spreadsheet-2'")
    match = ok(client.get("/api/v1/listings/request-main/matches"))
    candidate = next(r for r in match["candidates"] if r["user_id"] == "lin")
    assert candidate["estimated_minutes"] == 60
    assert candidate["total_amount"] == 30000
    assert "模板" in candidate["estimate_source"]


def test_zero_price_still_finishes_payment_state_and_conserves_funds(client, app):
    p = proposal(client)
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "amount": 0},
        )
    )
    a = activate(client, draft(client, p))
    for index in range(2):
        login(client, "zao")
        view = order(client, a["id"])
        stage = view["stages"][index]
        ok(
            cmd(
                client,
                f"/stages/{stage['id']}/fund",
                {"expected_version": view["version"]},
            )
        )
        ob = order(client, a["id"])["stages"][index]["obligations"][0]
        a = accept_ob(client, a, ob)
    assert a["status"] == "COMPLETED"
    with app.state.registry.get("cash").read() as s:
        payments = s.all(
            "SELECT * FROM payment_intents WHERE agreement_id=?", (a["id"],)
        )
        assert all(p["state"] == "RELEASED" and p["released"] == 0 for p in payments)
        assert (
            s.one("SELECT SUM(available+reserved) total FROM accounts")["total"]
            == 1100000
        )


def test_signed_terms_survive_later_capability_change(client, app):
    a = activate(client, draft(client))
    before = order(client, a["id"])["data"]
    with app.state.registry.get("cash").tx() as s:
        s.execute(
            "UPDATE evidence SET quality=20 WHERE owner_id='lin' AND category='spreadsheet'"
        )
        l = d.get(s, "listings", "request-main")
        s.execute(
            "UPDATE listings SET data=?,version=version+1 WHERE id=?",
            (dump(l["data"] | {"duration": 120}), l["id"]),
        )
    assert order(client, a["id"])["data"] == before
    login(client, "zao")
    view = order(client, a["id"])
    ok(
        cmd(
            client,
            f"/stages/{view['stages'][0]['id']}/fund",
            {"expected_version": view["version"]},
        )
    )
    a = accept_ob(client, a, order(client, a["id"])["stages"][0]["obligations"][0])
    assert a["status"] == "ACTIVE"


def test_preparation_recommendation_includes_executable_rounds(client, app):
    login(client, "zao", "barter")
    p = proposal(client)
    with app.state.registry.get("barter").tx() as s:
        data = p["data"]
        data["scope"]["preparation"] = 20
        data["scope"]["include_preparation"] = True
        s.execute("UPDATE proposals SET data=? WHERE id=?", (dump(data), p["id"]))
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": p["version"]},
        )
    )
    rec = p["data"]["recommendation"]
    assert rec["reverse_minutes"] == 120 and rec["rounds"] == 6
    assert rec["reverse"]["estimated_minutes"] == 120
    assert rec["reverse"]["total_amount"] == rec["main"]["total_amount"] == 20000
    a = draft(client, p, rounds=rec["rounds"])
    assert a["data"]["rounds"] == 6
    activate(client, a, "barter")


def test_reverse_window_must_be_feasible_before_suggesting_trade(client, app):
    login(client, "zao", "barter")
    p = proposal(client)
    with app.state.registry.get("barter").tx() as s:
        data = p["data"]
        data["reverse"]["service_mode"] = "OFFLINE"
        s.execute("UPDATE proposals SET data=? WHERE id=?", (dump(data), p["id"]))
    result = cmd(
        client, f"/proposals/{p['id']}/recommend", {"expected_version": p["version"]}
    )
    assert result.status_code == 422 and result.json()["code"] == "NO_FEASIBLE_PLAN"


def test_cash_costs_are_separate_from_time_and_not_hidden_in_barter(app):
    with app.state.registry.get("cash").read() as s:
        scope = d.get(s, "listings", "request-main")["data"] | {
            "category": "spreadsheet",
            "material_amount": 5000,
            "transport_amount": 2000,
        }
        result = d.evaluate(s, "lin", scope)
        assert result["estimated_minutes"] == 30 and result["time_amount"] == 15000
        assert result["total_amount"] == 22000
    with app.state.registry.get("barter").read() as s:
        p = d.get(s, "proposals", s.one("SELECT id FROM proposals LIMIT 1")["id"])
        p["data"]["scope"]["material_amount"] = 5000
        import pytest

        with pytest.raises(d.DomainError) as error:
            d.recommendation(s, p)
        assert error.value.code == "INVALID_INPUT"

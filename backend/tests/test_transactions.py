import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from .conftest import accept_ob, activate, cmd, draft, login, ok, order, proposal


def test_cash_no_skill_requirement_and_success(client, app):
    assert not any(
        l["kind"] == "OFFER" and l["category"] == "spreadsheet"
        for l in client.get("/api/v1/listings?owner_id=zao").json()
    )
    a = activate(client, draft(client, stage_amounts=[6000, 9000]))
    for index in (0, 1):
        login(client, "zao")
        view = order(client, a["id"])
        stage = view["stages"][index]
        a = ok(
            cmd(
                client,
                f"/stages/{stage['id']}/fund",
                {"expected_version": view["version"]},
            )
        )
        view = order(client, a["id"])
        ob = view["stages"][index]["obligations"][0]
        a = accept_ob(client, a, ob, execution=10 if index == 0 else 18)
    assert a["status"] == "COMPLETED"
    assert ok(client.get("/api/v1/me/mock-account"))["available"] == 85000
    login(client, "lin")
    assert ok(client.get("/api/v1/me/mock-account"))["available"] == 115000
    assert ok(client.get("/api/v1/me/time-summary"))["provided_minutes"] == 28
    with app.state.registry.get("cash").read() as s:
        assert (
            s.one("SELECT SUM(available+reserved) total FROM accounts")["total"]
            == 1100000
        )
        assert (
            len(s.all("SELECT * FROM evidence WHERE agreement_id=?", (a["id"],))) == 1
        )


def test_cash_insufficient_fake_fund_and_self_accept(client, app):
    a = activate(client, draft(client))
    login(client, "zao")
    view = order(client, a["id"])
    stage = view["stages"][0]
    with app.state.registry.get("cash").tx() as s:
        s.execute("UPDATE accounts SET available=0 WHERE user_id='zao'")
    r = cmd(
        client, f"/stages/{stage['id']}/fund", {"expected_version": view["version"]}
    )
    assert r.json()["code"] == "INSUFFICIENT_MOCK_BALANCE"
    assert order(client, a["id"])["stages"][0]["obligations"][0]["status"] == "LOCKED"
    assert (
        cmd(
            client,
            f"/stages/{stage['id']}/fund",
            {"expected_version": view["version"], "paid": True},
        ).status_code
        == 422
    )
    login(client, "lin")
    ob = view["stages"][0]["obligations"][0]
    assert (
        cmd(
            client,
            f"/obligations/{ob['id']}/accept",
            {
                "expected_version": ob["version"],
                "scores": {
                    "correctness": 100,
                    "completeness": 100,
                    "independence": 100,
                },
            },
        ).status_code
        == 403
    )


def test_idempotency_and_private_preferences(client, app):
    p = proposal(client)
    body = {
        "expected_version": p["version"],
        "scope_version": p["scope_version"],
        "value": 18000,
    }
    first = cmd(
        client, f"/proposals/{p['id']}/preference", body, method="PUT", key="same"
    )
    second = cmd(
        client, f"/proposals/{p['id']}/preference", body, method="PUT", key="same"
    )
    assert first.json() == second.json() and first.status_code == 200
    assert (
        cmd(
            client,
            f"/proposals/{p['id']}/preference",
            {**body, "value": 1},
            method="PUT",
            key="same",
        ).json()["code"]
        == "IDEMPOTENCY_CONFLICT"
    )
    login(client, "lin")
    assert client.get(f"/api/v1/proposals/{p['id']}/preference").json() is None
    assert "18000" not in json.dumps(client.get(f"/api/v1/proposals/{p['id']}").json())
    login(client, "mei")
    assert client.get(f"/api/v1/proposals/{p['id']}").status_code == 403
    assert client.get("/api/v1/review/queue").status_code == 403
    login(client, "reviewer")
    events = ok(client.get("/api/v1/demo/events"))
    assert "18000" not in json.dumps(events)


def test_assisted_cash_and_no_deal(client):
    p = proposal(client)
    assert (
        cmd(
            client,
            f"/proposals/{p['id']}/calculate",
            {"expected_version": p["version"]},
        ).json()["code"]
        == "WAITING_INPUT"
    )
    for actor, value in [("lin", 12000), ("zao", 18000)]:
        login(client, actor)
        ok(
            cmd(
                client,
                f"/proposals/{p['id']}/preference",
                {
                    "expected_version": p["version"],
                    "scope_version": p["scope_version"],
                    "value": value,
                },
                "PUT",
            )
        )
    assert ok(
        cmd(
            client,
            f"/proposals/{p['id']}/calculate",
            {"expected_version": p["version"]},
        )
    )["candidates"] == [15000]
    login(client, "zao", "no_deal")
    p = proposal(client)
    assert (
        cmd(
            client,
            f"/proposals/{p['id']}/calculate",
            {"expected_version": p["version"]},
        ).json()["code"]
        == "NO_FEASIBLE_PLAN"
    )
    assert not client.get("/api/v1/me/orders").json()


def test_barter_solver_ties_empty_and_version_invalidation(client):
    login(client, "zao", "barter")
    p = proposal(client)
    for low, high, expected in [(60, 120, [90]), (90, 105, [90, 105]), (91, 104, None)]:
        for actor, val in [("lin", low), ("zao", high)]:
            login(client, actor, "barter")
            ok(
                cmd(
                    client,
                    f"/proposals/{p['id']}/preference",
                    {
                        "expected_version": p["version"],
                        "scope_version": p["scope_version"],
                        "value": val,
                    },
                    "PUT",
                )
            )
        response = cmd(
            client,
            f"/proposals/{p['id']}/calculate",
            {"expected_version": p["version"]},
        )
        if expected is None:
            assert response.json()["code"] == "NO_FEASIBLE_PLAN"
        else:
            assert response.json()["candidates"] == expected
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "reverse_minutes": 105},
        )
    )
    assert client.get(f"/api/v1/proposals/{p['id']}/preference").json() is None
    assert (
        cmd(
            client,
            f"/proposals/{p['id']}/preference",
            {"expected_version": p["version"], "scope_version": 1, "value": 100},
            "PUT",
        ).json()["code"]
        == "VERSION_CONFLICT"
    )


def test_barter_full_success_and_round_lock(client):
    login(client, "zao", "barter")
    p = proposal(client)
    assert p["data"]["reverse_minutes"] == 90
    a = activate(client, draft(client), case="barter")
    view = order(client, a["id"])
    future = view["stages"][1]["obligations"][0]
    login(client, "lin", "barter")
    assert (
        cmd(
            client,
            f"/obligations/{future['id']}/submit",
            {
                "expected_version": future["version"],
                "evidence": "嘗試跳過原來輪次",
                "execution_minutes": 30,
            },
        ).json()["code"]
        == "INVALID_STATE"
    )
    for round in (0, 1):
        for index in (0, 1):
            ob = order(client, a["id"])["stages"][round]["obligations"][index]
            a = accept_ob(client, a, ob, case="barter")
    assert a["status"] == "COMPLETED"
    login(client, "lin", "barter")
    summary = ok(client.get("/api/v1/me/time-summary"))
    assert (
        summary["provided_minutes"] == 60 and summary["received_service_minutes"] == 90
    )


def test_hybrid_cash_direction_invalidation_and_release(client):
    login(client, "zao", "hybrid")
    p = proposal(client)
    assert p["data"]["amount"] == 5000
    for actor, value in [("lin", 3000), ("zao", 7000)]:
        login(client, actor, "hybrid")
        ok(
            cmd(
                client,
                f"/proposals/{p['id']}/preference",
                {
                    "expected_version": p["version"],
                    "scope_version": p["scope_version"],
                    "value": value,
                },
                "PUT",
            )
        )
    assert ok(
        cmd(
            client,
            f"/proposals/{p['id']}/calculate",
            {"expected_version": p["version"]},
        )
    )["candidates"] == [5000]
    changed = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "cash_payer_id": "lin"},
        )
    )
    assert changed["data"]["recommendation"] is None
    assert client.get(f"/api/v1/proposals/{p['id']}/preference").json() is None
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": changed["version"]},
        )
    )
    a = activate(client, draft(client, p), case="hybrid")
    for index in (0, 1):
        login(client, "zao", "hybrid")
        view = order(client, a["id"])
        stage = view["stages"][index]
        a = ok(
            cmd(
                client,
                f"/stages/{stage['id']}/fund",
                {"expected_version": view["version"]},
            )
        )
        view = order(client, a["id"])
        a = accept_ob(client, a, view["stages"][index]["obligations"][0], case="hybrid")
        login(client, "zao", "hybrid")
        view = order(client, a["id"])
        assert view["stages"][index]["payment"]["released"] == 0
        a = accept_ob(client, a, view["stages"][index]["obligations"][1], case="hybrid")
    assert a["status"] == "COMPLETED"
    login(client, "zao", "hybrid")
    assert ok(client.get("/api/v1/me/mock-account"))["available"] == 95000


def test_duplicate_funding_acceptance_release(client, app):
    a = activate(client, draft(client))
    login(client, "zao")
    view = order(client, a["id"])
    stage = view["stages"][0]
    body = {"expected_version": view["version"]}
    first = ok(cmd(client, f"/stages/{stage['id']}/fund", body, key="fund"))
    assert ok(cmd(client, f"/stages/{stage['id']}/fund", body, key="fund")) == first
    view = order(client, a["id"])
    ob = view["stages"][0]["obligations"][0]
    login(client, "lin")
    ob = ok(
        cmd(
            client,
            f"/obligations/{ob['id']}/submit",
            {
                "expected_version": ob["version"],
                "evidence": "第一階段完整交付資料",
                "execution_minutes": 15,
            },
        )
    )
    login(client, "zao")
    body = {
        "expected_version": ob["version"],
        "scores": {"correctness": 95, "completeness": 95, "independence": 95},
    }
    first = ok(cmd(client, f"/obligations/{ob['id']}/accept", body, key="accept"))
    assert (
        ok(cmd(client, f"/obligations/{ob['id']}/accept", body, key="accept")) == first
    )
    with app.state.registry.get("cash").read() as s:
        assert s.one("SELECT COUNT(*) n FROM ledger WHERE action='RESERVE'")["n"] == 1
        assert s.one("SELECT COUNT(*) n FROM ledger WHERE action='RELEASE'")["n"] == 1
        assert (
            s.one("SELECT SUM(minutes) n FROM time_entries WHERE status='CONFIRMED'")[
                "n"
            ]
            == 15
        )


def test_concurrent_single_request_assignment(client, app):
    p1 = proposal(client)
    p2 = ok(
        cmd(
            client,
            "/proposals",
            {"listing_id": "request-main", "provider_id": "wei", "mode": "MONEY"},
        )
    )
    p2 = ok(
        cmd(
            client,
            f"/proposals/{p2['id']}/recommend",
            {"expected_version": p2["version"]},
        )
    )
    a1 = draft(client, p1)
    a2 = draft(client, p2)
    for a in [a1, a2]:
        ok(
            cmd(
                client,
                f"/agreements/{a['id']}/confirm",
                {"expected_version": a["version"], "terms_version": 1},
            )
        )

    def sign(item):
        agreement, actor = item
        c = TestClient(app)
        login(c, actor)
        return cmd(
            c,
            f"/agreements/{agreement['id']}/confirm",
            {"expected_version": 2, "terms_version": 1},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(sign, [(a1, "lin"), (a2, "wei")]))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (
        next(r for r in results if r.status_code == 409).json()["code"]
        == "LISTING_TAKEN"
    )
    with app.state.registry.get("cash").read() as s:
        assert (
            s.one("SELECT COUNT(*) n FROM agreements WHERE status='ACTIVE'")["n"] == 1
        )
        assert s.one("SELECT COUNT(*) n FROM bookings")["n"] == 2


def test_stale_terms_confirm_cannot_activate(client):
    p = proposal(client)
    a = draft(client, p)
    a = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/confirm",
            {"expected_version": a["version"], "terms_version": 1},
        )
    )
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "amount": 16000},
        )
    )
    login(client, "lin")
    response = cmd(
        client,
        f"/agreements/{a['id']}/confirm",
        {"expected_version": a["version"], "terms_version": 1},
    )
    assert response.json()["code"] == "VERSION_CONFLICT"


def test_foreign_keys_and_demo_disabled(app, tmp_path):
    from backend.app.main import create_app

    with app.state.registry.get("cash").read() as s:
        assert s.one("PRAGMA foreign_keys")["foreign_keys"] == 1
    c = TestClient(create_app(tmp_path / "off", demo_mode=False))
    assert (
        c.post("/api/v1/auth/demo-login", json={"username": "zao"}).status_code == 403
    )
    assert c.get("/api/v1/demo/events").status_code == 403
    assert c.get("/api/v1/me").status_code == 401

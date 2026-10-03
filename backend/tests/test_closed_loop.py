from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from fastapi.testclient import TestClient

from backend.app import domain as d
from backend.app.db import dump

from .conftest import accept_ob, activate, cmd, draft, login, ok, order
from .test_settlements import sign_closeout


def funded_submission(client):
    a = activate(client, draft(client))
    login(client, "zao")
    view = order(client, a["id"])
    ok(
        cmd(
            client,
            f"/stages/{view['stages'][0]['id']}/fund",
            {"expected_version": view["version"]},
        )
    )
    login(client, "lin")
    ob = order(client, a["id"])["stages"][0]["obligations"][0]
    ob = ok(
        cmd(
            client,
            f"/obligations/{ob['id']}/submit",
            {
                "expected_version": ob["version"],
                "evidence": "完整交付的原始工作表及修改說明",
                "execution_minutes": 15,
            },
        )
    )
    login(client, "zao")
    return a, ob


def dispute(client, a, ob=None):
    return ok(
        cmd(
            client,
            f"/agreements/{a['id']}/disputes",
            {
                "expected_version": order(client, a["id"])["version"],
                "reason": "依原驗收標準核對交付與結清安排",
                "obligation_id": ob["id"] if ob else None,
            },
        )
    )


def review(client, case, outcome, **extra):
    return ok(
        cmd(
            client,
            f"/disputes/{case['id']}/review",
            {
                "expected_version": case["version"],
                "outcome": outcome,
                "basis": "依原協議與交付證據完成結構化復核",
                **extra,
            },
        )
    )


def test_withdrawal_during_dispute_is_not_undone_by_review(client):
    a, ob = funded_submission(client)
    case = dispute(client, a, ob)
    ok(
        cmd(
            client,
            f"/agreements/{a['id']}/withdraw",
            {
                "expected_version": order(client, a["id"])["version"],
                "reason": "爭議期間申請退出，保留原義務核對",
            },
        )
    )
    login(client, "reviewer")
    review(client, case, "REDO")
    view = order(client, a["id"])
    assert view["status"] == "CLOSING"
    assert view["stages"][1]["status"] == "LOCKED"
    login(client, "lin")
    ob = view["stages"][0]["obligations"][0]
    assert (
        cmd(
            client,
            f"/obligations/{ob['id']}/submit",
            {
                "expected_version": ob["version"],
                "evidence": "尚未雙方確認結清前不可重新履約",
                "execution_minutes": 15,
            },
        ).status_code
        == 409
    )


def test_other_open_dispute_keeps_order_frozen_then_resume_progresses(client, app):
    a, ob = funded_submission(client)
    first = dispute(client, a, ob)
    login(client, "reviewer")
    first = review(client, first, "UNRESOLVED")
    login(client, "zao")
    second = dispute(client, a)
    login(client, "reviewer")
    review(
        client,
        first,
        "ACCEPT",
        scores={"correctness": 95, "completeness": 95, "independence": 95},
    )
    frozen = order(client, a["id"])
    assert frozen["status"] == "DISPUTED"
    assert frozen["stages"][0]["obligations"][0]["status"] == "ACCEPTED"
    assert frozen["stages"][0]["payment"]["released"] == 0
    assert frozen["stages"][1]["status"] == "LOCKED"
    review(client, second, "RESUME")
    resumed = order(client, a["id"])
    assert resumed["status"] == "ACTIVE"
    assert resumed["stages"][0]["payment"]["released"] == 7500
    assert resumed["stages"][1]["status"] == "ACTIVE"
    login(client, "zao")
    ok(
        cmd(
            client,
            f"/stages/{resumed['stages'][1]['id']}/fund",
            {"expected_version": resumed["version"]},
        )
    )
    a = accept_ob(client, a, order(client, a["id"])["stages"][1]["obligations"][0])
    assert a["status"] == "COMPLETED"
    with app.state.registry.get("cash").read() as s:
        assert not s.all("SELECT * FROM bookings")
        assert s.one("SELECT SUM(available+reserved) n FROM accounts")["n"] == 1100000


def test_parallel_second_sign_for_distinct_requests_checks_buyer_capacity(client, app):
    agreements = []
    for i, provider in enumerate(["lin", "wei"]):
        login(client, "zao")
        with app.state.registry.get("cash").tx() as s:
            source = d.get(s, "listings", "request-main")
            data = source["data"]
            start = d.instant(data["start"]) + timedelta(hours=2 * i)
            data.update(
                start=start.isoformat(), end=(start + timedelta(hours=1)).isoformat()
            )
            s.insert(
                "listings",
                id=f"parallel-{i}",
                owner_id="zao",
                kind="REQUEST",
                category="spreadsheet",
                title="獨立時段的表格需求",
                data=dump(data),
            )
        p = ok(
            cmd(
                client,
                "/proposals",
                {
                    "listing_id": f"parallel-{i}",
                    "provider_id": provider,
                    "mode": "MONEY",
                },
            )
        )
        p = ok(
            cmd(
                client,
                f"/proposals/{p['id']}/recommend",
                {"expected_version": p["version"]},
            )
        )
        a = draft(client, p)
        login(client, provider)
        a = ok(
            cmd(
                client,
                f"/agreements/{a['id']}/confirm",
                {"expected_version": a["version"], "terms_version": a["terms_version"]},
            )
        )
        agreements.append(a)
    barrier = Barrier(2)

    def second_sign(a):
        with TestClient(app) as c:
            login(c)
            barrier.wait(timeout=5)
            return cmd(
                c,
                f"/agreements/{a['id']}/confirm",
                {"expected_version": a["version"], "terms_version": a["terms_version"]},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(second_sign, agreements))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["code"]
        == "CAPACITY_EXCEEDED"
    )
    with app.state.registry.get("cash").read() as s:
        assert (
            s.one("SELECT COUNT(*) n FROM agreements WHERE status='ACTIVE'")["n"] == 1
        )
        assert s.one("SELECT COUNT(*) n FROM bookings")["n"] == 2


def test_order_body_private_evidence_and_origin_permissions(client):
    a, _ob = funded_submission(client)
    login(client, "mei")
    assert client.get(f"/api/v1/agreements/{a['id']}").status_code == 403
    assert client.get(f"/api/v1/agreements/{a['id']}/time-ledger").status_code == 403
    assert not any(r["id"] == a["id"] for r in client.get("/api/v1/me/orders").json())
    assert "完整交付的原始工作表" not in str(client.get("/api/v1/listings").json())
    assert client.get("/api/v1/review/queue").status_code == 403
    login(client, "zao")
    view = order(client, a["id"])
    response = client.post(
        f"/api/v1/agreements/{a['id']}/withdraw",
        json={"expected_version": view["version"], "reason": "跨來源命令應被拒絕"},
        headers={
            "Idempotency-Key": "cross-origin",
            "Origin": "https://unrelated.example",
        },
    )
    assert response.status_code == 403 and order(client, a["id"])["status"] == "ACTIVE"


def test_confirmed_breach_remedy_requires_actual_original_resolution(client):
    a, ob = funded_submission(client)
    case = dispute(client, a, ob)
    login(client, "reviewer")
    case = review(client, case, "REDO", confirmed_breach_user_id="lin")
    assert client.get("/api/v1/users/lin/credit").json()["policy"]["blocked"] is True
    assert (
        cmd(
            client,
            f"/disputes/{case['id']}/remedy",
            {
                "expected_version": case["version"],
                "reason": "尚未完成原義務，不可僅點擊就解除限制",
            },
        ).status_code
        == 409
    )
    login(client, "zao")
    ok(
        cmd(
            client,
            f"/agreements/{a['id']}/withdraw",
            {
                "expected_version": order(client, a["id"])["version"],
                "reason": "保留首階段原義務，取消後續未開始服務",
            },
        )
    )
    a, _, _ = sign_closeout(client, a, continue_ids=[ob["id"]])
    a = accept_ob(client, a, order(client, a["id"])["stages"][0]["obligations"][0])
    assert a["status"] == "CANCELLED"
    assert client.get("/api/v1/users/lin/credit").json()["policy"]["blocked"] is True
    login(client, "reviewer")
    ok(
        cmd(
            client,
            f"/disputes/{case['id']}/remedy",
            {
                "expected_version": case["version"],
                "reason": "原義務已實際補做並驗收，剩餘服務及資金按雙方方案結清",
            },
        )
    )
    assert client.get("/api/v1/users/lin/credit").json()["policy"]["blocked"] is False
    login(client, "zao")
    listing = client.get("/api/v1/listings/request-main").json()
    ok(
        cmd(
            client,
            "/listings/request-main/reopen",
            {"expected_version": listing["version"]},
        )
    )
    p = ok(
        cmd(
            client,
            "/proposals",
            {"listing_id": "request-main", "provider_id": "lin", "mode": "MONEY"},
        )
    )
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": p["version"]},
        )
    )
    assert activate(client, draft(client, p))["status"] == "ACTIVE"


def test_assisted_no_intersection_cannot_bypass_calculation_by_drafting(client):
    login(client, "zao", "no_deal")
    p = client.get("/api/v1/me/proposals").json()[0]
    result = cmd(
        client,
        "/agreements",
        {"proposal_id": p["id"], "expected_version": p["version"], "rounds": 2},
    )
    assert result.status_code == 422 and result.json()["code"] == "NO_FEASIBLE_PLAN"
    assert client.get("/api/v1/me/orders").json() == []


def test_assisted_second_signature_rechecks_bounds_then_can_fully_complete(client):
    login(client, "zao", "no_deal")
    p = client.get("/api/v1/me/proposals").json()[0]

    def bound(user, value):
        login(client, user, "no_deal")
        ok(
            cmd(
                client,
                f"/proposals/{p['id']}/preference",
                {
                    "expected_version": p["version"],
                    "scope_version": p["scope_version"],
                    "value": value,
                },
                method="PUT",
            )
        )

    bound("lin", 12000)
    bound("zao", 18000)
    a = draft(client, p)
    a = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/confirm",
            {"expected_version": a["version"], "terms_version": a["terms_version"]},
        )
    )
    bound("zao", 14000)
    login(client, "lin", "no_deal")
    failed = cmd(
        client,
        f"/agreements/{a['id']}/confirm",
        {"expected_version": a["version"], "terms_version": a["terms_version"]},
    )
    assert failed.status_code == 422 and failed.json()["code"] == "NO_FEASIBLE_PLAN"
    assert order(client, a["id"])["status"] == "AWAITING_CONFIRMATION"
    bound("zao", 18000)
    login(client, "lin", "no_deal")
    a = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/confirm",
            {"expected_version": a["version"], "terms_version": a["terms_version"]},
        )
    )
    for i in range(2):
        login(client, "zao", "no_deal")
        view = order(client, a["id"])
        ok(
            cmd(
                client,
                f"/stages/{view['stages'][i]['id']}/fund",
                {"expected_version": view["version"]},
            )
        )
        a = accept_ob(
            client,
            a,
            order(client, a["id"])["stages"][i]["obligations"][0],
            case="no_deal",
        )
    assert a["status"] == "COMPLETED"


def test_direct_consent_is_not_rejected_by_optional_private_bounds(client):
    p = client.get("/api/v1/me/proposals").json()[0]
    for user, value in [("lin", 18000), ("zao", 12000)]:
        login(client, user)
        ok(
            cmd(
                client,
                f"/proposals/{p['id']}/preference",
                {
                    "expected_version": p["version"],
                    "scope_version": p["scope_version"],
                    "value": value,
                },
                method="PUT",
            )
        )
    assert activate(client, draft(client, p))["status"] == "ACTIVE"


def test_selecting_assisted_candidate_preserves_same_service_bounds_and_is_idempotent(
    client,
):
    login(client, "zao", "no_deal")
    p = client.get("/api/v1/me/proposals").json()[0]
    for user, value in [("lin", 18000), ("zao", 22000)]:
        login(client, user, "no_deal")
        ok(
            cmd(
                client,
                f"/proposals/{p['id']}/preference",
                {
                    "expected_version": p["version"],
                    "scope_version": p["scope_version"],
                    "value": value,
                },
                method="PUT",
            )
        )
    assert (
        cmd(
            client,
            f"/proposals/{p['id']}/select",
            {"expected_version": p["version"], "value": 15000},
        ).status_code
        == 422
    )
    body = {"expected_version": p["version"], "value": 20000}
    selected = ok(cmd(client, f"/proposals/{p['id']}/select", body, key="select-once"))
    assert (
        ok(cmd(client, f"/proposals/{p['id']}/select", body, key="select-once"))
        == selected
    )
    preference = client.get(f"/api/v1/proposals/{p['id']}/preference").json()
    assert (
        preference["value"] == 22000
        and preference["scope_version"] == selected["scope_version"]
    )
    assert (
        activate(client, draft(client, selected), case="no_deal")["status"] == "ACTIVE"
    )


def barter_bounds(client, p, low, high):
    for user, value in [("lin", low), ("zao", high)]:
        login(client, user, "barter")
        ok(
            cmd(
                client,
                f"/proposals/{p['id']}/preference",
                {
                    "expected_version": p["version"],
                    "scope_version": p["scope_version"],
                    "value": value,
                },
                method="PUT",
            )
        )


def test_assisted_barter_selects_nearest_executable_window_edge(client, app):
    login(client, "zao", "barter")
    p = client.get("/api/v1/me/proposals").json()[0]
    with app.state.registry.get("barter").tx() as s:
        data = p["data"]
        data["scope"]["end"] = (
            d.instant(data["scope"]["start"]) + timedelta(minutes=180)
        ).isoformat()
        s.execute(
            "UPDATE proposals SET data=?,path='ASSISTED' WHERE id=?",
            (dump(data), p["id"]),
        )
    barter_bounds(client, p, 60, 600)
    candidates = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/calculate",
            {"expected_version": p["version"]},
        )
    )
    assert candidates["candidates"] == [120]
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/select",
            {"expected_version": p["version"], "value": 120},
        )
    )
    a = activate(
        client, draft(client, p, rounds=p["data"]["selected_rounds"]), "barter"
    )
    for i in range(2):
        for j in range(2):
            a = accept_ob(
                client,
                a,
                order(client, a["id"])["stages"][i]["obligations"][j],
                "barter",
            )
    assert a["status"] == "COMPLETED"


def test_assisted_barter_rejects_bounds_without_executable_rounds(client, app):
    login(client, "zao", "barter")
    p = client.get("/api/v1/me/proposals").json()[0]
    with app.state.registry.get("barter").tx() as s:
        data = p["data"]
        data["scope"].update(duration=20, preparation=29, include_preparation=True)
        s.execute("UPDATE proposals SET data=? WHERE id=?", (dump(data), p["id"]))
    barter_bounds(client, p, 0, 15)
    result = cmd(
        client, f"/proposals/{p['id']}/calculate", {"expected_version": p["version"]}
    )
    assert result.status_code == 422 and result.json()["code"] == "NO_FEASIBLE_PLAN"
    assert client.get("/api/v1/me/orders").json() == []


def test_hybrid_recommendation_reprices_current_reverse_duration(client):
    login(client, "zao", "hybrid")
    p = client.get("/api/v1/me/proposals").json()[0]
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "reverse_minutes": 90},
        )
    )
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": p["version"]},
        )
    )
    rec = p["data"]["recommendation"]
    assert rec["reverse"]["estimated_minutes"] == 90
    assert rec["main"]["total_amount"] == rec["reverse"]["total_amount"] == 15000
    assert rec["amount"] == 0
    a = activate(client, draft(client, p), "hybrid")
    for i in range(2):
        login(client, "zao", "hybrid")
        view = order(client, a["id"])
        ok(
            cmd(
                client,
                f"/stages/{view['stages'][i]['id']}/fund",
                {"expected_version": view["version"]},
            )
        )
        for j in range(2):
            a = accept_ob(
                client,
                a,
                order(client, a["id"])["stages"][i]["obligations"][j],
                "hybrid",
            )
    assert a["status"] == "COMPLETED"
    assert client.get("/api/v1/me/mock-account").json()["available"] == 100000

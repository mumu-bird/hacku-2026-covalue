from datetime import timedelta

from backend.app import domain as d
from backend.app.db import dump

from .conftest import accept_ob, activate, cmd, draft, login, ok, order, proposal


def close_body(view, continue_ids=()):
    obligations = [
        o
        for s in view["stages"]
        for o in s["obligations"]
        if o["status"] not in ("ACCEPTED", "WAIVED")
    ]
    payments = [
        s["payment"]
        for s in view["stages"]
        if s["payment"]
        and s["payment"]["reserved"]
        > s["payment"]["released"] + s["payment"]["refunded"]
    ]
    return {
        "expected_version": view["version"],
        "reason": "双方明确确认原义务与资金如何结清",
        "obligations": [
            {
                "obligation_id": o["id"],
                "action": "CONTINUE" if o["id"] in continue_ids else "WAIVE",
            }
            for o in obligations
        ],
        "payments": [
            {"payment_id": p["id"], "action": "HOLD" if continue_ids else "REFUND"}
            for p in payments
        ],
    }


def sign_closeout(c, a, case="cash", continue_ids=()):
    view = order(c, a["id"])
    close = ok(
        cmd(c, f"/agreements/{a['id']}/closeouts", close_body(view, continue_ids))
    )
    body = {"expected_version": close["version"], "agreement_version": view["version"]}
    for user in ("zao", "lin"):
        login(c, user, case)
        result = ok(cmd(c, f"/closeouts/{close['id']}/confirm", body))
    return result, close, body


def test_withdrawal_refunds_only_unstarted_and_idempotent(client, app):
    login(client, "zao", "withdrawal")
    a = client.get("/api/v1/me/orders").json()[0]
    a = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/withdraw",
            {"expected_version": a["version"], "reason": "取消尚未開始的第二階段"},
        )
    )
    a, close, body = sign_closeout(client, a, "withdrawal")
    assert a["status"] == "CANCELLED"
    login(client, "zao", "withdrawal")
    assert ok(client.get("/api/v1/me/mock-account"))["available"] == 94000
    login(client, "lin", "withdrawal")
    assert ok(client.get("/api/v1/me/mock-account"))["available"] == 106000
    # New request cannot refund twice even if a user repeats confirmation.
    assert cmd(client, f"/closeouts/{close['id']}/confirm", body).status_code == 409
    with app.state.registry.get("withdrawal").read() as s:
        assert s.one("SELECT COUNT(*) n FROM ledger WHERE action='REFUND'")["n"] == 1
        assert s.one("SELECT SUM(available+reserved) n FROM accounts")["n"] == 1100000
        assert not s.all("SELECT * FROM bookings")
        assert not s.all("SELECT * FROM evidence WHERE agreement_id=?", (a["id"],))


def test_barter_exit_preserves_original_45_minutes_and_remediation(client):
    login(client, "zao", "barter")
    a = activate(client, draft(client), case="barter")
    view = order(client, a["id"])
    a = accept_ob(client, a, view["stages"][0]["obligations"][0], case="barter")
    login(client, "zao", "barter")
    view = order(client, a["id"])
    owed = view["stages"][0]["obligations"][1]
    assert owed["data"]["minutes"] == 45 and owed["status"] == "READY"
    a = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/withdraw",
            {
                "expected_version": view["version"],
                "reason": "退出後依原約定補做首輪回報",
            },
        )
    )
    a, _close, _ = sign_closeout(client, a, "barter", [owed["id"]])
    view = order(client, a["id"])
    assert view["status"] == "CLOSING"
    assert (
        next(
            o for s in view["stages"] for o in s["obligations"] if o["id"] == owed["id"]
        )["status"]
        == "READY"
    )
    assert all(o["status"] == "WAIVED" for o in view["stages"][1]["obligations"])
    a = accept_ob(client, a, view["stages"][0]["obligations"][1], case="barter")
    assert a["status"] == "CANCELLED"
    login(client, "lin", "barter")
    summary = ok(client.get("/api/v1/me/time-summary"))
    assert (
        summary["provided_minutes"] == 30 and summary["received_service_minutes"] == 45
    )
    assert "balance" not in summary


def test_hybrid_one_side_delivered_no_automatic_refund(client):
    login(client, "zao", "hybrid")
    a = activate(client, draft(client), case="hybrid")
    login(client, "zao", "hybrid")
    view = order(client, a["id"])
    a = ok(
        cmd(
            client,
            f"/stages/{view['stages'][0]['id']}/fund",
            {"expected_version": view["version"]},
        )
    )
    a = accept_ob(
        client, a, order(client, a["id"])["stages"][0]["obligations"][0], case="hybrid"
    )
    login(client, "zao", "hybrid")
    view = order(client, a["id"])
    owed = view["stages"][0]["obligations"][1]
    a = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/withdraw",
            {"expected_version": view["version"], "reason": "退出後仍需核對雙方原回報"},
        )
    )
    view = order(client, a["id"])
    assert (
        view["stages"][0]["payment"]["reserved"] == 2500
        and view["stages"][0]["payment"]["refunded"] == 0
    )
    body = close_body(view, [owed["id"]])
    body["payments"][0]["action"] = "REFUND"
    assert cmd(client, f"/agreements/{a['id']}/closeouts", body).status_code == 422
    a, _, _ = sign_closeout(client, a, "hybrid", [owed["id"]])
    view = order(client, a["id"])
    a = accept_ob(client, a, view["stages"][0]["obligations"][1], case="hybrid")
    assert a["status"] == "CANCELLED"
    assert order(client, a["id"])["stages"][0]["payment"]["released"] == 2500


def test_dispute_does_not_global_block_redo_and_new_time_entries(client, app):
    a = activate(client, draft(client))
    login(client, "zao")
    view = order(client, a["id"])
    a = ok(
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
                "evidence": "首次成果需要核對具体公式",
                "execution_minutes": 20,
            },
        )
    )
    login(client, "zao")
    a = order(client, a["id"])
    dispute = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/disputes",
            {
                "expected_version": a["version"],
                "obligation_id": ob["id"],
                "reason": "公式结果与验收样本不符",
            },
        )
    )
    assert not ok(client.get("/api/v1/users/lin/credit"))["policy"]["blocked"]
    assert order(client, a["id"])["status"] == "DISPUTED"
    assert (
        cmd(
            client,
            f"/disputes/{dispute['id']}/review",
            {
                "expected_version": dispute["version"],
                "outcome": "REDO",
                "basis": "依据具体交付样本核对公式",
            },
        ).status_code
        == 403
    )
    login(client, "reviewer")
    ok(
        cmd(
            client,
            f"/disputes/{dispute['id']}/review",
            {
                "expected_version": dispute["version"],
                "outcome": "REDO",
                "basis": "原义务按同版验收条款重新交付",
            },
        )
    )
    view = order(client, a["id"])
    ob = view["stages"][0]["obligations"][0]
    assert ob["status"] == "READY"
    a = accept_ob(client, a, ob, execution=18)
    with app.state.registry.get("cash").read() as s:
        assert (
            s.one(
                "SELECT SUM(minutes) n FROM time_entries WHERE obligation_id=? AND status='CONFIRMED'",
                (ob["id"],),
            )["n"]
            == 18
        )


def test_expiry_no_auto_accept_breach_or_release(client, app):
    a = activate(client, draft(client))
    db = app.state.registry.get("cash")
    with db.tx() as s:
        row = d.get(
            s,
            "obligations",
            s.one(
                "SELECT id FROM obligations WHERE agreement_id=? LIMIT 1", (a["id"],)
            )["id"],
        )
        data = row["data"]
        data["due_at"] = (d.instant(d.now()) - timedelta(hours=1)).isoformat()
        s.execute("UPDATE obligations SET data=? WHERE id=?", (dump(data), row["id"]))
        d.expire(s)
    view = order(client, a["id"])
    assert view["status"] == "UNRESOLVED"
    assert view["stages"][0]["obligations"][0]["status"] == "LOCKED"
    assert not ok(client.get("/api/v1/users/lin/credit"))["policy"]["blocked"]
    with db.read() as s:
        assert len(s.all("SELECT * FROM bookings")) == 2 and not s.all(
            "SELECT * FROM ledger"
        )


def test_first_investment_limit_and_duration_mismatch(client):
    login(client, "zao", "barter")
    p = proposal(client)
    assert (
        cmd(
            client,
            "/agreements",
            {"proposal_id": p["id"], "expected_version": p["version"], "rounds": 1},
        ).json()["code"]
        == "POLICY_BLOCKED"
    )
    a = activate(client, draft(client), case="barter")
    login(client, "lin", "barter")
    ob = order(client, a["id"])["stages"][0]["obligations"][0]
    assert (
        cmd(
            client,
            f"/obligations/{ob['id']}/submit",
            {
                "expected_version": ob["version"],
                "evidence": "时间不满足原协议的提交",
                "execution_minutes": 45,
            },
        ).status_code
        == 422
    )


def test_reset_isolated_authorized_and_persistent(client, app):
    cash_p = proposal(client)
    assert cmd(client, "/demo/reset").status_code == 403
    login(client, "reviewer", "barter")
    ok(cmd(client, "/demo/reset"))
    login(client, "zao")
    assert proposal(client)["id"] == cash_p["id"]
    login(client, "zao", "barter")
    assert proposal(client)["data"]["reverse_minutes"] == 90


def test_capacity_second_sign_not_precheck(client, app):
    activate(client, draft(client))
    login(client, "zao")
    with app.state.registry.get("cash").tx() as s:
        source = d.get(s, "listings", "request-main")
        data = source["data"]
        data["start"] = (d.instant(data["start"]) + timedelta(hours=1)).isoformat()
        s.insert(
            "listings",
            id="second-request",
            owner_id="zao",
            kind="REQUEST",
            category="spreadsheet",
            title="另一份待处理表格",
            data=dump(data),
        )
    p = ok(
        cmd(
            client,
            "/proposals",
            {"listing_id": "second-request", "provider_id": "wei", "mode": "MONEY"},
        )
    )
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": p["version"]},
        )
    )
    b = draft(client, p)
    b = ok(
        cmd(
            client,
            f"/agreements/{b['id']}/confirm",
            {"expected_version": b["version"], "terms_version": 1},
        )
    )
    login(client, "wei")
    assert (
        cmd(
            client,
            f"/agreements/{b['id']}/confirm",
            {"expected_version": b["version"], "terms_version": 1},
        ).json()["code"]
        == "CAPACITY_EXCEEDED"
    )
    with app.state.registry.get("cash").read() as s:
        assert len(s.all("SELECT * FROM bookings")) == 2


def test_direct_price_change_keeps_advisory_and_new_signatures(client):
    p = proposal(client)
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "amount": 16000},
        )
    )
    assert draft(client, p)["data"]["amount"] == 16000


def test_request_change_invalidates_prior_suggestion(client, app):
    p = proposal(client)
    with app.state.registry.get("cash").tx() as s:
        s.execute("UPDATE listings SET version=version+1 WHERE id='request-main'")
    assert (
        cmd(
            client,
            "/agreements",
            {"proposal_id": p["id"], "expected_version": p["version"], "rounds": 2},
        ).json()["code"]
        == "RECOMMENDATION_STALE"
    )

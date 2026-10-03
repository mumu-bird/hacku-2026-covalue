import json
from datetime import timedelta

from backend.app import domain as d
from backend.app.db import dump

from .conftest import cmd, draft, login, ok, proposal


def test_efficiency_and_capability_change_total(client):
    m = ok(client.get("/api/v1/listings/request-main/matches"))
    assert m["recommended_id"] == "lin"
    a, b, c = m["candidates"]
    assert a["hourly_rate"] > b["hourly_rate"] > c["hourly_rate"]
    assert a["total_amount"] < b["total_amount"] < c["total_amount"]
    assert [a["estimated_minutes"], b["estimated_minutes"], c["estimated_minutes"]] == [
        30,
        60,
        90,
    ]
    assert all("body" not in json.dumps(p["evidence_summary"]) for p in m["candidates"])


def test_missing_skills_and_low_quality_excluded(client, app):
    db = app.state.registry.get("cash")
    with db.tx() as s:
        s.execute("UPDATE evidence SET quality=40 WHERE owner_id='mei'")
        rows = s.all("SELECT * FROM evidence WHERE owner_id='wei'")
        for r in rows:
            data = json.loads(r["data"])
            data["skills"] = ["資料清理"]
            s.execute("UPDATE evidence SET data=? WHERE id=?", (dump(data), r["id"]))
    m = ok(client.get("/api/v1/listings/request-main/matches"))
    assert [c["user_id"] for c in m["candidates"]] == ["lin"]
    assert {"wei", "mei"} <= {c["user_id"] for c in m["excluded"]}


def test_new_user_no_quality_or_premium(client, app):
    db = app.state.registry.get("cash")
    with db.tx() as s:
        l = d.get(s, "listings", "request-main")
        l["data"]["required_skills"] = []
        l["data"]["preferred_skills"] = []
        s.execute(
            "UPDATE listings SET data=? WHERE id=?", (dump(l["data"]), "request-main")
        )
    m = ok(client.get("/api/v1/listings/request-main/matches"))
    newbie = next(c for c in m["candidates"] if c["user_id"] == "peer4")
    assert newbie["quality"] is None and newbie["recommendation_score"] is None
    assert newbie["coefficient"] == 1 and newbie["confidence"] == "待驗證"
    assert newbie["hourly_rate"] == 20000


def test_duplicate_peers_external_limit_and_category_isolation(client, app):
    with app.state.registry.get("cash").tx() as s:
        original = d.evaluate(
            s,
            "lin",
            d.get(s, "listings", "request-main")["data"] | {"category": "spreadsheet"},
        )
        assert original["quality"] == 96
        for n in range(8):
            s.insert(
                "evidence",
                id=f"duplicate-{n}",
                owner_id="lin",
                category="spreadsheet",
                kind="HISTORY",
                peer_id="peer1",
                quality=95,
                status="APPROVED",
                created=d.now(),
                data=dump(
                    {"skills": ["資料清理", "公式"], "title": "同一對手重複資料"}
                ),
            )
        for n in range(8):
            s.insert(
                "evidence",
                id=f"external-{n}",
                owner_id="lin",
                category="spreadsheet",
                kind="WORK",
                quality=90,
                status="APPROVED",
                created=d.now(),
                data=dump({"skills": ["資料清理", "公式"], "title": "已復核作品"}),
            )
        result = d.evaluate(
            s,
            "lin",
            d.get(s, "listings", "request-main")["data"] | {"category": "spreadsheet"},
        )
        assert result["independent_peers"] == 3 and result["evidence_count"] == 5
        english = d.evaluate(
            s,
            "lin",
            {
                "category": "english",
                "difficulty": "basic",
                "workload": "medium",
                "duration": 60,
            },
        )
        assert english["quality"] is None


def test_schedule_mismatch_even_high_quality(client, app):
    with app.state.registry.get("cash").tx() as s:
        r = d.get(s, "listings", "offer-lin-spreadsheet")
        r["data"]["end"] = (
            d.instant(r["data"]["start"]) + timedelta(minutes=1)
        ).isoformat()
        s.execute("UPDATE listings SET data=? WHERE id=?", (dump(r["data"]), r["id"]))
    result = ok(client.get("/api/v1/listings/request-main/matches"))
    assert "lin" not in [r["user_id"] for r in result["candidates"]]


def test_evidence_review_permissions_and_stale_recommendation(client):
    login(client, "lin")
    ev = ok(
        cmd(
            client,
            "/capability-evidence",
            {
                "category": "spreadsheet",
                "kind": "WORK",
                "title": "整理結果",
                "body": "資料、公式與格式的完整演示作品",
                "skills": ["資料清理", "公式"],
                "difficulty": "basic",
            },
        )
    )
    review = {
        "approve": True,
        "scores": {"correctness": 95, "completeness": 95, "independence": 95},
        "basis": "依作品內容與模板逐項核對確認",
    }
    assert (
        cmd(client, f"/capability-evidence/{ev['id']}/review", review).status_code
        == 403
    )
    login(client, "reviewer")
    ok(cmd(client, f"/capability-evidence/{ev['id']}/review", review))
    login(client, "zao")
    p = proposal(client)
    response = cmd(
        client,
        "/agreements",
        {"proposal_id": p["id"], "expected_version": p["version"], "rounds": 2},
    )
    assert response.json()["code"] == "RECOMMENDATION_STALE"
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": p["version"]},
        )
    )
    assert draft(client, p)["status"] == "AWAITING_CONFIRMATION"


def test_prep_changes_quote_and_reverse_minutes(client):
    login(client, "zao", "barter")
    p = proposal(client)
    assert p["data"]["reverse_minutes"] == 90
    scope = p["data"]["scope"].copy()
    scope.pop("category")
    scope.pop("title")
    scope = {
        **scope,
        "category": "tutoring",
        "title": "輔導加備課",
        "kind": "REQUEST",
        "preparation": 20,
        "include_preparation": True,
    }
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/revise",
            {"expected_version": p["version"], "scope": scope},
        )
    )
    p = ok(
        cmd(
            client,
            f"/proposals/{p['id']}/recommend",
            {"expected_version": p["version"]},
        )
    )
    assert p["data"]["recommendation"]["main"]["estimated_minutes"] == 80
    assert p["data"]["reverse_minutes"] == 120


def test_template_rubric_quality_and_advanced_threshold(client, app):
    with app.state.registry.get("cash").tx() as s:
        assert (
            d.quality({"correctness": 100, "completeness": 80, "independence": 60})
            == 86
        )
        scope = d.get(s, "listings", "request-main")["data"] | {
            "category": "spreadsheet",
            "difficulty": "advanced",
        }
        assert not d.evaluate(s, "lin", scope)["eligible"]
        assert not d.evaluate(s, "wei", scope)["eligible"]

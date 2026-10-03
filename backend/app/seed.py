import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import domain as d
from .config import POLICY, TEMPLATES
from .db import dump


def seed(s, case):
    fixture = json.loads(
        (Path(__file__).resolve().parents[2] / "fixtures" / f"{case}.json").read_text()
    )
    start = (datetime.now(UTC) + timedelta(hours=2)).replace(microsecond=0)
    end = start + timedelta(hours=8)
    people = [
        ("zao", "周予安", "予", "想學好表格，也能陪你練習英語", 0),
        ("lin", "林知行", "知", "表格處理與教學 · 擅長把複雜問題說清楚", 0),
        ("wei", "陳思維", "維", "細心整理資料，提供完整交付說明", 0),
        ("mei", "許映美", "映", "從基礎開始，一起完成每個小目標", 0),
        ("reviewer", "社羣復核員", "審", "依據作品、測評與原協議復核", 1),
    ]
    people += [
        (f"peer{i}", f"演示對手 {i}", str(i), "模擬歷史交易對手", 0)
        for i in range(1, 7)
    ]
    for id, name, initials, headline, reviewer in people:
        s.execute(
            "INSERT OR IGNORE INTO users(id,name,initials,headline,reviewer) VALUES(?,?,?,?,?)",
            (id, name, initials, headline, reviewer),
        )
        s.execute("UPDATE users SET blocked=0 WHERE id=?", (id,))
        s.insert("accounts", user_id=id, available=POLICY["initial_balance"])

    def scope(category, kind="OFFER"):
        t = TEMPLATES[category]
        return {
            "scenario": "學習社羣的非標準服務需求",
            "difficulty": "basic",
            "workload": "medium",
            "required_skills": t["skills"][:2] if kind == "REQUEST" else [],
            "preferred_skills": t["skills"][2:] if kind == "REQUEST" else [],
            "duration": 60,
            "preparation": 0,
            "travel": 0,
            "include_preparation": False,
            "include_travel": False,
            "material_amount": 0,
            "transport_amount": 0,
            "delivery_standard": t["deliverable"],
            "service_mode": "ONLINE",
            "location": "線上",
            "start": (start - timedelta(hours=1)).isoformat()
            if kind == "OFFER"
            else start.isoformat(),
            "end": (end + timedelta(hours=1)).isoformat()
            if kind == "OFFER"
            else end.isoformat(),
            "accepted_modes": ["MONEY", "BARTER", "HYBRID"],
        }

    for actor, q, minutes in [("lin", 96, 30), ("wei", 85, 60), ("mei", 75, 90)]:
        for category in ("spreadsheet", "tutoring"):
            for n in range(3):
                payload = {
                    "title": f"{TEMPLATES[category]['name']} · 已確認履約 {n + 1}",
                    "difficulty": "basic",
                    "workload": "medium",
                    "skills": TEMPLATES[category]["skills"],
                    "confirmed_minutes": minutes if category == "spreadsheet" else 60,
                    "source": "獨立種子歷史（模擬）",
                    "basis": "正確性、完整性與獨立完成的預置驗收",
                    "is_demo": True,
                }
                s.insert(
                    "evidence",
                    id=f"ev-{actor}-{category}-{n}",
                    owner_id=actor,
                    category=category,
                    kind="HISTORY",
                    peer_id=f"peer{n + 1}",
                    data=dump(payload),
                    status="APPROVED",
                    quality=q,
                    created=(start - timedelta(days=5 - n)).isoformat(),
                )
            s.insert(
                "listings",
                id=f"offer-{actor}-{category}",
                owner_id=actor,
                kind="OFFER",
                title=f"{TEMPLATES[category]['name']} · {s.one('SELECT name FROM users WHERE id=?', (actor,))['name']}",
                category=category,
                data=dump(scope(category)),
            )
    s.insert(
        "evidence",
        id="ev-zao-english",
        owner_id="zao",
        category="english",
        kind="ASSESSMENT",
        data=dump(
            {
                "title": "英語交流結構化測評",
                "body": "模擬測評材料：交流、發音回饋、引導練習",
                "difficulty": "basic",
                "skills": TEMPLATES["english"]["skills"],
                "basis": "復核員確認：正確性 74、完整性 74、自主完成 74",
                "source": "預置已復核測評（模擬）",
                "is_demo": True,
            }
        ),
        status="APPROVED",
        quality=74,
        created=start.isoformat(),
        reviewer_id="reviewer",
    )
    s.insert(
        "listings",
        id="offer-zao-english",
        owner_id="zao",
        kind="OFFER",
        title="一起練習英語交流",
        category="english",
        data=dump(scope("english")),
    )
    s.insert(
        "listings",
        id="offer-peer4-spreadsheet",
        owner_id="peer4",
        kind="OFFER",
        title="基礎表格整理 · 待驗證",
        category="spreadsheet",
        data=dump(scope("spreadsheet")),
    )
    category = fixture["category"]
    title = (
        "想把表格公式真正學懂"
        if category == "tutoring"
        else "整理一份散亂的社羣活動表格"
    )
    main = scope(category, "REQUEST")
    s.insert(
        "listings",
        id="request-main",
        owner_id="zao",
        kind="REQUEST",
        title=title,
        category=category,
        data=dump(main),
    )
    for n, (category, title) in enumerate(
        [
            ("tutoring", "有人能教我用表格做預算嗎？"),
            ("english", "想找人一起練習英文自我介紹"),
            ("spreadsheet", "幫我整理讀書會報名清單"),
        ]
    ):
        s.insert(
            "listings",
            id=f"request-extra-{n}",
            owner_id=f"peer{n + 4}",
            kind="REQUEST",
            title=title,
            category=category,
            data=dump(scope(category, "REQUEST")),
        )
    mode = fixture["mode"]
    p = d.create_proposal(
        s,
        "zao",
        {
            "listing_id": "request-main",
            "provider_id": "lin",
            "mode": mode,
            "reverse_listing_id": "offer-zao-english" if mode != "MONEY" else None,
            "negotiation_path": "ASSISTED" if case == "no_deal" else "DIRECT",
        },
    )
    p = d.recommend(s, "zao", p, p["version"])
    if case == "no_deal":
        for actor, value in fixture["bounds"].items():
            d.preference(
                s,
                actor,
                p,
                {
                    "expected_version": p["version"],
                    "scope_version": p["scope_version"],
                    "value": value,
                },
            )
    if case == "withdrawal":
        a = d.create_agreement(
            s,
            "zao",
            p,
            {
                "expected_version": p["version"],
                "rounds": 2,
                "stage_amounts": fixture["stage_amounts"],
            },
        )
        for actor in ("zao", "lin"):
            a = d.confirm(
                s,
                actor,
                a,
                {"expected_version": a["version"], "terms_version": a["terms_version"]},
            )
        stage = s.one(
            "SELECT * FROM stages WHERE agreement_id=? AND round_no=1", (a["id"],)
        )
        a = d.fund(s, "zao", stage, a["version"])
        ob = d.get(
            s,
            "obligations",
            s.one("SELECT id FROM obligations WHERE stage_id=?", (stage["id"],))["id"],
        )
        ob = d.submit(
            s,
            "lin",
            ob,
            {
                "expected_version": ob["version"],
                "evidence": "預置材料：已交付並整理樣本工作表",
                "execution_minutes": 12,
            },
        )
        a = d.accept(
            s,
            "zao",
            ob,
            {
                "expected_version": ob["version"],
                "scores": {"correctness": 96, "completeness": 96, "independence": 96},
            },
        )
        stage = s.one(
            "SELECT * FROM stages WHERE agreement_id=? AND round_no=2", (a["id"],)
        )
        d.fund(s, "zao", stage, a["version"])
    d.emit(s, "reviewer", "demo", case, "SEEDED", {"simulated": True})


def reset(s, case):
    for table in [
        "idempotency",
        "events",
        "ledger",
        "time_entries",
        "closeouts",
        "disputes",
        "consents",
        "bookings",
        "evidence",
        "payment_intents",
        "obligations",
        "stages",
        "agreements",
        "preferences",
        "perspectives",
        "proposals",
        "listings",
        "accounts",
    ]:
        s.execute(f"DELETE FROM {table}")
    seed(s, case)

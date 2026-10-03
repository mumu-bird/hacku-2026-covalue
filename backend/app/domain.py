import uuid
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from hashlib import sha256
from math import ceil, floor
from statistics import median

from .config import POLICY, RULE_VERSION, TEMPLATES
from .db import dump, unpack
from .value_model import SWINGS, nash_candidates, recipient_benefit


class DomainError(Exception):
    def __init__(self, code, message, details=None, status=409):
        self.code, self.message, self.details, self.status = (
            code,
            message,
            details or {},
            status,
        )

    def payload(self):
        return {"code": self.code, "message": self.message, "details": self.details}


def fail(code, message, details=None, status=409):
    raise DomainError(code, message, details, status)


def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def now():
    return datetime.now(UTC).isoformat()


def instant(value):
    return datetime.fromisoformat(value).astimezone(UTC)


def normalize(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def get(s, table, id):
    r = unpack(s.one(f"SELECT * FROM {table} WHERE id=?", (id,)))
    if not r:
        fail("NOT_FOUND", "找不到這項資料", status=404)
    return r


def version(row, expected):
    if expected != row["version"]:
        fail(
            "VERSION_CONFLICT",
            "內容已更新，請重新載入",
            {"current_version": row["version"]},
        )


def participant(row, user):
    if user not in (row["requester_id"], row["provider_id"]):
        fail("UNAUTHORIZED_ACTION", "只有交易雙方可操作", status=403)


def reviewer(s, user):
    if not get(s, "users", user)["reviewer"]:
        fail("UNAUTHORIZED_ACTION", "需要授權復核員", status=403)


def emit(s, user, entity, id, action, data=None):
    s.insert(
        "events",
        id=uid("evt"),
        actor_id=user,
        entity=entity,
        entity_id=id,
        action=action,
        data=dump(data or {}),
        created=now(),
    )


def amount_round(value):
    return int((Fraction(value) + 50) // 100) * 100


def evidence_for(s, user, category, minimum_difficulty=None):
    rows = s.all(
        "SELECT e.* FROM evidence e LEFT JOIN agreements a ON e.agreement_id=a.id WHERE e.owner_id=? AND e.category=? AND e.status='APPROVED' AND (e.agreement_id IS NULL OR a.status='COMPLETED') ORDER BY e.created DESC, e.id DESC",
        (user, category),
    )
    selected = []
    peers = set()
    external = 0
    for raw in rows:
        row = unpack(raw)
        if minimum_difficulty:
            difficulty_rank = {"basic": 0, "medium": 1, "advanced": 2}
            if (
                difficulty_rank.get(row["data"].get("difficulty", "basic"), 0)
                < difficulty_rank[minimum_difficulty]
            ):
                continue
        if row["kind"] == "HISTORY":
            if row["peer_id"] in peers:
                continue
            peers.add(row["peer_id"])
        else:
            if external >= POLICY["max_external"]:
                continue
            external += 1
        selected.append(row)
        if len(selected) >= POLICY["max_evidence"]:
            break
    return selected


def capacity(s, user, category, role="PROVIDER"):
    rows = evidence_for(s, user, category)
    peers = {r["peer_id"] for r in rows if r["kind"] == "HISTORY"}
    if role == "REQUESTER":
        histories = [
            unpack(r)
            for r in s.all(
                "SELECT * FROM agreements WHERE requester_id=? AND mode='MONEY' AND status='COMPLETED'",
                (user,),
            )
        ]
        peers = {
            r["provider_id"]
            for r in histories
            if r["data"]["scope"]["category"] == category
        }
    advanced = len(peers) >= 3 and not get(s, "users", user)["blocked"]
    in_flight = s.one(
        "SELECT COUNT(*) n FROM agreements WHERE (requester_id=? OR provider_id=?) AND status IN ('ACTIVE','CLOSING','DISPUTED','UNRESOLVED')",
        (user, user),
    )["n"]
    return {
        "limit": 2 if advanced else 1,
        "in_flight": in_flight,
        "advanced": advanced,
        "blocked": bool(get(s, "users", user)["blocked"]),
        "role": role,
        "completed_peers": len(peers),
    }


def evaluate(s, user, scope):
    template = TEMPLATES[scope["category"]]
    rows = evidence_for(s, user, scope["category"], scope.get("difficulty", "basic"))
    qualities = [r["quality"] for r in rows if r["quality"] is not None]
    q = float(median(qualities)) if qualities else None
    skills = sorted({skill for r in rows for skill in r["data"].get("skills", [])})
    required = scope.get("required_skills", [])
    preferred = scope.get("preferred_skills", [])
    all_skills = set(required + preferred)
    m = (
        100 * len(all_skills.intersection(skills)) / len(all_skills)
        if all_skills
        else 100
    )
    missing = [x for x in required if x not in skills]
    peers = {r["peer_id"] for r in rows if r["kind"] == "HISTORY"}
    external = sum(r["kind"] != "HISTORY" for r in rows)
    e = min(100, 20 * len(peers) + 10 * external)
    threshold = {"basic": 60, "medium": 80, "advanced": 90}[
        scope.get("difficulty", "basic")
    ]
    eligible = not missing and (
        q is None and threshold == 60 or q is not None and q >= threshold
    )
    k = (
        Fraction(3, 2)
        if q is not None and q >= 90
        else Fraction(5, 4)
        if q is not None and q >= 80
        else Fraction(1)
    )
    rate = amount_round(template["base_rate"] * k)
    basis = template["basis"]
    matching = [
        r
        for r in rows
        if r["kind"] == "HISTORY"
        and r["data"].get("difficulty") == scope.get("difficulty", "basic")
        and r["data"].get("workload") == scope.get("workload", "medium")
        and r["data"].get("confirmed_minutes", 0) > 0
    ]
    samples = [r["data"]["confirmed_minutes"] for r in matching]
    sufficient = len(samples) >= 3
    if basis == "DURATION":
        execution = scope.get("duration", 60)
        source = "約定服務時長"
    elif sufficient:
        execution = int(median(samples))
        source = "同類、同難度與工作量的已確認歷史中位數"
    else:
        execution = template["minutes"][scope.get("workload", "medium")]
        source = "公開任務模板；歷史樣本不足"
    prep = scope.get("preparation", 0) if scope.get("include_preparation") else 0
    travel = scope.get("travel", 0) if scope.get("include_travel") else 0
    minutes = execution + prep + travel
    confidence = "充足" if len(peers) >= 3 else "有限" if rows else "待驗證"
    band = Fraction(1, 5) if len(peers) >= 3 else Fraction(2, 5)
    if basis == "DURATION":
        execution_range = [execution, execution]
        duration_band = Fraction(0)
        duration_mad = None
    elif sufficient:
        center = Fraction(median(samples))
        duration_mad = median(abs(Fraction(x) - center) for x in samples)
        duration_band = max(Fraction(1, 5), duration_mad / center)
        execution_range = [
            max(1, floor(execution * (1 - duration_band))),
            max(1, ceil(execution * (1 + duration_band))),
        ]
    else:
        duration_band = Fraction(2, 5)
        duration_mad = None
        execution_range = [
            max(1, floor(execution * (1 - duration_band))),
            max(1, ceil(execution * (1 + duration_band))),
        ]
    minutes_range = [x + prep + travel for x in execution_range]
    hourly_range = [
        amount_round(rate * (1 - band)),
        amount_round(rate * (1 + band)),
    ]
    total = (
        amount_round(Fraction(rate * minutes, 60))
        + scope.get("material_amount", 0)
        + scope.get("transport_amount", 0)
    )
    score = (
        round(sum(w * v / 100 for w, v in zip(POLICY["ranking_weights"], (m, q, e))), 2)
        if q is not None
        else None
    )
    digest = sha256(
        dump(
            [{"id": r["id"], "quality": r["quality"], "data": r["data"]} for r in rows]
        ).encode()
    ).hexdigest()
    fees = scope.get("material_amount", 0) + scope.get("transport_amount", 0)
    total_range = [
        amount_round(Fraction(hourly_range[i] * minutes_range[i], 60)) + fees
        for i in (0, 1)
    ]
    suggested = eligible and q is not None
    valuation = {
        "algorithm_version": "value-estimate-v1",
        "pricing_rule_version": RULE_VERSION,
        "status": "ESTIMATED"
        if suggested
        else "TEMPLATE_ONLY"
        if eligible
        else "NOT_ELIGIBLE",
        "suggested_amount": total if suggested else None,
        "reference_amount": total,
        "amount_range": total_range if suggested else None,
        "reference_range": total_range,
        "currency": POLICY["currency"],
        "base_hourly_rate": template["base_rate"],
        "quality": q,
        "quality_coefficient": float(k),
        "hourly_rate": rate,
        "hourly_range": hourly_range,
        "execution_minutes": execution,
        "execution_range": execution_range,
        "preparation_minutes": prep,
        "travel_minutes": travel,
        "recognized_minutes": minutes,
        "minutes_range": minutes_range,
        "time_amount": total - fees,
        "material_amount": scope.get("material_amount", 0),
        "transport_amount": scope.get("transport_amount", 0),
        "duration_source": source,
        "duration_sample_count": len(samples),
        "duration_mad_minutes": float(duration_mad)
        if duration_mad is not None
        else None,
        "duration_band": float(duration_band),
        "rate_band": float(band),
        "independent_peers": len(peers),
        "reviewed_external_count": external,
        "evidence_count": len(rows),
        "evidence_digest": digest,
        "difficulty": scope.get("difficulty", "basic"),
        "workload": scope.get("workload", "medium"),
        "formula": "小時基準 × 能力系數 × 認可投入分鐘 ÷ 60 ＋ 單列現金費用",
        "range_basis": "時薪演示範圍與工時範圍組合；固定時長及已納入的準備、差旅不作隨機浮動；不是統計置信區間",
        "is_demo": True,
    }
    return {
        "user_id": user,
        "category": scope["category"],
        "quality": q,
        "fit": round(m, 2),
        "evidence_score": e,
        "recommendation_score": score,
        "eligible": eligible,
        "missing_skills": missing,
        "verified_skills": skills,
        "evidence_count": len(rows),
        "independent_peers": len(peers),
        "confidence": confidence,
        "coefficient": float(k),
        "hourly_rate": rate,
        "hourly_range": hourly_range,
        "estimated_minutes": minutes,
        "execution_minutes": execution,
        "preparation_minutes": prep,
        "travel_minutes": travel,
        "minutes_range": minutes_range,
        "value_estimate": valuation,
        "estimate_source": source,
        "total_amount": total,
        "time_amount": amount_round(Fraction(rate * minutes, 60)),
        "material_amount": scope.get("material_amount", 0),
        "transport_amount": scope.get("transport_amount", 0),
        "evidence_digest": digest,
        "evidence_summary": [
            {
                "id": r["id"],
                "kind": r["kind"],
                "quality": r["quality"],
                "title": r["data"].get("title", "相關履約"),
                "difficulty": r["data"].get("difficulty"),
                "skills": r["data"].get("skills", []),
            }
            for r in rows
        ],
        "rule_version": RULE_VERSION,
        "is_demo": True,
    }


def overlap(a, b, c, d):
    return instant(a) < instant(d) and instant(c) < instant(b)


def schedule_free(s, user, start, end, exclude=None):
    for row in s.all("SELECT * FROM bookings WHERE user_id=?", (user,)):
        if row["agreement_id"] != exclude and overlap(
            start, end, row["start"], row["end"]
        ):
            return False
    return True


def matches(s, listing):
    scope = {**listing["data"], "category": listing["category"]}
    candidates = []
    excluded = []
    seen = set()
    for raw in s.all(
        "SELECT * FROM listings WHERE kind='OFFER' AND status='OPEN' AND category=?",
        (listing["category"],),
    ):
        offer = unpack(raw)
        user = offer["owner_id"]
        if user == listing["owner_id"] or user in seen:
            continue
        result = evaluate(s, user, scope)
        result["benefit"] = recipient_benefit(
            result, scope["category"], scope.get("duration", 60)
        )
        d = offer["data"]
        p = capacity(s, user, listing["category"])
        reason = None
        if not result["eligible"]:
            reason = "必需技能或本單能力門檻不符"
        elif (
            d.get("service_mode") != scope.get("service_mode")
            or scope.get("service_mode") == "OFFLINE"
            and d.get("location") != scope.get("location")
        ):
            reason = "服務方式或地點不符"
        elif (
            instant(d["start"]) > instant(scope["start"])
            or instant(d["end"]) < instant(scope["end"])
            or not schedule_free(s, user, scope["start"], scope["end"])
        ):
            reason = "可用時段不符或已被佔用"
        elif (
            instant(scope["end"]) - instant(scope["start"])
        ).total_seconds() / 60 < result["estimated_minutes"]:
            reason = "時段不足以完成預計投入"
        elif p["blocked"] or p["in_flight"] >= p["limit"]:
            reason = "目前在途容量或交易保護限制"
        if reason:
            excluded.append({"user_id": user, "reason": reason})
            continue
        seen.add(user)
        profile = get(s, "users", user)
        candidates.append(
            {
                **result,
                "name": profile["name"],
                "initials": profile["initials"],
                "headline": profile["headline"],
                "offer_id": offer["id"],
                "capacity": p,
            }
        )
    verified = sorted(
        [c for c in candidates if c["quality"] is not None],
        key=lambda c: (-c["recommendation_score"], c["total_amount"], c["user_id"]),
    )
    pending = sorted(
        [c for c in candidates if c["quality"] is None], key=lambda c: c["user_id"]
    )
    frontier = [
        c["user_id"]
        for c in verified
        if not any(
            other["user_id"] != c["user_id"]
            and other["benefit"]["score"] >= c["benefit"]["score"]
            and other["total_amount"] <= c["total_amount"]
            and other["estimated_minutes"] <= c["estimated_minutes"]
            and (
                other["benefit"]["score"] > c["benefit"]["score"]
                or other["total_amount"] < c["total_amount"]
                or other["estimated_minutes"] < c["estimated_minutes"]
            )
            for other in verified
        )
    ]
    return {
        "candidates": verified + pending,
        "pending_verification": pending,
        "benefit_frontier_ids": frontier,
        "excluded": excluded,
        "recommended_id": verified[0]["user_id"] if verified else None,
        "budget_id": min(verified, key=lambda c: (c["total_amount"], c["user_id"]))[
            "user_id"
        ]
        if verified
        else None,
        "fastest_id": min(
            verified, key=lambda c: (c["estimated_minutes"], c["user_id"])
        )["user_id"]
        if verified
        else None,
        "rule_version": RULE_VERSION,
        "is_demo": True,
    }


def create_proposal(s, user, body):
    listing = get(s, "listings", body["listing_id"])
    if listing["status"] != "OPEN":
        fail("LISTING_TAKEN", "需求目前不可承接")
    if listing["kind"] == "REQUEST":
        requester = listing["owner_id"]
        provider = body.get("provider_id") or user
        if user != requester and provider != user:
            fail("UNAUTHORIZED_ACTION", "不能代他人報價", status=403)
    else:
        requester = user
        provider = listing["owner_id"]
    if requester == provider:
        fail("INVALID_INPUT", "不能與自己交易", status=422)
    get(s, "users", provider)
    mode = body.get("mode", "MONEY")
    if mode not in listing["data"]["accepted_modes"]:
        fail("INVALID_INPUT", "刊登未接受這種交易方式", status=422)
    reverse = None
    if mode != "MONEY":
        if not body.get("reverse_listing_id"):
            fail("INVALID_INPUT", "互換需要反向服務", status=422)
        reverse = get(s, "listings", body["reverse_listing_id"])
        if (
            reverse["owner_id"] != requester
            or reverse["kind"] != "OFFER"
            or reverse["status"] != "OPEN"
        ):
            fail("INVALID_INPUT", "反向服務必須由需求方提供", status=422)
    scope = {
        **listing["data"],
        "category": listing["category"],
        "title": listing["title"],
    }
    data = {
        "scope": scope,
        "listing_version": listing["version"],
        "reverse": {
            **reverse["data"],
            "category": reverse["category"],
            "title": reverse["title"],
            "listing_id": reverse["id"],
            "listing_version": reverse["version"],
        }
        if reverse
        else None,
        "amount": 0,
        "reverse_minutes": reverse["data"]["duration"] if reverse else None,
        "payer_id": requester,
        "payee_id": provider,
        "recommendation": None,
        "warnings": [],
    }
    id = uid("proposal")
    s.insert(
        "proposals",
        id=id,
        listing_id=listing["id"],
        requester_id=requester,
        provider_id=provider,
        mode=mode,
        path=body.get("negotiation_path", "DIRECT"),
        data=dump(data),
    )
    emit(s, user, "proposal", id, "CREATED")
    return get(s, "proposals", id)


def exchange_rounds(main, reverse, minutes, window, limit):
    if (
        main["estimated_minutes"]
        + minutes
        + reverse["preparation_minutes"]
        + reverse["travel_minutes"]
        > window
    ):
        return None
    return next(
        (
            n
            for n in range(2, 21)
            if n <= min(main["execution_minutes"], minutes)
            and (main["execution_minutes"] + n - 1) // n
            + main["preparation_minutes"]
            + main["travel_minutes"]
            <= limit
        ),
        None,
    )


def recommendation(s, p):
    d = p["data"]
    if p["mode"] == "BARTER" and any(
        scope and (scope.get("material_amount", 0) or scope.get("transport_amount", 0))
        for scope in (d["scope"], d["reverse"])
    ):
        fail(
            "INVALID_INPUT",
            "純互換不包含現金費用，請選擇互換補差並單列費用",
            status=422,
        )
    a = evaluate(s, p["provider_id"], d["scope"])
    if not a["eligible"]:
        fail("POLICY_BLOCKED", "供給方未符合本單技能或能力門檻")
    if a["quality"] is None:
        fail(
            "INSUFFICIENT_EVIDENCE",
            "缺少已確認能力證據，只能展示模板參考；請先復核作品或測評，再生成平台方案",
            status=422,
        )
    b = None
    cash = 0
    payer = p["requester_id"]
    payee = p["provider_id"]
    chosen = d.get("reverse_minutes")
    rounds = min(2, a["execution_minutes"])
    if p["mode"] == "MONEY":
        cash = a["total_amount"]
    else:
        if d["reverse"]["category"] not in TEMPLATES:
            fail("INVALID_INPUT", "反向服務類別不符", status=422)
        b = evaluate(s, p["requester_id"], d["reverse"] | {"duration": chosen})
        if not b["eligible"]:
            fail("POLICY_BLOCKED", "反向服務未符合能力門檻")
        if b["quality"] is None:
            fail(
                "INSUFFICIENT_EVIDENCE",
                "反向服務缺少已確認能力證據，平台暫停生成確定交換方案；請先復核或明確協商",
                status=422,
            )
        rs, scope = d["reverse"], d["scope"]
        if (
            instant(rs["start"]) > instant(scope["start"])
            or instant(rs["end"]) < instant(scope["end"])
            or rs["service_mode"] != scope["service_mode"]
            or scope["service_mode"] == "OFFLINE"
            and rs["location"] != scope["location"]
        ):
            fail("NO_FEASIBLE_PLAN", "反向服務時段、方式或地點不符合本單", status=422)
        both_advanced = (
            capacity(s, p["provider_id"], scope["category"])["advanced"]
            and capacity(s, p["requester_id"], rs["category"])["advanced"]
        )
        limit = (
            POLICY["advanced_minutes"] if both_advanced else POLICY["advance_minutes"]
        )

        def legal_rounds(minutes):
            window = (
                instant(scope["end"]) - instant(scope["start"])
            ).total_seconds() / 60
            return exchange_rounds(a, b, minutes, window, limit)

        if p["mode"] == "BARTER":
            if TEMPLATES[d["reverse"]["category"]]["basis"] != "DURATION":
                fail("INVALID_INPUT", "首版輔助互換以反向時長型服務為變量", status=422)
            window = int(
                (
                    instant(d["scope"]["end"]) - instant(d["scope"]["start"])
                ).total_seconds()
                / 60
            )
            candidates = range(
                POLICY["time_step"],
                max(
                    16,
                    min(
                        1440,
                        window
                        - a["estimated_minutes"]
                        - b["preparation_minutes"]
                        - b["travel_minutes"],
                    )
                    + 1,
                ),
                POLICY["time_step"],
            )
            losses = {
                x: abs(
                    Fraction(
                        b["hourly_rate"]
                        * (x + b["preparation_minutes"] + b["travel_minutes"]),
                        60,
                    )
                    + d["reverse"].get("material_amount", 0)
                    + d["reverse"].get("transport_amount", 0)
                    - a["total_amount"]
                )
                for x in candidates
                if legal_rounds(x) is not None
            }
            if not losses:
                fail("NO_FEASIBLE_PLAN", "時段內沒有合法的交換方案", status=422)
            minimum = min(losses.values())
            options = [x for x, v in losses.items() if v == minimum]
            chosen = options[0]
            rounds = legal_rounds(chosen)
            b = evaluate(s, p["requester_id"], d["reverse"] | {"duration": chosen})
        else:
            rounds = legal_rounds(chosen)
            if rounds is None:
                fail("NO_FEASIBLE_PLAN", "固定服務組合沒有合法的分輪方案", status=422)
            delta = a["total_amount"] - b["total_amount"]
            cash = abs(delta)
            if delta < 0:
                payer, payee = payee, payer
    rec = {
        "main": a,
        "reverse": b,
        "amount": cash,
        "reverse_minutes": chosen,
        "rounds": rounds,
        "payer_id": payer,
        "payee_id": payee,
        "candidates": options if p["mode"] == "BARTER" else [],
        "rule_version": RULE_VERSION,
        "scope_version": p["scope_version"],
        "created": now(),
        "is_demo": True,
    }
    return rec


def recommend(s, user, p, expected):
    participant(p, user)
    version(p, expected)
    if s.one(
        "SELECT id FROM agreements WHERE proposal_id=? AND status NOT IN ('CANCELLED')",
        (p["id"],),
    ):
        fail("INVALID_STATE", "已有協議，請透過結清或新單處理")
    rec = recommendation(s, p)
    if rec["reverse_minutes"] != p["data"].get("reverse_minutes"):
        s.execute("DELETE FROM perspectives WHERE proposal_id=?", (p["id"],))
        s.execute("DELETE FROM value_contexts WHERE proposal_id=?", (p["id"],))
    d = {
        **p["data"],
        "recommendation": rec,
        "selected_rounds": None,
        "amount": rec["amount"],
        "reverse_minutes": rec["reverse_minutes"],
        "payer_id": rec["payer_id"],
        "payee_id": rec["payee_id"],
    }
    s.execute(
        "UPDATE proposals SET data=?,version=version+1 WHERE id=?", (dump(d), p["id"])
    )
    emit(s, user, "proposal", p["id"], "RECOMMENDED", {"rule_version": RULE_VERSION})
    return get(s, "proposals", p["id"])


def revise(s, user, p, body):
    participant(p, user)
    version(p, body["expected_version"])
    if s.one(
        "SELECT id FROM agreements WHERE proposal_id=? AND status IN ('ACTIVE','CLOSING','DISPUTED','UNRESOLVED','COMPLETED')",
        (p["id"],),
    ):
        fail("INVALID_STATE", "生效條款不能單方修改")
    d = p["data"]
    mode = body.get("mode") or p["mode"]
    if mode != "MONEY" and not d["reverse"]:
        fail("INVALID_INPUT", "請先建立含反向服務的新提案", status=422)
    changed_scope = (
        bool(body.get("scope"))
        or mode != p["mode"]
        or body.get("cash_payer_id")
        and body["cash_payer_id"] != d["payer_id"]
    )
    if body.get("scope"):
        d["scope"] = {**normalize(body["scope"]), "title": body["scope"]["title"]}
    if body.get("amount") is not None:
        d["amount"] = body["amount"]
    if body.get("reverse_minutes") is not None:
        d["reverse_minutes"] = body["reverse_minutes"]
        changed_scope = True
    if mode == "MONEY":
        d.update(
            payer_id=p["requester_id"], payee_id=p["provider_id"], reverse_minutes=None
        )
    elif body.get("cash_payer_id"):
        if body["cash_payer_id"] not in (p["requester_id"], p["provider_id"]):
            fail("INVALID_INPUT", "付款方必須為交易當事人", status=422)
        d["payer_id"] = body["cash_payer_id"]
        d["payee_id"] = (
            p["provider_id"]
            if d["payer_id"] == p["requester_id"]
            else p["requester_id"]
        )
    if mode == "BARTER":
        d["amount"] = 0
    d["selected_rounds"] = None
    d["warnings"] = []
    rec = d.get("recommendation")
    if (
        rec
        and mode == "MONEY"
        and not 0.6 * rec["amount"] <= d["amount"] <= 1.4 * rec["amount"]
    ):
        d["warnings"].append("協商價格偏離平臺參考，請確認服務與條件")
    if changed_scope:
        d["recommendation"] = None
    elif d.get("recommendation"):
        d["recommendation"]["scope_version"] = p["scope_version"] + 1
    s.execute(
        "UPDATE proposals SET data=?,mode=?,scope_version=scope_version+1,version=version+1 WHERE id=?",
        (dump(d), mode, p["id"]),
    )
    s.execute("DELETE FROM preferences WHERE proposal_id=?", (p["id"],))
    for agreement in s.all(
        "SELECT id FROM agreements WHERE proposal_id=? AND status='AWAITING_CONFIRMATION'",
        (p["id"],),
    ):
        s.execute(
            "UPDATE agreements SET status='CANCELLED',terms_version=terms_version+1,version=version+1 WHERE id=?",
            (agreement["id"],),
        )
    emit(s, user, "proposal", p["id"], "REVISED")
    return get(s, "proposals", p["id"])


def preference(s, user, p, body):
    participant(p, user)
    version(p, body["expected_version"])
    if body["scope_version"] != p["scope_version"]:
        fail("VERSION_CONFLICT", "接受條件適用範圍已更新")
    if p["mode"] == "BARTER":
        kind = "LOW" if user == p["provider_id"] else "HIGH"
    else:
        kind = "LOW" if user == p["data"]["payee_id"] else "HIGH"
    s.execute(
        "INSERT INTO preferences(proposal_id,user_id,scope_version,kind,value) VALUES(?,?,?,?,?) ON CONFLICT(proposal_id,user_id) DO UPDATE SET scope_version=excluded.scope_version,kind=excluded.kind,value=excluded.value",
        (p["id"], user, p["scope_version"], kind, body["value"]),
    )
    emit(s, user, "proposal", p["id"], "PREFERENCE_SET")
    return {"saved": True, "scope_version": p["scope_version"]}


def acceptance_bounds(s, p):
    rows = s.all(
        "SELECT * FROM preferences WHERE proposal_id=? AND scope_version=?",
        (p["id"], p["scope_version"]),
    )
    if len(rows) != 2:
        fail("WAITING_INPUT", "仍需另一方提交接受條件")
    low = next(r["value"] for r in rows if r["kind"] == "LOW")
    high = next(r["value"] for r in rows if r["kind"] == "HIGH")
    return low, high


def save_perspective(s, user, p, body):
    participant(p, user)
    version(p, body["expected_version"])
    if p["mode"] == "MONEY":
        fail("INVALID_INPUT", "價值分歧比較使用含雙向服務的提案", status=422)
    if body["scope_version"] != p["scope_version"]:
        fail("VERSION_CONFLICT", "服務範圍已變更，請重新表達本單價值")
    s.execute(
        "INSERT INTO perspectives(proposal_id,user_id,scope_version,received_value,reason,shared,updated) VALUES(?,?,?,?,?,?,?) ON CONFLICT(proposal_id,user_id) DO UPDATE SET scope_version=excluded.scope_version,received_value=excluded.received_value,reason=excluded.reason,shared=excluded.shared,updated=excluded.updated",
        (
            p["id"],
            user,
            p["scope_version"],
            body["received_value"],
            body["reason"],
            int(body["shared"]),
            now(),
        ),
    )
    emit(
        s, user, "proposal", p["id"], "PERSPECTIVE_UPDATED", {"shared": body["shared"]}
    )
    return perspectives(s, user, p)


def save_value_context(s, user, p, body):
    participant(p, user)
    version(p, body["expected_version"])
    if body["scope_version"] != p["scope_version"]:
        fail("VERSION_CONFLICT", "服務範圍已變更，請重新確認目標")
    if p["mode"] == "MONEY" and user == p["provider_id"]:
        fail("INVALID_INPUT", "本單此方接收款項，沒有接收服務目標", status=422)
    data = {
        "target_minutes": body["target_minutes"],
        "swings": {k: body[f"swing_{k}"] for k in SWINGS},
    }
    s.execute(
        "INSERT INTO value_contexts(proposal_id,user_id,scope_version,data) VALUES(?,?,?,?) ON CONFLICT(proposal_id,user_id) DO UPDATE SET scope_version=excluded.scope_version,data=excluded.data",
        (p["id"], user, p["scope_version"], dump(data)),
    )
    emit(s, user, "proposal", p["id"], "VALUE_CONTEXT_CONFIRMED")
    return perspectives(s, user, p)


def goal_plan(s, user, p, target):
    if user != p["provider_id"] or p["mode"] == "MONEY" or not p["data"].get("reverse"):
        return None
    if TEMPLATES[p["data"]["reverse"]["category"]]["basis"] != "DURATION" or any(
        "HYBRID" not in scope.get("accepted_modes", [])
        for scope in (p["data"]["scope"], p["data"]["reverse"])
    ):
        return None
    if s.one(
        "SELECT id FROM agreements WHERE proposal_id=? AND status!='CANCELLED'",
        (p["id"],),
    ):
        return None
    minutes = ceil(Fraction(target, POLICY["time_step"])) * POLICY["time_step"]
    if minutes >= p["data"]["reverse_minutes"]:
        return None
    candidate = p | {"mode": "HYBRID", "data": p["data"] | {"reverse_minutes": minutes}}
    try:
        rec = recommendation(s, candidate)
    except DomainError:
        return None
    return {
        "mode": "HYBRID",
        "reverse_minutes": minutes,
        "amount": rec["amount"],
        "payer_id": rec["payer_id"],
        "payee_id": rec["payee_id"],
        "rounds": rec["rounds"],
        "explanation": "目標時長達到後，額外時長不增加此模型的時長受益。減少反向服務，以本單參考價差建議補差；仍須雙方同意現金與全部條件。",
    }


def apply_value_plan(s, user, p, body):
    participant(p, user)
    version(p, body["expected_version"])
    if body["scope_version"] != p["scope_version"]:
        fail("VERSION_CONFLICT", "目標方案的適用範圍已更新")
    plan = goal_plan(s, user, p, body["target_minutes"])
    if not plan:
        fail(
            "NO_FEASIBLE_PLAN",
            "目前沒有可帶入的目標方案；已建立協議須保留原條款",
            status=422,
        )
    updated = revise(
        s,
        user,
        p,
        {
            "expected_version": p["version"],
            "mode": plan["mode"],
            "reverse_minutes": plan["reverse_minutes"],
            "amount": plan["amount"],
            "cash_payer_id": plan["payer_id"],
        },
    )
    updated = recommend(s, user, updated, updated["version"])
    save_value_context(
        s,
        user,
        updated,
        body
        | {
            "expected_version": updated["version"],
            "scope_version": updated["scope_version"],
        },
    )
    return updated


def perspectives(s, user, p):
    participant(p, user)
    context_row = unpack(
        s.one(
            "SELECT * FROM value_contexts WHERE proposal_id=? AND user_id=? AND scope_version=?",
            (p["id"], user, p["scope_version"]),
        )
    )
    context = context_row["data"] if context_row else None
    agreement = s.one(
        "SELECT * FROM agreements WHERE proposal_id=? AND status!='CANCELLED'",
        (p["id"],),
    )
    snapshot = unpack(agreement)["data"] if agreement else None
    estimates = []
    services = [(p["requester_id"], p["provider_id"], p["data"]["scope"], "main")]
    if p["mode"] != "MONEY" and p["data"].get("reverse"):
        services.append(
            (
                p["provider_id"],
                p["requester_id"],
                p["data"]["reverse"] | {"duration": p["data"]["reverse_minutes"]},
                "reverse",
            )
        )
    for recipient, service_provider, received, side in services:
        reference = (
            snapshot[f"{side}_estimate"]
            if snapshot
            else evaluate(s, service_provider, received)
        )
        valuation = reference.get("value_estimate")
        if not valuation:
            # Preserve old agreements' original estimates; never use today's evidence
            # to retrofit or reprice an existing agreement.
            valuation = {
                "algorithm_version": "legacy-snapshot",
                "status": "ESTIMATED"
                if reference["quality"] is not None and reference["eligible"]
                else "TEMPLATE_ONLY",
                "suggested_amount": reference["total_amount"]
                if reference["quality"] is not None and reference["eligible"]
                else None,
                "reference_amount": reference["total_amount"],
                "amount_range": None,
                "range_basis": "沿用原協議估值；此歷史快照未保存新版總價範圍",
                "duration_source": reference["estimate_source"],
                "formula": "沿用建立協議時的能力與投入快照",
                "is_demo": True,
            }
        target = (
            context["target_minutes"]
            if context and recipient == user
            else p["data"]["reverse" if side == "reverse" else "scope"].get(
                "duration", 60
            )
        )
        benefit = (
            recipient_benefit(
                reference,
                received["category"],
                target,
                context["swings"] if context and recipient == user else None,
                bool(context),
            )
            if recipient == user
            else None
        )
        estimates.append(
            {
                "user_id": recipient,
                "provider_id": service_provider,
                "received_title": received["title"],
                "platform_value": reference["total_amount"],
                "platform_minutes": reference["estimated_minutes"],
                "valuation": valuation,
                "benefit": benefit,
                "source": "AGREEMENT_SNAPSHOT" if snapshot else "CURRENT_EVIDENCE",
                "agreement_id": agreement["id"] if agreement else None,
            }
        )
    rows = s.all(
        "SELECT * FROM perspectives WHERE proposal_id=? AND scope_version=? AND (user_id=? OR shared=1)",
        (p["id"], p["scope_version"], user),
    )
    result = []
    for row in rows:
        estimate = next(x for x in estimates if x["user_id"] == row["user_id"])
        result.append(
            {
                **row,
                "received_title": estimate["received_title"],
                "platform_value": estimate["platform_value"],
                "platform_minutes": estimate["platform_minutes"],
                "difference": row["received_value"] - estimate["platform_value"],
                "reference_basis": estimate["valuation"]["duration_source"],
            }
        )
    return {
        "scope_version": p["scope_version"],
        "own_context": context,
        "goal_plan": goal_plan(
            s,
            user,
            p,
            context["target_minutes"]
            if context
            else p["data"].get("reverse", {}).get("duration", 60),
        )
        if p["data"].get("reverse")
        else None,
        "estimates": estimates,
        "views": result,
        "explanation": "平台先根據相關能力、工時與納入投入給出估值；個人可採用或調整。確認價值不自動改成交條件，私人接受底線始終不公開。",
    }


def validate_assisted_terms(s, p, value):
    if p["path"] != "ASSISTED":
        return
    low, high = acceptance_bounds(s, p)
    if not low <= value <= high:
        fail(
            "NO_FEASIBLE_PLAN",
            "此方案不在當前共同接受範圍內，請更新協商條件",
            status=422,
        )


def calculate(s, user, p, expected):
    participant(p, user)
    version(p, expected)
    low, high = acceptance_bounds(s, p)
    step = 15 if p["mode"] == "BARTER" else 100
    first = ((max(low, 1 if p["mode"] == "BARTER" else 0) + step - 1) // step) * step
    if first > high:
        fail("NO_FEASIBLE_PLAN", "雙方接受條件內沒有合法方案", status=422)
    # Inspect only integers nearest midpoint, not an unbounded enumeration.
    center = (low + high) // (2 * step)
    candidates = {first, (high // step) * step, center * step, (center + 1) * step}
    candidates = [x for x in candidates if low <= x <= high and x >= first]
    if p["mode"] == "BARTER":
        scope = p["data"]["scope"]
        rec = recommendation(s, p)
        window = int(
            (instant(scope["end"]) - instant(scope["start"])).total_seconds() / 60
        )
        limit = (
            POLICY["advanced_minutes"]
            if (
                capacity(s, p["provider_id"], scope["category"])["advanced"]
                and capacity(s, p["requester_id"], p["data"]["reverse"]["category"])[
                    "advanced"
                ]
            )
            else POLICY["advance_minutes"]
        )
        candidates = [
            x
            for x in range(first, min(high, 1440) + 1, step)
            if exchange_rounds(rec["main"], rec["reverse"], x, window, limit)
            is not None
        ]
    if not candidates:
        fail("NO_FEASIBLE_PLAN", "時段或數量限制內沒有方案", status=422)
    result = nash_candidates(candidates, low, high)
    return {
        "candidates": result,
        "unit": "分鐘" if p["mode"] == "BARTER" else "港仙",
        "scope_version": p["scope_version"],
        "rule_version": RULE_VERSION,
        "model": "NASH_LINEAR_RESERVATION_APPROXIMATION",
        "explanation": "以接受界限作線性偏好近似，最大化雙方增益乘積；零寬範圍只表示雙方可接受，不表示正增益。仍受時段與分輪限制，不代表已量測真實效用或客觀公平。",
    }


def select_candidate(s, user, p, body):
    options = calculate(s, user, p, body["expected_version"])
    if body["value"] not in options["candidates"]:
        fail("INVALID_INPUT", "此數值不是目前有效的協商候選", status=422)
    preferences = s.all(
        "SELECT * FROM preferences WHERE proposal_id=? AND scope_version=?",
        (p["id"], p["scope_version"]),
    )
    field = "reverse_minutes" if p["mode"] == "BARTER" else "amount"
    updated = revise(
        s, user, p, {"expected_version": body["expected_version"], field: body["value"]}
    )
    # The solver changes only its negotiated variable, so these same-service bounds remain valid.
    for preference in preferences:
        s.insert(
            "preferences",
            proposal_id=p["id"],
            user_id=preference["user_id"],
            scope_version=updated["scope_version"],
            kind=preference["kind"],
            value=preference["value"],
        )
    rec = recommendation(s, updated)
    rounds = rec["rounds"]
    if updated["mode"] == "BARTER":
        scope = updated["data"]["scope"]
        window = (instant(scope["end"]) - instant(scope["start"])).total_seconds() / 60
        limit = (
            POLICY["advanced_minutes"]
            if (
                capacity(s, updated["provider_id"], scope["category"])["advanced"]
                and capacity(
                    s, updated["requester_id"], updated["data"]["reverse"]["category"]
                )["advanced"]
            )
            else POLICY["advance_minutes"]
        )
        rounds = exchange_rounds(
            rec["main"], rec["reverse"], body["value"], window, limit
        )
    updated["data"]["selected_rounds"] = rounds
    s.execute(
        "UPDATE proposals SET data=? WHERE id=?", (dump(updated["data"]), p["id"])
    )
    emit(
        s,
        user,
        "proposal",
        p["id"],
        "CANDIDATE_SELECTED",
        {"scope_version": updated["scope_version"]},
    )
    return updated


def agreement_view(s, a, user):
    if (
        user not in (a["requester_id"], a["provider_id"])
        and not get(s, "users", user)["reviewer"]
    ):
        fail("UNAUTHORIZED_ACTION", "無權讀取此訂單", status=403)
    stages = [
        unpack(r)
        for r in s.all(
            "SELECT * FROM stages WHERE agreement_id=? ORDER BY round_no", (a["id"],)
        )
    ]
    for stage in stages:
        stage["obligations"] = [
            unpack(r)
            for r in s.all(
                "SELECT * FROM obligations WHERE stage_id=? ORDER BY seq",
                (stage["id"],),
            )
        ]
        for obligation in stage["obligations"]:
            obligation["time_entries"] = s.all(
                "SELECT * FROM time_entries WHERE obligation_id=?", (obligation["id"],)
            )
        stage["payment"] = s.one(
            "SELECT * FROM payment_intents WHERE stage_id=?", (stage["id"],)
        )
    return {
        **a,
        "stages": stages,
        "confirmed_by": [
            r["user_id"]
            for r in s.all(
                "SELECT * FROM consents WHERE target='AGREEMENT' AND target_id=? AND version=?",
                (a["id"], a["terms_version"]),
            )
        ],
        "closeouts": [
            {
                **unpack(r),
                "confirmed_by": [
                    c["user_id"]
                    for c in s.all(
                        "SELECT user_id FROM consents WHERE target='CLOSEOUT' AND target_id=? AND version=?",
                        (r["id"], r["version"]),
                    )
                ],
            }
            for r in s.all("SELECT * FROM closeouts WHERE agreement_id=?", (a["id"],))
        ],
        "disputes": [
            unpack(r)
            for r in s.all("SELECT * FROM disputes WHERE agreement_id=?", (a["id"],))
        ],
    }


def split(total, n):
    base = total // n
    return [base] * (n - 1) + [total - base * (n - 1)]


def create_agreement(s, user, p, body):
    participant(p, user)
    version(p, body["expected_version"])
    if s.one(
        "SELECT id FROM agreements WHERE proposal_id=? AND status!='CANCELLED'",
        (p["id"],),
    ):
        fail("INVALID_STATE", "提案已有協議")
    d = p["data"]
    scope = d["scope"]
    validate_assisted_terms(
        s, p, d["reverse_minutes"] if p["mode"] == "BARTER" else d["amount"]
    )
    if p["mode"] == "BARTER" and any(
        service
        and (service.get("material_amount", 0) or service.get("transport_amount", 0))
        for service in (scope, d["reverse"])
    ):
        fail("INVALID_INPUT", "含材料或交通現金費用時請使用互換補差", status=422)
    n = body.get("rounds", 2)
    listing = get(s, "listings", p["listing_id"])
    if listing["status"] != "OPEN":
        fail("LISTING_TAKEN", "此需求已被承接")
    if listing["version"] != d["listing_version"]:
        fail("RECOMMENDATION_STALE", "刊登內容已更新，請建立新的提案")
    if d.get("reverse"):
        reverse_listing = get(s, "listings", d["reverse"]["listing_id"])
        if reverse_listing["version"] != d["reverse"]["listing_version"]:
            fail("RECOMMENDATION_STALE", "反向服務已更新，請建立新提案")
    main = evaluate(s, p["provider_id"], scope)
    if not main["eligible"]:
        fail("POLICY_BLOCKED", "能力證據未滿足本單要求")
    rec = d.get("recommendation")
    if rec:
        fresh = recommendation(s, p)
        if (
            rec["scope_version"] != p["scope_version"]
            or rec["main"]["evidence_digest"] != fresh["main"]["evidence_digest"]
            or rec.get("reverse")
            and rec["reverse"]["evidence_digest"] != fresh["reverse"]["evidence_digest"]
        ):
            fail("RECOMMENDATION_STALE", "能力證據已更新，請重新計算建議")
    if p["mode"] == "MONEY" and d["payer_id"] != p["requester_id"]:
        fail("INVALID_INPUT", "付費模式由需求方付款", status=422)
    if p["mode"] == "BARTER" and d["amount"] != 0:
        fail("INVALID_INPUT", "純互換不能包含現金", status=422)
    if p["mode"] != "MONEY" and (not d["reverse"] or not d["reverse_minutes"]):
        fail("INVALID_INPUT", "互換必須有兩項服務", status=422)
    if main["execution_minutes"] < n:
        fail("INVALID_INPUT", "服務無法拆成這麼多階段", status=422)
    first = body.get("first_provider_id") or p["provider_id"]
    if first not in (p["requester_id"], p["provider_id"]):
        fail("INVALID_INPUT", "先行方必須是當事人", status=422)
    amounts = body.get("stage_amounts") or split(d["amount"], n)
    if (
        len(amounts) != n
        or any(type(v) != int or v < 0 for v in amounts)
        or sum(amounts) != d["amount"]
    ):
        fail("INVALID_INPUT", "階段金額合計必須等於總額", status=422)
    main_parts = split(main["execution_minutes"], n)
    reverse_parts = split(d["reverse_minutes"], n) if p["mode"] != "MONEY" else []
    reverse_eval = (
        evaluate(
            s, p["requester_id"], d["reverse"] | {"duration": d["reverse_minutes"]}
        )
        if reverse_parts
        else None
    )
    if reverse_eval and not reverse_eval["eligible"]:
        fail("POLICY_BLOCKED", "反向服務能力未達要求")
    if reverse_parts and (
        min(reverse_parts) <= 0
        or TEMPLATES[d["reverse"]["category"]]["basis"] != "DURATION"
    ):
        fail("INVALID_INPUT", "反向服務必須可按約定時長分輪", status=422)
    if reverse_parts:
        both_advanced = (
            capacity(s, p["provider_id"], scope["category"])["advanced"]
            and capacity(s, p["requester_id"], d["reverse"]["category"])["advanced"]
        )
        limit = (
            POLICY["advanced_minutes"] if both_advanced else POLICY["advance_minutes"]
        )
        parts = main_parts if first == p["provider_id"] else reverse_parts
        first_eval = main if first == p["provider_id"] else reverse_eval
        if (
            max(parts)
            + first_eval["preparation_minutes"]
            + first_eval["travel_minutes"]
            > limit
        ):
            fail(
                "POLICY_BLOCKED",
                "先行投入超過每輪限制，請增加真實可驗收輪次",
                {"limit_minutes": limit},
            )
    total_minutes = main["estimated_minutes"] + (
        d["reverse_minutes"]
        + reverse_eval["preparation_minutes"]
        + reverse_eval["travel_minutes"]
        if reverse_eval
        else 0
    )
    if (
        instant(scope["end"]) - instant(scope["start"])
    ).total_seconds() / 60 < total_minutes:
        fail("SCHEDULE_CONFLICT", "約定時段不足以容納服務投入")
    id = uid("agreement")
    snapshot = {
        **d,
        "rule_version": RULE_VERSION,
        "scope_version": p["scope_version"],
        "rounds": n,
        "first_provider_id": first,
        "response_due": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
        "cancel_rule": "已確認貢獻保留；原回報義務完成或雙方明確豁免後才能結清",
        "currency": "HKD",
        "simulated": True,
        "main_estimate": main,
        "reverse_estimate": reverse_eval,
    }
    s.insert(
        "agreements",
        id=id,
        proposal_id=p["id"],
        listing_id=p["listing_id"],
        requester_id=p["requester_id"],
        provider_id=p["provider_id"],
        mode=p["mode"],
        status="AWAITING_CONFIRMATION",
        data=dump(snapshot),
    )
    for i in range(n):
        sid = uid("stage")
        s.insert("stages", id=sid, agreement_id=id, round_no=i + 1, status="LOCKED")
        services = [(p["provider_id"], p["requester_id"], scope, main_parts[i], main)]
        if reverse_parts:
            services.append(
                (
                    p["requester_id"],
                    p["provider_id"],
                    d["reverse"],
                    reverse_parts[i],
                    reverse_eval,
                )
            )
        if reverse_parts and first == p["requester_id"]:
            services.reverse()
        for seq, (provider, recipient, service, minutes, estimate) in enumerate(
            services
        ):
            ob = {
                "service": service,
                "minutes": minutes,
                "preparation": estimate["preparation_minutes"] if i == 0 else 0,
                "travel": estimate["travel_minutes"] if i == 0 else 0,
                "acceptance": service.get("delivery_standard")
                or TEMPLATES[service["category"]]["deliverable"],
                "stage_deliverable": (
                    "樣本工作表整理" if i == 0 else "其餘工作表與修改說明"
                )
                if service["category"] == "spreadsheet" and n == 2
                else f"第 {i + 1} 輪：{minutes} 分鐘服務",
                "due_at": scope["end"],
                "evidence": None,
            }
            s.insert(
                "obligations",
                id=uid("obligation"),
                agreement_id=id,
                stage_id=sid,
                provider_id=provider,
                recipient_id=recipient,
                seq=seq,
                status="LOCKED",
                data=dump(ob),
            )
        if p["mode"] != "BARTER":
            s.insert(
                "payment_intents",
                id=uid("payment"),
                agreement_id=id,
                stage_id=sid,
                payer_id=d["payer_id"],
                payee_id=d["payee_id"],
                amount=amounts[i],
            )
    emit(s, user, "agreement", id, "DRAFT_CREATED")
    return get(s, "agreements", id)


def activate_stage(s, a, stage):
    s.execute("UPDATE stages SET status='ACTIVE' WHERE id=?", (stage["id"],))
    if a["mode"] == "BARTER":
        first = s.one(
            "SELECT id FROM obligations WHERE stage_id=? ORDER BY seq LIMIT 1",
            (stage["id"],),
        )
        s.execute(
            "UPDATE obligations SET status='READY',version=version+1 WHERE id=?",
            (first["id"],),
        )


def confirm(s, user, a, body):
    participant(a, user)
    version(a, body["expected_version"])
    if body["terms_version"] != a["terms_version"]:
        fail("VERSION_CONFLICT", "確認的條款版本已失效")
    if a["status"] != "AWAITING_CONFIRMATION":
        fail("INVALID_STATE", "訂單不在待確認狀態")
    p = get(s, "proposals", a["proposal_id"])
    if p["scope_version"] != a["data"]["scope_version"]:
        fail("VERSION_CONFLICT", "提案範圍已更新")
    validate_assisted_terms(
        s,
        p,
        a["data"]["reverse_minutes"] if a["mode"] == "BARTER" else a["data"]["amount"],
    )
    if a["data"]["rule_version"] != RULE_VERSION:
        fail("VERSION_CONFLICT", "規則版本已更新")
    rec = a["data"].get("recommendation")
    if rec:
        fresh = recommendation(s, p)
        if (
            rec["main"]["evidence_digest"] != fresh["main"]["evidence_digest"]
            or rec.get("reverse")
            and rec["reverse"]["evidence_digest"] != fresh["reverse"]["evidence_digest"]
        ):
            fail("RECOMMENDATION_STALE", "能力證據已更新，請重新生成協議")
    s.execute(
        "INSERT OR IGNORE INTO consents(target,target_id,user_id,version,created) VALUES('AGREEMENT',?,?,?,?)",
        (a["id"], user, a["terms_version"], now()),
    )
    count = s.one(
        "SELECT COUNT(*) n FROM consents WHERE target='AGREEMENT' AND target_id=? AND version=?",
        (a["id"], a["terms_version"]),
    )["n"]
    if count == 2:
        listing = get(s, "listings", a["listing_id"])
        if listing["status"] != "OPEN":
            fail("LISTING_TAKEN", "此需求已被承接")
        scope = a["data"]["scope"]
        if listing["version"] != a["data"]["listing_version"]:
            fail("RECOMMENDATION_STALE", "需求內容已更新，請重新建立提案")
        if not evaluate(s, a["provider_id"], scope)["eligible"]:
            fail("POLICY_BLOCKED", "目前能力未符合本單要求")
        if a["data"]["reverse"]:
            reverse = a["data"]["reverse"]
            reverse_listing = get(s, "listings", reverse["listing_id"])
            if reverse_listing["version"] != reverse["listing_version"]:
                fail("RECOMMENDATION_STALE", "反向服務已更新")
            if not evaluate(s, a["requester_id"], reverse)["eligible"]:
                fail("POLICY_BLOCKED", "反向服務能力未符合要求")
            rd = reverse_listing["data"]
            if (
                reverse_listing["status"] != "OPEN"
                or instant(rd["start"]) > instant(scope["start"])
                or instant(rd["end"]) < instant(scope["end"])
                or rd["service_mode"] != scope["service_mode"]
                or scope["service_mode"] == "OFFLINE"
                and rd["location"] != scope["location"]
            ):
                fail("SCHEDULE_CONFLICT", "反向服務可用時段或方式不符")
        for actor, category in [
            (a["provider_id"], scope["category"]),
            (
                a["requester_id"],
                a["data"]["reverse"]["category"]
                if a["data"]["reverse"]
                else scope["category"],
            ),
        ]:
            role = (
                "REQUESTER"
                if actor == a["requester_id"] and a["mode"] == "MONEY"
                else "PROVIDER"
            )
            policy = capacity(s, actor, category, role)
            if policy["blocked"]:
                fail("POLICY_BLOCKED", "存在尚未補救的已確認違約")
            if policy["in_flight"] >= policy["limit"]:
                fail("CAPACITY_EXCEEDED", "當事人的在途容量已滿")
            if not schedule_free(s, actor, scope["start"], scope["end"]):
                fail("SCHEDULE_CONFLICT", "約定時段已被佔用")
            # Provider availability is an explicit offer declaration, not an inferred promise.
            if actor == a["provider_id"]:
                offers = [
                    unpack(r)
                    for r in s.all(
                        "SELECT * FROM listings WHERE owner_id=? AND category=? AND kind='OFFER' AND status='OPEN'",
                        (actor, category),
                    )
                ]
                if not any(
                    instant(o["data"]["start"]) <= instant(scope["start"])
                    and instant(o["data"]["end"]) >= instant(scope["end"])
                    and o["data"]["service_mode"] == scope["service_mode"]
                    and (
                        scope["service_mode"] == "ONLINE"
                        or o["data"]["location"] == scope["location"]
                    )
                    for o in offers
                ):
                    fail("SCHEDULE_CONFLICT", "供給方未聲明可用的服務時段")
            s.insert(
                "bookings",
                id=uid("booking"),
                agreement_id=a["id"],
                user_id=actor,
                start=scope["start"],
                end=scope["end"],
            )
        if listing["kind"] == "REQUEST":
            s.execute(
                "UPDATE listings SET status='TAKEN',version=version+1 WHERE id=? AND status='OPEN'",
                (listing["id"],),
            )
        s.execute("UPDATE agreements SET status='ACTIVE' WHERE id=?", (a["id"],))
        stage = s.one(
            "SELECT * FROM stages WHERE agreement_id=? ORDER BY round_no LIMIT 1",
            (a["id"],),
        )
        activate_stage(s, a, stage)
    s.execute("UPDATE agreements SET version=version+1 WHERE id=?", (a["id"],))
    emit(
        s,
        user,
        "agreement",
        a["id"],
        "CONFIRMED",
        {"terms_version": a["terms_version"], "activated": count == 2},
    )
    return get(s, "agreements", a["id"])


def money_action(s, user, payment, action):
    amount = (
        payment["amount"]
        if action == "RESERVE"
        else payment["reserved"] - payment["released"] - payment["refunded"]
    )
    if action == "RESERVE" and payment["state"] != "NEW":
        return
    if action != "RESERVE" and payment["state"] != "RESERVED":
        return
    payer = payment["payer_id"]
    payee = payment["payee_id"]
    escrow = "reserved:" + payment["id"]
    if action == "RESERVE":
        account = s.one("SELECT * FROM accounts WHERE user_id=?", (payer,))
        if account["available"] < amount:
            fail("INSUFFICIENT_MOCK_BALANCE", "模擬餘額不足")
        s.execute(
            "UPDATE accounts SET available=available-?,reserved=reserved+? WHERE user_id=?",
            (amount, amount, payer),
        )
        s.execute(
            "UPDATE payment_intents SET reserved=?,state='RESERVED' WHERE id=?",
            (amount, payment["id"]),
        )
        source, destination = "available:" + payer, escrow
    else:
        s.execute(
            "UPDATE accounts SET reserved=reserved-? WHERE user_id=?", (amount, payer)
        )
        target = payee if action == "RELEASE" else payer
        s.execute(
            "UPDATE accounts SET available=available+? WHERE user_id=?",
            (amount, target),
        )
        column = "released" if action == "RELEASE" else "refunded"
        s.execute(
            f"UPDATE payment_intents SET {column}={column}+?,state=? WHERE id=?",
            (amount, "RELEASED" if action == "RELEASE" else "REFUNDED", payment["id"]),
        )
        source, destination = escrow, "available:" + target
    s.insert(
        "ledger",
        id=uid("ledger"),
        payment_id=payment["id"],
        action=action,
        source=source,
        destination=destination,
        amount=amount,
        created=now(),
        business_key=payment["id"] + ":" + action,
    )
    emit(
        s, user, "payment", payment["id"], action, {"amount": amount, "simulated": True}
    )


def fund(s, user, stage, expected):
    a = get(s, "agreements", stage["agreement_id"])
    participant(a, user)
    version(a, expected)
    if a["status"] != "ACTIVE" or stage["status"] != "ACTIVE":
        fail("INVALID_STATE", "此階段尚未開放或已暫停")
    payment = s.one("SELECT * FROM payment_intents WHERE stage_id=?", (stage["id"],))
    if not payment or user != payment["payer_id"]:
        fail("UNAUTHORIZED_ACTION", "只有本階段付款方可預留", status=403)
    money_action(s, user, payment, "RESERVE")
    first = s.one(
        "SELECT * FROM obligations WHERE stage_id=? ORDER BY seq LIMIT 1",
        (stage["id"],),
    )
    if first["status"] == "LOCKED":
        s.execute(
            "UPDATE obligations SET status='READY',version=version+1 WHERE id=?",
            (first["id"],),
        )
    s.execute("UPDATE agreements SET version=version+1 WHERE id=?", (a["id"],))
    return get(s, "agreements", a["id"])


def allow_fulfillment(s, a, ob):
    if a["status"] == "ACTIVE":
        return
    if a["status"] == "CLOSING":
        for raw in s.all(
            "SELECT * FROM closeouts WHERE agreement_id=? AND status='EXECUTING'",
            (a["id"],),
        ):
            if any(
                x["obligation_id"] == ob["id"] and x["action"] == "CONTINUE"
                for x in unpack(raw)["data"]["obligations"]
            ):
                return
    fail("INVALID_STATE", "訂單已暫停；需要復核或雙方確認補做方案")


def submit(s, user, ob, body):
    version(ob, body["expected_version"])
    if user != ob["provider_id"]:
        fail("UNAUTHORIZED_ACTION", "只有提供者可提交交付", status=403)
    a = get(s, "agreements", ob["agreement_id"])
    allow_fulfillment(s, a, ob)
    if ob["status"] != "READY":
        fail("INVALID_STATE", "此服務尚未開放或已提交")
    data = ob["data"]
    service = data["service"]
    if (
        TEMPLATES[service["category"]]["basis"] == "DURATION"
        and body["execution_minutes"] != data["minutes"]
    ):
        fail("INVALID_INPUT", "時長型交付必須符合約定時長；變更需重新協商", status=422)
    if (
        body.get("preparation_minutes", 0)
        and not service.get("include_preparation")
        or body.get("travel_minutes", 0)
        and not service.get("include_travel")
    ):
        fail("INVALID_INPUT", "未約定的準備或差旅不能作為認可投入", status=422)
    if (
        body.get("preparation_minutes", 0) > data["preparation"]
        or body.get("travel_minutes", 0) > data["travel"]
    ):
        fail("INVALID_INPUT", "額外投入需要事先協商", status=422)
    data["evidence"] = body["evidence"]
    data.setdefault("submissions", []).append(
        {
            "evidence": body["evidence"],
            "execution_minutes": body["execution_minutes"],
            "preparation_minutes": body.get("preparation_minutes", 0),
            "travel_minutes": body.get("travel_minutes", 0),
            "at": now(),
        }
    )
    data["submitted_at"] = now()
    s.execute(
        "UPDATE obligations SET data=?,status='SUBMITTED',version=version+1 WHERE id=?",
        (dump(data), ob["id"]),
    )
    for component, minutes in [
        ("EXECUTION", body["execution_minutes"]),
        ("PREPARATION", body.get("preparation_minutes", 0)),
        ("TRAVEL", body.get("travel_minutes", 0)),
    ]:
        s.execute(
            "INSERT INTO time_entries(id,obligation_id,provider_id,component,minutes,status,created) VALUES(?,?,?,?,?,?,?) ON CONFLICT(obligation_id,component) DO UPDATE SET minutes=excluded.minutes,status=excluded.status,created=excluded.created",
            (uid("time"), ob["id"], user, component, minutes, "SUBMITTED", now()),
        )
    s.execute("UPDATE agreements SET version=version+1 WHERE id=?", (a["id"],))
    emit(s, user, "obligation", ob["id"], "SUBMITTED")
    return get(s, "obligations", ob["id"])


def quality(scores):
    return round(
        sum(
            w * scores[k] / 100
            for w, k in zip(
                POLICY["quality_weights"],
                ("correctness", "completeness", "independence"),
            )
        ),
        2,
    )


def finish_closeout(s, a):
    pending = s.one(
        "SELECT COUNT(*) n FROM obligations WHERE agreement_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
        (a["id"],),
    )["n"]
    funds = s.one(
        "SELECT COALESCE(SUM(reserved-released-refunded),0) n FROM payment_intents WHERE agreement_id=?",
        (a["id"],),
    )["n"]
    disputes = s.one(
        "SELECT COUNT(*) n FROM disputes WHERE agreement_id=? AND status='OPEN'",
        (a["id"],),
    )["n"]
    if not pending and not funds and not disputes:
        s.execute(
            "UPDATE agreements SET status='CANCELLED',version=version+1 WHERE id=?",
            (a["id"],),
        )
        s.execute(
            "UPDATE closeouts SET status='COMPLETED' WHERE agreement_id=? AND status='EXECUTING'",
            (a["id"],),
        )
        s.execute("DELETE FROM bookings WHERE agreement_id=?", (a["id"],))
        emit(s, a["requester_id"], "agreement", a["id"], "CLOSEOUT_COMPLETED")


def accept_internal(s, user, ob, scores, note=""):
    a = get(s, "agreements", ob["agreement_id"])
    s.execute(
        "UPDATE obligations SET status='ACCEPTED',version=version+1 WHERE id=?",
        (ob["id"],),
    )
    s.execute(
        "UPDATE time_entries SET status='CONFIRMED' WHERE obligation_id=?", (ob["id"],)
    )
    data = ob["data"]
    data["assessment"] = {"scores": scores, "note": note}
    s.execute("UPDATE obligations SET data=? WHERE id=?", (dump(data), ob["id"]))
    total = s.one(
        "SELECT COALESCE(SUM(minutes),0) n FROM time_entries WHERE obligation_id=? AND status='CONFIRMED' AND component='EXECUTION'",
        (ob["id"],),
    )["n"]
    # Historical effort is aggregated by whole completed service, never counted per stage.
    stage = get(s, "stages", ob["stage_id"])
    remaining = s.one(
        "SELECT COUNT(*) n FROM obligations WHERE stage_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
        (stage["id"],),
    )["n"]
    if not remaining:
        if a["status"] == "ACTIVE":
            payment = s.one(
                "SELECT * FROM payment_intents WHERE stage_id=?", (stage["id"],)
            )
            if payment:
                if payment["state"] == "NEW":
                    fail("INVALID_STATE", "未預留的階段不能釋放資金")
                money_action(s, user, payment, "RELEASE")
        s.execute("UPDATE stages SET status='COMPLETED' WHERE id=?", (stage["id"],))
        if a["status"] == "ACTIVE":
            next_stage = s.one(
                "SELECT * FROM stages WHERE agreement_id=? AND round_no>? ORDER BY round_no LIMIT 1",
                (a["id"], stage["round_no"]),
            )
            if next_stage:
                activate_stage(s, a, next_stage)
            else:
                s.execute(
                    "UPDATE agreements SET status='COMPLETED' WHERE id=?", (a["id"],)
                )
                s.execute("DELETE FROM bookings WHERE agreement_id=?", (a["id"],))
                record_history(s, a)
    elif a["status"] in ("ACTIVE", "CLOSING"):
        next_ob = s.one(
            "SELECT id FROM obligations WHERE stage_id=? AND status='LOCKED' ORDER BY seq LIMIT 1",
            (stage["id"],),
        )
        if next_ob:
            if a["status"] == "ACTIVE":
                s.execute(
                    "UPDATE obligations SET status='READY',version=version+1 WHERE id=?",
                    (next_ob["id"],),
                )
            else:
                target = get(s, "obligations", next_ob["id"])
                try:
                    allow_fulfillment(s, a, target)
                except DomainError:
                    pass
                else:
                    s.execute(
                        "UPDATE obligations SET status='READY',version=version+1 WHERE id=?",
                        (next_ob["id"],),
                    )
    s.execute("UPDATE agreements SET version=version+1 WHERE id=?", (a["id"],))
    if a["status"] == "CLOSING":
        # Confirmed closeout actions execute only when their original obligations are settled.
        execute_closeout_payments(s, user, a)
        finish_closeout(s, a)
    emit(
        s,
        user,
        "obligation",
        ob["id"],
        "ACCEPTED",
        {"confirmed_execution_minutes": total},
    )


def record_history(s, a):
    obligations = [
        unpack(r)
        for r in s.all("SELECT * FROM obligations WHERE agreement_id=?", (a["id"],))
    ]
    for provider in {r["provider_id"] for r in obligations}:
        mine = [r for r in obligations if r["provider_id"] == provider]
        service = mine[0]["data"]["service"]
        peer = mine[0]["recipient_id"]
        scores = [quality(r["data"]["assessment"]["scores"]) for r in mine]
        minutes = sum(
            s.one(
                "SELECT COALESCE(SUM(minutes),0) n FROM time_entries WHERE obligation_id=? AND component='EXECUTION' AND status='CONFIRMED'",
                (r["id"],),
            )["n"]
            for r in mine
        )
        payload = {
            "title": service["title"],
            "difficulty": service.get("difficulty", "basic"),
            "workload": service.get("workload", "medium"),
            "skills": service.get("required_skills", [])
            + service.get("preferred_skills", []),
            "confirmed_minutes": minutes,
            "source": "本平臺整單完成與結構化驗收",
            "basis": "各階段成果驗收",
            "is_demo": True,
        }
        s.insert(
            "evidence",
            id=uid("history"),
            owner_id=provider,
            category=service["category"],
            kind="HISTORY",
            peer_id=peer,
            agreement_id=a["id"],
            data=dump(payload),
            status="APPROVED",
            quality=float(median(scores)),
            created=now(),
        )


def accept(s, user, ob, body):
    version(ob, body["expected_version"])
    if user != ob["recipient_id"]:
        fail("UNAUTHORIZED_ACTION", "只有接收者可驗收，不能自驗收", status=403)
    a = get(s, "agreements", ob["agreement_id"])
    allow_fulfillment(s, a, ob)
    if ob["status"] != "SUBMITTED":
        fail("INVALID_STATE", "服務尚未提交或已完成")
    accept_internal(s, user, ob, body["scores"], body.get("note", ""))
    return get(s, "agreements", a["id"])


def withdraw(s, user, a, body):
    participant(a, user)
    version(a, body["expected_version"])
    if a["status"] not in ("ACTIVE", "DISPUTED", "UNRESOLVED"):
        fail("INVALID_STATE", "此訂單不能申請退出")
    data = a["data"]
    data["withdrawal"] = {"by": user, "reason": body["reason"], "at": now()}
    s.execute(
        "UPDATE agreements SET status='CLOSING',data=?,version=version+1 WHERE id=?",
        (dump(data), a["id"]),
    )
    emit(s, user, "agreement", a["id"], "WITHDRAWAL_REQUESTED")
    return get(s, "agreements", a["id"])


def create_dispute(s, user, a, body):
    participant(a, user)
    version(a, body["expected_version"])
    if a["status"] not in ("ACTIVE", "CLOSING", "UNRESOLVED"):
        fail("INVALID_STATE", "此訂單目前不能新增爭議")
    if body.get("obligation_id"):
        ob = get(s, "obligations", body["obligation_id"])
        if ob["agreement_id"] != a["id"]:
            fail("INVALID_INPUT", "義務不屬於此訂單", status=422)
        if ob["status"] == "SUBMITTED":
            s.execute(
                "UPDATE obligations SET status='CONTESTED',version=version+1 WHERE id=?",
                (ob["id"],),
            )
    id = uid("dispute")
    s.insert(
        "disputes",
        id=id,
        agreement_id=a["id"],
        author_id=user,
        obligation_id=body.get("obligation_id"),
        status="OPEN",
        data=dump(
            {"reason": body["reason"], "previous_status": a["status"], "review": None}
        ),
    )
    s.execute(
        "UPDATE agreements SET status='DISPUTED',version=version+1 WHERE id=?",
        (a["id"],),
    )
    emit(s, user, "dispute", id, "OPENED")
    return get(s, "disputes", id)


def resume_accepted_stages(s, a, user):
    """Finish accepted stages held by a dispute, only after all disputes are resolved."""
    if a["status"] != "ACTIVE":
        return
    for stage in s.all(
        "SELECT * FROM stages WHERE agreement_id=? AND status='COMPLETED' ORDER BY round_no",
        (a["id"],),
    ):
        pending = s.one(
            "SELECT COUNT(*) n FROM obligations WHERE stage_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
            (stage["id"],),
        )["n"]
        if pending:
            continue
        payment = s.one(
            "SELECT * FROM payment_intents WHERE stage_id=?", (stage["id"],)
        )
        if payment:
            if payment["state"] == "NEW":
                fail("INVALID_STATE", "未預留的階段不能釋放資金")
            money_action(s, user, payment, "RELEASE")
        next_stage = s.one(
            "SELECT * FROM stages WHERE agreement_id=? AND round_no>? ORDER BY round_no LIMIT 1",
            (a["id"], stage["round_no"]),
        )
        if next_stage:
            if next_stage["status"] == "LOCKED":
                activate_stage(s, a, next_stage)
        else:
            s.execute("UPDATE agreements SET status='COMPLETED' WHERE id=?", (a["id"],))
            s.execute("DELETE FROM bookings WHERE agreement_id=?", (a["id"],))
            record_history(s, a)


def review_dispute(s, user, d, body):
    reviewer(s, user)
    version(d, body["expected_version"])
    if d["status"] != "OPEN":
        fail("INVALID_STATE", "爭議已復核")
    a = get(s, "agreements", d["agreement_id"])
    ob = get(s, "obligations", d["obligation_id"]) if d["obligation_id"] else None
    outcome = body["outcome"]
    data = d["data"]
    data["review"] = {
        "by": user,
        "basis": body["basis"],
        "outcome": outcome,
        "confirmed_breach_user_id": body.get("confirmed_breach_user_id"),
        "at": now(),
    }
    if body.get("confirmed_breach_user_id"):
        if body["confirmed_breach_user_id"] not in (
            a["requester_id"],
            a["provider_id"],
        ):
            fail("INVALID_INPUT", "違約方不屬於此訂單", status=422)
        s.execute(
            "UPDATE users SET blocked=1 WHERE id=?", (body["confirmed_breach_user_id"],)
        )
    s.execute(
        "UPDATE disputes SET data=?,status=?,version=version+1 WHERE id=?",
        (dump(data), "OPEN" if outcome == "UNRESOLVED" else "REVIEWED", d["id"]),
    )
    other_open = s.one(
        "SELECT COUNT(*) n FROM disputes WHERE agreement_id=? AND id!=? AND status='OPEN'",
        (a["id"], d["id"]),
    )["n"]
    status = (
        "UNRESOLVED"
        if outcome == "UNRESOLVED"
        else "DISPUTED"
        if other_open
        else "CLOSING"
        if outcome == "CLOSEOUT"
        or a["data"].get("withdrawal")
        or a["status"] == "CLOSING"
        or data["previous_status"] == "CLOSING"
        else "ACTIVE"
    )
    s.execute(
        "UPDATE agreements SET status=?,version=version+1 WHERE id=?", (status, a["id"])
    )
    if outcome == "ACCEPT":
        if (
            not ob
            or ob["status"] not in ("CONTESTED", "SUBMITTED")
            or not body.get("scores")
        ):
            fail("INVALID_INPUT", "需要待驗收義務與評分", status=422)
        accept_internal(s, user, ob, body["scores"], body["basis"])
    elif outcome == "REDO":
        if not ob or ob["status"] not in ("CONTESTED", "SUBMITTED"):
            fail("INVALID_INPUT", "需要可重做的義務", status=422)
        s.execute(
            "UPDATE obligations SET status='READY',version=version+1 WHERE id=?",
            (ob["id"],),
        )
        s.execute(
            "UPDATE time_entries SET status='CONTESTED' WHERE obligation_id=?",
            (ob["id"],),
        )
    elif outcome == "RESUME" and ob and ob["status"] == "CONTESTED":
        s.execute(
            "UPDATE obligations SET status='SUBMITTED',version=version+1 WHERE id=?",
            (ob["id"],),
        )
    resume_accepted_stages(s, get(s, "agreements", a["id"]), user)
    emit(s, user, "dispute", d["id"], "REVIEWED", {"outcome": outcome})
    return get(s, "disputes", d["id"])


def create_closeout(s, user, a, body):
    participant(a, user)
    version(a, body["expected_version"])
    if a["status"] not in ("CLOSING", "UNRESOLVED"):
        fail("INVALID_STATE", "先申請退出或處理爭議")
    if s.one(
        "SELECT id FROM disputes WHERE agreement_id=? AND status='OPEN'", (a["id"],)
    ):
        fail("INVALID_STATE", "需要先復核未解決爭議")
    remaining = s.all(
        "SELECT id,status FROM obligations WHERE agreement_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
        (a["id"],),
    )
    ids = {r["id"] for r in remaining}
    actions = body["obligations"]
    if len(actions) != len(ids) or {x["obligation_id"] for x in actions} != ids:
        fail("INVALID_INPUT", "結清方案必須列出每項尚未解決的原義務", status=422)
    if any(r["status"] in ("SUBMITTED", "CONTESTED") for r in remaining):
        fail("INVALID_STATE", "已提交成果須先驗收或復核，不能直接豁免")
    payments = s.all(
        "SELECT * FROM payment_intents WHERE agreement_id=? AND reserved>released+refunded",
        (a["id"],),
    )
    if len(body.get("payments", [])) != len(payments) or {
        x["payment_id"] for x in body.get("payments", [])
    } != {x["id"] for x in payments}:
        fail("INVALID_INPUT", "需要明確處置每筆尚未結清的模擬預留", status=422)
    old = s.all(
        "SELECT id FROM closeouts WHERE agreement_id=? AND status='AWAITING_CONFIRMATION'",
        (a["id"],),
    )
    for r in old:
        s.execute("UPDATE closeouts SET status='SUPERSEDED' WHERE id=?", (r["id"],))
    if s.one(
        "SELECT id FROM closeouts WHERE agreement_id=? AND status='EXECUTING'",
        (a["id"],),
    ):
        fail("INVALID_STATE", "已有執行中的結清方案")
    id = uid("closeout")
    data = {
        "obligations": actions,
        "payments": body.get("payments", []),
        "reason": body["reason"],
        "agreement_version": a["version"],
        "created_by": user,
    }
    # If continuing a paid obligation, funds must remain reserved until its resolution.
    for item in data["payments"]:
        payment = get(s, "payment_intents", item["payment_id"])
        stage_ids = {
            r["id"]
            for r in s.all(
                "SELECT id FROM obligations WHERE stage_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
                (payment["stage_id"],),
            )
        }
        if item["action"] != "HOLD" and any(
            x["obligation_id"] in stage_ids and x["action"] == "CONTINUE"
            for x in actions
        ):
            fail("INVALID_INPUT", "仍需補做的服務，其相關預留必須保持", status=422)
    s.insert(
        "closeouts",
        id=id,
        agreement_id=a["id"],
        status="AWAITING_CONFIRMATION",
        data=dump(data),
    )
    emit(s, user, "closeout", id, "CREATED")
    return get(s, "closeouts", id)


def execute_closeout_payments(s, user, a):
    for raw in s.all(
        "SELECT * FROM closeouts WHERE agreement_id=? AND status='EXECUTING'",
        (a["id"],),
    ):
        close = unpack(raw)
        for action in close["data"]["payments"]:
            payment = get(s, "payment_intents", action["payment_id"])
            unfinished = s.one(
                "SELECT COUNT(*) n FROM obligations WHERE stage_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
                (payment["stage_id"],),
            )["n"]
            if unfinished:
                continue
            if action["action"] == "HOLD":
                accepted = s.one(
                    "SELECT COUNT(*) n FROM obligations WHERE stage_id=? AND status='ACCEPTED'",
                    (payment["stage_id"],),
                )["n"]
                money_action(s, user, payment, "RELEASE" if accepted else "REFUND")
            else:
                money_action(s, user, payment, action["action"])


def confirm_closeout(s, user, c, body):
    a = get(s, "agreements", c["agreement_id"])
    participant(a, user)
    version(c, body["expected_version"])
    if (
        body["agreement_version"] != a["version"]
        or c["data"]["agreement_version"] != a["version"]
    ):
        fail(
            "VERSION_CONFLICT",
            "訂單已更新，需要新的結清方案",
            {"current_version": a["version"]},
        )
    if c["status"] != "AWAITING_CONFIRMATION":
        fail("INVALID_STATE", "結清方案已確認或被替代")
    s.execute(
        "INSERT OR IGNORE INTO consents(target,target_id,user_id,version,created) VALUES('CLOSEOUT',?,?,?,?)",
        (c["id"], user, c["version"], now()),
    )
    count = s.one(
        "SELECT COUNT(*) n FROM consents WHERE target='CLOSEOUT' AND target_id=? AND version=?",
        (c["id"], c["version"]),
    )["n"]
    if count == 2:
        if a["status"] not in ("CLOSING", "UNRESOLVED"):
            fail("INVALID_STATE", "訂單不在結清狀態")
        s.execute("UPDATE closeouts SET status='EXECUTING' WHERE id=?", (c["id"],))
        s.execute("UPDATE agreements SET status='CLOSING' WHERE id=?", (a["id"],))
        for action in c["data"]["obligations"]:
            ob = get(s, "obligations", action["obligation_id"])
            if ob["status"] in ("ACCEPTED", "WAIVED"):
                fail("VERSION_CONFLICT", "原義務已改變")
            if action["action"] == "WAIVE":
                s.execute(
                    "UPDATE obligations SET status='WAIVED',version=version+1 WHERE id=?",
                    (ob["id"],),
                )
            else:
                # Keep same-stage sequential dependency even during agreed remediation.
                predecessors = s.one(
                    "SELECT COUNT(*) n FROM obligations WHERE stage_id=? AND seq<? AND status NOT IN ('ACCEPTED','WAIVED')",
                    (ob["stage_id"], ob["seq"]),
                )["n"]
                status = "LOCKED" if predecessors else "READY"
                payment = s.one(
                    "SELECT * FROM payment_intents WHERE stage_id=?", (ob["stage_id"],)
                )
                if payment and payment["state"] == "NEW":
                    fail(
                        "INVALID_INPUT",
                        "尚未預留的後續付費階段不可補做，請取消或另建新單",
                        status=422,
                    )
                s.execute(
                    "UPDATE obligations SET status=?,version=version+1 WHERE id=?",
                    (status, ob["id"]),
                )
        execute_closeout_payments(s, user, a)
        finish_closeout(s, a)
    emit(s, user, "closeout", c["id"], "CONFIRMED", {"executing": count == 2})
    return get(s, "agreements", a["id"])


def time_summary(s, user):
    rows = s.all(
        "SELECT o.*,t.component,t.minutes FROM time_entries t JOIN obligations o ON o.id=t.obligation_id WHERE t.status='CONFIRMED' AND (o.provider_id=? OR o.recipient_id=?)",
        (user, user),
    )
    provided = []
    received = []
    for raw in rows:
        r = unpack(raw)
        service = r["data"]["service"]
        record = {
            "obligation_id": r["id"],
            "agreement_id": r["agreement_id"],
            "category": service["category"],
            "title": service["title"],
            "component": r["component"],
            "minutes": r["minutes"],
        }
        (provided if r["provider_id"] == user else received).append(record)
    pending = [
        unpack(r)
        for r in s.all(
            "SELECT o.* FROM obligations o JOIN agreements a ON a.id=o.agreement_id WHERE (o.provider_id=? OR o.recipient_id=?) AND o.status NOT IN ('ACCEPTED','WAIVED') AND a.status IN ('ACTIVE','CLOSING','DISPUTED','UNRESOLVED')",
            (user, user),
        )
    ]
    return {
        "provided_minutes": sum(r["minutes"] for r in provided),
        "received_service_minutes": sum(
            r["minutes"] for r in received if r["component"] == "EXECUTION"
        ),
        "provided": provided,
        "received": received,
        "pending": pending,
        "notice": "不同服務的分鐘數不抵扣；貢獻記錄不是可消費積分",
    }


def expire(s):
    current = datetime.now(UTC)
    for raw in s.all(
        "SELECT * FROM agreements WHERE status IN ('ACTIVE','CLOSING','DISPUTED')"
    ):
        a = unpack(raw)
        obligations = [
            unpack(r)
            for r in s.all(
                "SELECT * FROM obligations WHERE agreement_id=? AND status NOT IN ('ACCEPTED','WAIVED')",
                (a["id"],),
            )
        ]
        due = any(
            current > instant(o["data"]["due_at"])
            or o["status"] in ("SUBMITTED", "CONTESTED")
            and o["data"].get("submitted_at")
            and current
            > instant(o["data"]["submitted_at"])
            + timedelta(hours=POLICY["response_hours"])
            for o in obligations
        )
        if due:
            s.execute(
                "UPDATE agreements SET status='UNRESOLVED',version=version+1 WHERE id=?",
                (a["id"],),
            )
            emit(
                s,
                a["requester_id"],
                "agreement",
                a["id"],
                "RESPONSE_OVERDUE",
                {"automatic_acceptance": False},
            )

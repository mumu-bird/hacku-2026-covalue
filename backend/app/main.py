import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import domain as d
from . import mechanism
from . import schemas as sc
from .config import CASES, DATA_DIR, DEMO_MODE, POLICY, RULE_VERSION, TEMPLATES
from .db import DB, dump, unpack
from .seed import reset, seed


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.dbs = {}

    def get(self, case):
        if case not in CASES:
            d.fail("INVALID_INPUT", "未知演示案例", status=422)
        if case not in self.dbs:
            db = DB(self.path / (case + ".sqlite3"))
            with db.tx() as s:
                if not s.one("SELECT id FROM users LIMIT 1"):
                    seed(s, case)
            self.dbs[case] = db
        return self.dbs[case]


def create_app(data_dir=None, demo_mode=None):
    demo = DEMO_MODE if demo_mode is None else demo_mode
    registry = Registry(data_dir or DATA_DIR)

    async def sweep():
        while True:
            await asyncio.sleep(60)
            for db in list(registry.dbs.values()):
                with db.tx() as s:
                    d.expire(s)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(sweep())
        yield
        task.cancel()

    app = FastAPI(title="Hourlink · 時間有價", version="0.3.0", lifespan=lifespan)
    app.state.registry = registry

    @app.exception_handler(d.DomainError)
    async def domain_error(request, error):
        return JSONResponse(error.payload(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse(
            {
                "code": "INVALID_INPUT",
                "message": "輸入欄位不符合契約",
                "details": {
                    "fields": [
                        {"loc": list(e["loc"]), "message": e["msg"]}
                        for e in error.errors()
                    ]
                },
            },
            status_code=422,
        )

    def auth(request):
        case = request.cookies.get("hour_case", "cash")
        db = registry.get(case)
        with db.read() as s:
            session = s.one(
                "SELECT * FROM sessions WHERE token=?",
                (request.cookies.get("hour_session", ""),),
            )
            if not session or d.instant(session["expires"]) < datetime.now(UTC):
                d.fail("UNAUTHORIZED_ACTION", "請先登入演示帳戶", status=401)
            user = d.get(s, "users", session["user_id"])
        return db, user

    def command(request, body, fn):
        db, user = auth(request)
        key = request.headers.get("Idempotency-Key")
        if not key or len(key) > 200:
            d.fail("INVALID_INPUT", "寫入命令需要 Idempotency-Key", status=422)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            d.fail("UNAUTHORIZED_ACTION", "跨來源命令已拒絕", status=403)
        data = d.normalize(body.model_dump() if hasattr(body, "model_dump") else body)
        digest = sha256(dump(data).encode()).hexdigest()
        path = request.url.path
        with db.tx() as s:
            previous = s.one(
                "SELECT * FROM idempotency WHERE user_id=? AND key=?", (user["id"], key)
            )
            if previous:
                if (
                    previous["method"] != request.method
                    or previous["path"] != path
                    or previous["digest"] != digest
                ):
                    d.fail("IDEMPOTENCY_CONFLICT", "相同請求鍵不能用於不同命令")
                return JSONResponse(
                    json.loads(previous["result"]), status_code=previous["status"]
                )
            s.execute("SAVEPOINT business_command")
            try:
                result = fn(s, user["id"], data)
                status = 200
                s.execute("RELEASE SAVEPOINT business_command")
            except d.DomainError as error:
                s.execute("ROLLBACK TO SAVEPOINT business_command")
                s.execute("RELEASE SAVEPOINT business_command")
                result = error.payload()
                status = error.status
            s.insert(
                "idempotency",
                user_id=user["id"],
                key=key,
                method=request.method,
                path=path,
                digest=digest,
                result=dump(result),
                status=status,
            )
        return JSONResponse(result, status_code=status)

    def read(request, fn):
        db, user = auth(request)
        with db.read() as s:
            return fn(s, user["id"])

    @app.get("/api/v1/health")
    def health():
        return {
            "ok": True,
            "rule_version": RULE_VERSION,
            "demo_mode": demo,
            "real_payments": False,
        }

    @app.get("/api/v1/templates")
    def templates():
        return {
            "templates": TEMPLATES,
            "policy": POLICY,
            "rule_version": RULE_VERSION,
            "is_demo": True,
        }

    @app.get("/api/v1/demo/cases")
    def cases():
        if not demo:
            d.fail("UNAUTHORIZED_ACTION", "演示模式未開啟", status=403)
        return {"cases": [{"id": id, "name": name} for id, name in CASES.items()]}

    @app.get("/api/v1/mechanism")
    def mechanism_report():
        if not demo:
            d.fail("UNAUTHORIZED_ACTION", "機制實驗僅供演示", status=403)
        return mechanism.report()

    @app.post("/api/v1/mechanism/simulate")
    def mechanism_simulate(body: sc.MechanismInput):
        if not demo:
            d.fail("UNAUTHORIZED_ACTION", "機制實驗僅供演示", status=403)
        return mechanism.simulate(body.model_dump())

    @app.get("/api/v1/demo/users")
    def users():
        if not demo:
            d.fail("UNAUTHORIZED_ACTION", "演示模式未開啟", status=403)
        with registry.get("cash").read() as s:
            return s.all(
                "SELECT id,name,initials,headline,reviewer FROM users WHERE id IN ('zao','lin','wei','mei','reviewer')"
            )

    @app.post("/api/v1/auth/demo-login")
    def login(body: sc.Login):
        if not demo:
            d.fail("UNAUTHORIZED_ACTION", "演示登入僅限 DEMO_MODE", status=403)
        if body.username not in ("zao", "lin", "wei", "mei", "reviewer"):
            d.fail("INVALID_INPUT", "只能登入預置演示帳戶", status=422)
        db = registry.get(body.case)
        token = uuid.uuid4().hex + uuid.uuid4().hex
        with db.tx() as s:
            user = d.get(s, "users", body.username)
            s.insert(
                "sessions",
                token=token,
                user_id=user["id"],
                expires=(datetime.now(UTC) + timedelta(hours=12)).isoformat(),
            )
        response = JSONResponse({"user": user, "case": body.case, "simulated": True})
        response.set_cookie(
            "hour_session", token, httponly=True, samesite="strict", max_age=43200
        )
        response.set_cookie(
            "hour_case", body.case, httponly=True, samesite="strict", max_age=43200
        )
        return response

    @app.get("/api/v1/me")
    def me(request: Request):
        db, user = auth(request)
        with db.read() as s:
            return {
                "user": user,
                "case": request.cookies.get("hour_case", "cash"),
                "policy": d.capacity(s, user["id"], "spreadsheet"),
                "rule_version": RULE_VERSION,
            }

    @app.get("/api/v1/listings")
    def listings(
        request: Request,
        kind: str | None = None,
        category: str | None = None,
        q: str = "",
        owner_id: str | None = None,
        service_mode: str | None = None,
        location: str | None = None,
        time_start: datetime | None = None,
        time_end: datetime | None = None,
    ):
        db = registry.get(request.cookies.get("hour_case", "cash"))
        with db.read() as s:
            if (time_start and time_start.tzinfo is None) or (
                time_end and time_end.tzinfo is None
            ):
                d.fail("INVALID_INPUT", "篩選時段必須包含時區", status=422)
            rows = [
                unpack(r)
                for r in s.all(
                    "SELECT l.*,u.name owner_name,u.initials owner_initials FROM listings l JOIN users u ON u.id=l.owner_id ORDER BY CASE WHEN l.id='request-main' THEN 0 ELSE 1 END,l.rowid DESC"
                )
            ]
            return [
                r
                for r in rows
                if (not kind or r["kind"] == kind)
                and (not category or r["category"] == category)
                and (not owner_id or r["owner_id"] == owner_id)
                and (not service_mode or r["data"]["service_mode"] == service_mode)
                and (not location or location.lower() in r["data"]["location"].lower())
                and (not time_start or d.instant(r["data"]["end"]) >= time_start)
                and (not time_end or d.instant(r["data"]["start"]) <= time_end)
                and q.lower() in (r["title"] + r["data"]["scenario"]).lower()
            ]

    @app.post("/api/v1/listings")
    def publish(request: Request, body: sc.ListingInput):
        def run(s, user, b):
            id = d.uid("listing")
            category = b.pop("category")
            kind = b.pop("kind")
            title = b.pop("title")
            allowed = set(TEMPLATES[category]["skills"])
            if not set(b["required_skills"] + b["preferred_skills"]) <= allowed:
                d.fail("INVALID_INPUT", "技能標籤不屬於此服務模板", status=422)
            s.insert(
                "listings",
                id=id,
                owner_id=user,
                kind=kind,
                title=title,
                category=category,
                data=dump(b),
            )
            d.emit(s, user, "listing", id, "PUBLISHED")
            return d.get(s, "listings", id)

        return command(request, body, run)

    @app.get("/api/v1/listings/{id}")
    def listing(request: Request, id: str):
        with registry.get(request.cookies.get("hour_case", "cash")).read() as s:
            return d.get(s, "listings", id)

    @app.patch("/api/v1/listings/{id}")
    def edit_listing(request: Request, id: str, body: sc.ListingPatch):
        def run(s, user, b):
            row = d.get(s, "listings", id)
            d.version(row, b.pop("expected_version"))
            if row["owner_id"] != user:
                d.fail("UNAUTHORIZED_ACTION", "只能修改自己的刊登", status=403)
            if row["kind"] != b["kind"]:
                d.fail("INVALID_INPUT", "不能改變刊登入口", status=422)
            category = b.pop("category")
            b.pop("kind")
            title = b.pop("title")
            s.execute(
                "UPDATE listings SET category=?,title=?,data=?,version=version+1 WHERE id=?",
                (category, title, dump(b), id),
            )
            d.emit(s, user, "listing", id, "UPDATED")
            return d.get(s, "listings", id)

        return command(request, body, run)

    @app.post("/api/v1/listings/{id}/reopen")
    def reopen(request: Request, id: str, body: sc.Reopen):
        def run(s, user, b):
            row = d.get(s, "listings", id)
            d.version(row, b["expected_version"])
            if row["owner_id"] != user:
                d.fail("UNAUTHORIZED_ACTION", "只能重新開放自己的需求", status=403)
            if s.one(
                "SELECT id FROM agreements WHERE listing_id=? AND status IN ('ACTIVE','CLOSING','DISPUTED','UNRESOLVED','COMPLETED')",
                (id,),
            ):
                d.fail("INVALID_STATE", "需先結清；完整完成的需求請另建新單")
            s.execute(
                "UPDATE listings SET status='OPEN',version=version+1 WHERE id=?", (id,)
            )
            d.emit(s, user, "listing", id, "REOPENED")
            return d.get(s, "listings", id)

        return command(request, body, run)

    @app.post("/api/v1/listings/{id}/analyze")
    def analyze(request: Request, id: str, body: sc.Command):
        def run(s, user, b):
            row = d.get(s, "listings", id)
            d.version(row, b["expected_version"])
            if row["owner_id"] != user:
                d.fail("UNAUTHORIZED_ACTION", "只有刊登者可分析需求", status=403)
            missing = [
                field
                for field in ["scenario", "delivery_standard"]
                if not row["data"].get(field)
            ]
            d.emit(s, user, "listing", id, "ANALYZED")
            return {
                "requirements": row["data"],
                "category": row["category"],
                "missing_fields": missing,
                "template": TEMPLATES[row["category"]],
                "rule_version": RULE_VERSION,
                "is_demo": True,
            }

        return command(request, body, run)

    @app.get("/api/v1/listings/{id}/matches")
    def matches(request: Request, id: str):
        with registry.get(request.cookies.get("hour_case", "cash")).read() as s:
            return d.matches(s, d.get(s, "listings", id))

    @app.get("/api/v1/listings/{id}/proposals")
    def responses(request: Request, id: str):
        def run(s, user):
            if d.get(s, "listings", id)["owner_id"] != user:
                d.fail("UNAUTHORIZED_ACTION", "只有刊登者可查看全部回應", status=403)
            return [
                unpack(r)
                for r in s.all("SELECT * FROM proposals WHERE listing_id=?", (id,))
            ]

        return read(request, run)

    @app.post("/api/v1/proposals")
    def proposals(request: Request, body: sc.ProposalInput):
        return command(request, body, lambda s, u, b: d.create_proposal(s, u, b))

    @app.get("/api/v1/me/proposals")
    def my_proposals(request: Request):
        return read(
            request,
            lambda s, u: [
                unpack(r)
                for r in s.all(
                    "SELECT * FROM proposals WHERE requester_id=? OR provider_id=? ORDER BY rowid DESC",
                    (u, u),
                )
            ],
        )

    @app.get("/api/v1/proposals/{id}")
    def proposal(request: Request, id: str):
        def run(s, u):
            p = d.get(s, "proposals", id)
            d.participant(p, u)
            return p

        return read(request, run)

    @app.post("/api/v1/proposals/{id}/recommend")
    def recommend(request: Request, id: str, body: sc.Command):
        return command(
            request,
            body,
            lambda s, u, b: d.recommend(
                s, u, d.get(s, "proposals", id), b["expected_version"]
            ),
        )

    @app.post("/api/v1/proposals/{id}/revise")
    def revise(request: Request, id: str, body: sc.Revise):
        return command(
            request, body, lambda s, u, b: d.revise(s, u, d.get(s, "proposals", id), b)
        )

    @app.put("/api/v1/proposals/{id}/preference")
    def preference(request: Request, id: str, body: sc.Preference):
        return command(
            request,
            body,
            lambda s, u, b: d.preference(s, u, d.get(s, "proposals", id), b),
        )

    @app.get("/api/v1/proposals/{id}/preference")
    def own_preference(request: Request, id: str):
        def run(s, u):
            p = d.get(s, "proposals", id)
            d.participant(p, u)
            return s.one(
                "SELECT * FROM preferences WHERE proposal_id=? AND user_id=?", (id, u)
            )

        return read(request, run)

    @app.post("/api/v1/proposals/{id}/calculate")
    def calculate(request: Request, id: str, body: sc.Command):
        return command(
            request,
            body,
            lambda s, u, b: d.calculate(
                s, u, d.get(s, "proposals", id), b["expected_version"]
            ),
        )

    @app.get("/api/v1/proposals/{id}/perspectives")
    def perspectives(request: Request, id: str):
        return read(
            request, lambda s, u: d.perspectives(s, u, d.get(s, "proposals", id))
        )

    @app.put("/api/v1/proposals/{id}/perspectives")
    def save_perspective(request: Request, id: str, body: sc.Perspective):
        return command(
            request,
            body,
            lambda s, u, b: d.save_perspective(s, u, d.get(s, "proposals", id), b),
        )

    @app.post("/api/v1/proposals/{id}/select")
    def select_candidate(request: Request, id: str, body: sc.SelectCandidate):
        return command(
            request,
            body,
            lambda s, u, b: d.select_candidate(s, u, d.get(s, "proposals", id), b),
        )

    @app.post("/api/v1/agreements")
    def agreements(request: Request, body: sc.AgreementInput):
        return command(
            request,
            body,
            lambda s, u, b: d.create_agreement(
                s, u, d.get(s, "proposals", b["proposal_id"]), b
            ),
        )

    @app.get("/api/v1/agreements/{id}")
    def agreement(request: Request, id: str):
        return read(
            request, lambda s, u: d.agreement_view(s, d.get(s, "agreements", id), u)
        )

    @app.post("/api/v1/agreements/{id}/confirm")
    def confirm(request: Request, id: str, body: sc.Confirm):
        return command(
            request,
            body,
            lambda s, u, b: d.confirm(s, u, d.get(s, "agreements", id), b),
        )

    @app.post("/api/v1/stages/{id}/fund")
    def fund(request: Request, id: str, body: sc.Command):
        return command(
            request,
            body,
            lambda s, u, b: d.fund(s, u, d.get(s, "stages", id), b["expected_version"]),
        )

    @app.post("/api/v1/obligations/{id}/submit")
    def submit(request: Request, id: str, body: sc.Submit):
        return command(
            request,
            body,
            lambda s, u, b: d.submit(s, u, d.get(s, "obligations", id), b),
        )

    @app.post("/api/v1/obligations/{id}/accept")
    def accept(request: Request, id: str, body: sc.Accept):
        return command(
            request,
            body,
            lambda s, u, b: d.accept(s, u, d.get(s, "obligations", id), b),
        )

    @app.post("/api/v1/agreements/{id}/withdraw")
    def withdraw(request: Request, id: str, body: sc.Reason):
        return command(
            request,
            body,
            lambda s, u, b: d.withdraw(s, u, d.get(s, "agreements", id), b),
        )

    @app.post("/api/v1/agreements/{id}/disputes")
    def disputes(request: Request, id: str, body: sc.DisputeInput):
        return command(
            request,
            body,
            lambda s, u, b: d.create_dispute(s, u, d.get(s, "agreements", id), b),
        )

    @app.post("/api/v1/disputes/{id}/review")
    def review(request: Request, id: str, body: sc.Review):
        return command(
            request,
            body,
            lambda s, u, b: d.review_dispute(s, u, d.get(s, "disputes", id), b),
        )

    @app.post("/api/v1/agreements/{id}/closeouts")
    def closeouts(request: Request, id: str, body: sc.CloseoutInput):
        return command(
            request,
            body,
            lambda s, u, b: d.create_closeout(s, u, d.get(s, "agreements", id), b),
        )

    @app.post("/api/v1/closeouts/{id}/confirm")
    def closeout_confirm(request: Request, id: str, body: sc.CloseoutConfirm):
        return command(
            request,
            body,
            lambda s, u, b: d.confirm_closeout(s, u, d.get(s, "closeouts", id), b),
        )

    @app.get("/api/v1/me/orders")
    def orders(request: Request):
        return read(
            request,
            lambda s, u: [
                unpack(r)
                for r in s.all(
                    "SELECT * FROM agreements WHERE requester_id=? OR provider_id=? ORDER BY rowid DESC",
                    (u, u),
                )
            ],
        )

    @app.get("/api/v1/me/mock-account")
    def account(request: Request):
        return read(
            request,
            lambda s, u: {
                **s.one("SELECT * FROM accounts WHERE user_id=?", (u,)),
                "ledger": s.all(
                    "SELECT l.* FROM ledger l JOIN payment_intents p ON p.id=l.payment_id WHERE p.payer_id=? OR p.payee_id=? ORDER BY l.created DESC",
                    (u, u),
                ),
                "simulated": True,
                "withdrawable": False,
            },
        )

    @app.get("/api/v1/me/time-summary")
    def time_summary(request: Request):
        return read(request, lambda s, u: d.time_summary(s, u))

    @app.get("/api/v1/agreements/{id}/time-ledger")
    def time_ledger(request: Request, id: str):
        def run(s, u):
            a = d.agreement_view(s, d.get(s, "agreements", id), u)
            return {
                "agreement_id": id,
                "stages": a["stages"],
                "notice": "已確認貢獻保留；不同服務分鐘數不相減",
            }

        return read(request, run)

    @app.get("/api/v1/users/{id}/credit")
    def credit(
        request: Request, id: str, category: str = "spreadsheet", role: str = "PROVIDER"
    ):
        def run(s, u):
            d.get(s, "users", id)
            if category not in TEMPLATES:
                d.fail("INVALID_INPUT", "未知類別", status=422)
            evidence = d.evidence_for(s, id, category)
            if role not in ("PROVIDER", "REQUESTER"):
                d.fail("INVALID_INPUT", "未知履約角色", status=422)
            policy = d.capacity(s, id, category, role)
            completed = [e for e in evidence if e["kind"] == "HISTORY"]
            if role == "REQUESTER":
                completed = [
                    unpack(r)
                    for r in s.all(
                        "SELECT * FROM agreements WHERE requester_id=? AND mode='MONEY' AND status='COMPLETED'",
                        (id,),
                    )
                    if unpack(r)["data"]["scope"]["category"] == category
                ]
            return {
                "user_id": id,
                "category": category,
                "role": role,
                "completed_orders": len(completed),
                "independent_peers": policy["completed_peers"],
                "policy": policy,
                "simulated": True,
                "notice": "分類履約事實不等於專業資格，信用不直接改價",
            }

        return read(request, run)

    @app.post("/api/v1/capability-evidence")
    def capability(request: Request, body: sc.EvidenceInput):
        def run(s, u, b):
            if not set(b["skills"]) <= set(TEMPLATES[b["category"]]["skills"]):
                d.fail("INVALID_INPUT", "技能不屬於此模板", status=422)
            for row in s.all(
                "SELECT * FROM evidence WHERE owner_id=? AND category=? AND kind=?",
                (u, b["category"], b["kind"]),
            ):
                if unpack(row)["data"].get("body", "").strip() == b["body"].strip():
                    d.fail(
                        "DUPLICATE_EVIDENCE",
                        "這份材料已提交，不會重複提高能力評估",
                        status=422,
                    )
            id = d.uid("evidence")
            category = b.pop("category")
            kind = b.pop("kind")
            s.insert(
                "evidence",
                id=id,
                owner_id=u,
                category=category,
                kind=kind,
                data=dump({**b, "is_demo": True}),
                status="PENDING",
                created=d.now(),
            )
            d.emit(s, u, "evidence", id, "SUBMITTED")
            return d.get(s, "evidence", id)

        return command(request, body, run)

    @app.get("/api/v1/me/evidence")
    def evidence(request: Request):
        return read(
            request,
            lambda s, u: [
                unpack(r)
                for r in s.all(
                    "SELECT * FROM evidence WHERE owner_id=? ORDER BY created DESC",
                    (u,),
                )
            ],
        )

    @app.get("/api/v1/review/queue")
    def queue(request: Request):
        def run(s, u):
            d.reviewer(s, u)
            return {
                "evidence": [
                    unpack(r)
                    for r in s.all("SELECT * FROM evidence WHERE status='PENDING'")
                ],
                "disputes": [
                    unpack(r)
                    for r in s.all("SELECT * FROM disputes WHERE status='OPEN'")
                ],
            }

        return read(request, run)

    @app.post("/api/v1/capability-evidence/{id}/review")
    def evidence_review(request: Request, id: str, body: sc.EvidenceReview):
        def run(s, u, b):
            d.reviewer(s, u)
            row = d.get(s, "evidence", id)
            if row["status"] != "PENDING":
                d.fail("INVALID_STATE", "這項證據已復核")
            data = {
                **row["data"],
                "scores": b["scores"],
                "basis": b["basis"],
                "reviewed_at": d.now(),
            }
            s.execute(
                "UPDATE evidence SET status=?,quality=?,reviewer_id=?,data=? WHERE id=?",
                (
                    "APPROVED" if b["approve"] else "REJECTED",
                    d.quality(b["scores"]),
                    u,
                    dump(data),
                    id,
                ),
            )
            d.emit(s, u, "evidence", id, "REVIEWED")
            return d.get(s, "evidence", id)

        return command(request, body, run)

    @app.post("/api/v1/disputes/{id}/remedy")
    def remedy(request: Request, id: str, body: sc.Reason):
        def run(s, u, b):
            d.reviewer(s, u)
            row = d.get(s, "disputes", id)
            d.version(row, b["expected_version"])
            target = (row["data"].get("review") or {}).get("confirmed_breach_user_id")
            if not target:
                d.fail("INVALID_STATE", "沒有可補救的已確認違約")
            a = d.get(s, "agreements", row["agreement_id"])
            if a["status"] not in ("COMPLETED", "CANCELLED"):
                d.fail("INVALID_STATE", "原義務尚未完成或豁免，不能宣告補救完畢")
            other = [
                unpack(r) for r in s.all("SELECT * FROM disputes WHERE id!=?", (id,))
            ]
            if not any(
                (r["data"].get("review") or {}).get("confirmed_breach_user_id")
                == target
                and not r["data"].get("remedied")
                for r in other
            ):
                s.execute("UPDATE users SET blocked=0 WHERE id=?", (target,))
            data = {
                **row["data"],
                "remedied": {"by": u, "basis": b["reason"], "at": d.now()},
            }
            s.execute(
                "UPDATE disputes SET data=?,version=version+1 WHERE id=?",
                (dump(data), id),
            )
            d.emit(s, u, "dispute", id, "REMEDIED")
            return d.get(s, "disputes", id)

        return command(request, body, run)

    @app.post("/api/v1/demo/reset")
    def demo_reset(request: Request):
        if not demo:
            d.fail("UNAUTHORIZED_ACTION", "演示模式未開啟", status=403)
        db, user = auth(request)
        if not user["reviewer"]:
            d.fail("UNAUTHORIZED_ACTION", "只有復核員可以重置案例", status=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            d.fail("UNAUTHORIZED_ACTION", "跨來源命令已拒絕", status=403)
        with db.tx() as s:
            reset(s, request.cookies.get("hour_case", "cash"))
        return {"reset": True, "case": request.cookies.get("hour_case", "cash")}

    @app.get("/api/v1/demo/events")
    def export(request: Request):
        if not demo:
            d.fail("UNAUTHORIZED_ACTION", "演示模式未開啟", status=403)

        def run(s, u):
            d.reviewer(s, u)
            return {
                "rule_version": RULE_VERSION,
                "simulated": True,
                "events": [
                    unpack(r) for r in s.all("SELECT * FROM events ORDER BY created")
                ],
                "payments": s.all("SELECT * FROM payment_intents"),
                "obligations": [
                    {
                        "id": r["id"],
                        "agreement_id": r["agreement_id"],
                        "provider_id": r["provider_id"],
                        "recipient_id": r["recipient_id"],
                        "status": r["status"],
                        "minutes": unpack(r)["data"]["minutes"],
                    }
                    for r in s.all("SELECT * FROM obligations")
                ],
            }

        return read(request, run)

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            if path.startswith("api/"):
                d.fail("NOT_FOUND", "未知 API", status=404)
            return FileResponse(dist / "index.html")

    return app


app = create_app()

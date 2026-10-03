import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "data")


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        login(c)
        yield c


def login(c, user="zao", case="cash"):
    response = c.post("/api/v1/auth/demo-login", json={"username": user, "case": case})
    assert response.status_code == 200, response.text
    return c


def cmd(c, path, body=None, method="POST", key=None):
    return c.request(
        method,
        "/api/v1" + path,
        json=body or {},
        headers={"Idempotency-Key": key or str(uuid.uuid4())},
    )


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def proposal(c):
    return c.get("/api/v1/me/proposals").json()[0]


def draft(c, p=None, **options):
    p = p or proposal(c)
    return ok(
        cmd(
            c,
            "/agreements",
            {
                "proposal_id": p["id"],
                "expected_version": p["version"],
                "rounds": 2,
                **options,
            },
        )
    )


def order(c, id):
    return ok(c.get("/api/v1/agreements/" + id))


def activate(c, a, case="cash"):
    login(c, "zao", case)
    a = ok(
        cmd(
            c,
            f"/agreements/{a['id']}/confirm",
            {"expected_version": a["version"], "terms_version": a["terms_version"]},
        )
    )
    login(c, "lin", case)
    return ok(
        cmd(
            c,
            f"/agreements/{a['id']}/confirm",
            {"expected_version": a["version"], "terms_version": a["terms_version"]},
        )
    )


def accept_ob(c, a, ob, case="cash", execution=None):
    login(c, ob["provider_id"], case)
    ob = ok(
        cmd(
            c,
            f"/obligations/{ob['id']}/submit",
            {
                "expected_version": ob["version"],
                "evidence": "已依本階段驗收標準交付成果",
                "execution_minutes": execution or ob["data"]["minutes"],
            },
        )
    )
    login(c, ob["recipient_id"], case)
    return ok(
        cmd(
            c,
            f"/obligations/{ob['id']}/accept",
            {
                "expected_version": ob["version"],
                "scores": {"correctness": 95, "completeness": 95, "independence": 95},
            },
        )
    )

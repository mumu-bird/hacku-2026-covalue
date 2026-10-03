from .conftest import activate, cmd, draft, login, ok, order, proposal


def listing_body(client, id="request-main"):
    listing = ok(client.get("/api/v1/listings/" + id))
    return listing, listing["data"] | {
        "title": listing["title"],
        "kind": listing["kind"],
        "category": listing["category"],
        "expected_version": listing["version"],
    }


def test_edit_invalidates_pending_signatures_and_old_proposal(client):
    p = proposal(client)
    a = draft(client, p)
    a = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/confirm",
            {"expected_version": a["version"], "terms_version": a["terms_version"]},
        )
    )
    listing, body = listing_body(client)
    edited = ok(
        cmd(
            client,
            "/listings/request-main",
            body | {"title": "更新交付範圍的表格需求"},
            method="PATCH",
        )
    )
    assert edited["version"] == listing["version"] + 1
    assert order(client, a["id"])["status"] == "CANCELLED"
    viewed = ok(client.get(f"/api/v1/proposals/{p['id']}"))
    assert viewed["stale_listing"] and viewed["agreement"] is None
    assert (
        cmd(
            client,
            "/agreements",
            {"proposal_id": p["id"], "expected_version": p["version"], "rounds": 2},
        ).json()["code"]
        == "RECOMMENDATION_STALE"
    )


def test_active_listing_cannot_edit_or_close_and_money_unchanged(client):
    a = activate(client, draft(client))
    login(client)
    listing, body = listing_body(client)
    before = ok(client.get("/api/v1/me/mock-account"))
    assert (
        cmd(client, "/listings/request-main", body, method="PATCH").json()["code"]
        == "INVALID_STATE"
    )
    assert (
        cmd(
            client,
            "/listings/request-main/close",
            {"expected_version": listing["version"]},
        ).json()["code"]
        == "INVALID_STATE"
    )
    assert before == ok(client.get("/api/v1/me/mock-account"))
    assert order(client, a["id"])["status"] == "ACTIVE"


def test_close_reopen_idempotency_permissions_and_public_filter(client):
    listing, _ = listing_body(client)
    login(client, "lin")
    assert (
        cmd(
            client,
            "/listings/request-main/close",
            {"expected_version": listing["version"]},
        ).status_code
        == 403
    )
    login(client)
    key = "close-same-request"
    closed = ok(
        cmd(
            client,
            "/listings/request-main/close",
            {"expected_version": listing["version"]},
            key=key,
        )
    )
    assert closed["status"] == "CLOSED"
    assert (
        ok(
            cmd(
                client,
                "/listings/request-main/close",
                {"expected_version": listing["version"]},
                key=key,
            )
        )
        == closed
    )
    assert "request-main" not in [
        x["id"] for x in ok(client.get("/api/v1/listings?status=OPEN"))
    ]
    assert (
        cmd(
            client, "/proposals", {"listing_id": "request-main", "provider_id": "lin"}
        ).json()["code"]
        == "LISTING_TAKEN"
    )
    reopened = ok(
        cmd(
            client,
            "/listings/request-main/reopen",
            {"expected_version": closed["version"]},
        )
    )
    assert reopened["status"] == "OPEN"
    assert (
        cmd(
            client,
            "/listings/request-main/close",
            {"expected_version": closed["version"]},
        ).json()["code"]
        == "VERSION_CONFLICT"
    )


def test_patch_cannot_inject_other_category_skills(client):
    _, body = listing_body(client)
    bad = cmd(
        client,
        "/listings/request-main",
        body | {"required_skills": ["英语交流"]},
        method="PATCH",
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "INVALID_INPUT"


def test_cancel_unsigned_contract_is_atomic_and_cannot_cancel_active(client):
    p = proposal(client)
    a = draft(client, p)
    view = ok(client.get(f"/api/v1/proposals/{p['id']}"))
    assert view["agreement"]["id"] == a["id"]
    before = ok(client.get("/api/v1/me/mock-account"))
    cancelled = ok(
        cmd(
            client,
            f"/agreements/{a['id']}/cancel-draft",
            {"expected_version": a["version"]},
            key="cancel-draft",
        )
    )
    assert cancelled["status"] == "CANCELLED"
    assert cancelled == ok(
        cmd(
            client,
            f"/agreements/{a['id']}/cancel-draft",
            {"expected_version": a["version"]},
            key="cancel-draft",
        )
    )
    assert ok(client.get(f"/api/v1/proposals/{p['id']}"))["agreement"] is None
    assert before == ok(client.get("/api/v1/me/mock-account"))
    active = activate(client, draft(client, p))
    assert (
        cmd(
            client,
            f"/agreements/{active['id']}/cancel-draft",
            {"expected_version": active["version"]},
        ).json()["code"]
        == "INVALID_STATE"
    )


def test_close_reverse_offer_cancels_draft_and_active_reverse_offer_is_protected(
    client,
):
    login(client, "zao", "barter")
    p = proposal(client)
    a = draft(client, p)
    reverse_id = p["data"]["reverse"]["listing_id"]
    listing, _ = listing_body(client, reverse_id)
    ok(
        cmd(
            client,
            f"/listings/{reverse_id}/close",
            {"expected_version": listing["version"]},
        )
    )
    assert order(client, a["id"])["status"] == "CANCELLED"
    assert ok(client.get(f"/api/v1/proposals/{p['id']}"))["stale_listing"]
    closed, _ = listing_body(client, reverse_id)
    reopened = ok(
        cmd(
            client,
            f"/listings/{reverse_id}/reopen",
            {"expected_version": closed["version"]},
        )
    )
    fresh = ok(
        cmd(
            client,
            "/proposals/recommended",
            {
                "listing_id": "request-main",
                "provider_id": "lin",
                "mode": "BARTER",
                "reverse_listing_id": reverse_id,
            },
        )
    )
    activate(client, draft(client, fresh), "barter")
    login(client, "zao", "barter")
    _, body = listing_body(client, reverse_id)
    for response in [
        cmd(client, f"/listings/{reverse_id}", body, method="PATCH"),
        cmd(
            client,
            f"/listings/{reverse_id}/close",
            {"expected_version": reopened["version"]},
        ),
    ]:
        assert response.status_code == 409
        assert response.json()["code"] == "INVALID_STATE"


def test_recommended_proposal_failure_leaves_no_orphan_and_success_replays(client):
    before = ok(client.get("/api/v1/me/proposals"))
    response = cmd(
        client,
        "/proposals/recommended",
        {"listing_id": "request-main", "provider_id": "peer1", "mode": "MONEY"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "POLICY_BLOCKED"
    assert before == ok(client.get("/api/v1/me/proposals"))
    body = {"listing_id": "request-main", "provider_id": "lin", "mode": "MONEY"}
    success = ok(cmd(client, "/proposals/recommended", body, key="recommended"))
    assert success["data"]["recommendation"]
    assert success == ok(cmd(client, "/proposals/recommended", body, key="recommended"))
    assert len(ok(client.get("/api/v1/me/proposals"))) == len(before) + 1

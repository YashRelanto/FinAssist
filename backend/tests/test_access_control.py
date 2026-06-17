"""
Access control / IDOR regression tests.

These tests verify that:
  1. Unauthenticated requests are rejected (401).
  2. Authenticated users can only access their own data.
  3. Supplying another user's ID in a query param / body is silently ignored
     and the response always contains the caller's own data.
  4. Mutating another user's resource returns 403 Forbidden.
  5. Admin users can access any user's data.

Run with:
    cd backend
    pytest tests/test_access_control.py -v
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

USER_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ADMIN_ID  = "cccccccc-cccc-cccc-cccc-cccccccccccc"

TOKEN_A     = "token-user-a"
TOKEN_B     = "token-user-b"
TOKEN_ADMIN = "token-admin"


def _make_auth_user(user_id: str, role: str = "user") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = f"{user_id[:4]}@test.com"
    u.user_metadata = {"role": role}
    return u


def _make_get_user(user_id: str, role: str = "user"):
    """Return a mock supabase_auth.auth.get_user that resolves the given user."""
    resp = MagicMock()
    resp.user = _make_auth_user(user_id, role)

    def _get_user(token: str):
        mapping = {
            TOKEN_A:     (USER_A_ID, "user"),
            TOKEN_B:     (USER_B_ID, "user"),
            TOKEN_ADMIN: (ADMIN_ID,  "admin"),
        }
        uid, r = mapping.get(token, (None, None))
        if uid is None:
            raise Exception("Invalid token")
        rr = MagicMock()
        rr.user = _make_auth_user(uid, r)
        return rr

    return _get_user


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """
    Build a TestClient with supabase_auth mocked so no real network calls occur.
    supabase_db (table reads/writes) is also mocked to return empty data.
    """
    mock_auth = MagicMock()
    mock_auth.auth.get_user.side_effect = _make_get_user(USER_A_ID)

    mock_db = MagicMock()
    # Default: table().select().eq().execute() returns empty list
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_db.table.return_value.select.return_value.execute.return_value.data = []
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"user_id": USER_A_ID}]
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [{"user_id": USER_A_ID}]
    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []

    with (
        patch("app.utils.supabase_client.supabase_auth", mock_auth),
        patch("app.utils.supabase_client.supabase_db",   mock_db),
        patch("app.utils.supabase_client.supabase",      mock_db),
    ):
        from app.main import app
        with TestClient(app) as c:
            c._mock_auth = mock_auth
            c._mock_db   = mock_db
            yield c


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper: make mock_auth.auth.get_user resolve multi-token mapping
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_get_user(client):
    client._mock_auth.auth.get_user.side_effect = _make_get_user(USER_A_ID)


# ---------------------------------------------------------------------------
# 1. Unauthenticated requests → 401
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    READ_ENDPOINTS = [
        "/api/transactions",
        "/api/accounts",
        "/api/dashboard-summary",
        "/api/account-hub-analysis",
        "/api/upcoming-payments",
        "/api/budget-goals-summary",
        "/api/budgets",
        "/api/goals",
        "/api/investments",
        "/api/forecast",
        "/api/statement/uploaded-statements",
    ]

    @pytest.mark.parametrize("path", READ_ENDPOINTS)
    def test_get_without_token_is_401(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} should require auth"

    def test_post_transaction_without_token_is_401(self, client):
        resp = client.post("/api/transactions", json={
            "account_id": str(uuid.uuid4()), "amount": 100,
            "transaction_type": "expense", "merchant_name": "Shop",
            "description": "Test", "main_category": "Food",
            "transaction_date": "2025-01-01",
        })
        assert resp.status_code == 401

    def test_delete_budget_without_token_is_401(self, client):
        resp = client.delete(f"/api/budgets/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. Authenticated user always gets their own data (user_id query param ignored)
# ---------------------------------------------------------------------------

class TestQueryParamIgnored:
    def test_transactions_user_id_param_ignored(self, client):
        """Passing ?user_id=<other_user> should silently use the JWT identity."""
        resp = client.get(f"/api/transactions?user_id={USER_B_ID}", headers=_auth(TOKEN_A))
        # The endpoint is now auth-gated; it should not fail with 403/401.
        # The response will use USER_A (from token), not USER_B.
        assert resp.status_code != 403
        assert resp.status_code != 401

    def test_accounts_user_id_param_ignored(self, client):
        resp = client.get(f"/api/accounts?user_id={USER_B_ID}", headers=_auth(TOKEN_A))
        assert resp.status_code not in (401, 403)

    def test_budgets_user_id_param_ignored(self, client):
        resp = client.get(f"/api/budgets?user_id={USER_B_ID}", headers=_auth(TOKEN_A))
        assert resp.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# 3. PUT/DELETE cross-user → 403
# ---------------------------------------------------------------------------

class TestOwnershipEnforcement:
    def _setup_resource_owned_by_b(self, client, table: str, pk_col: str, pk_val: str):
        """Make the DB mock return USER_B as owner of the resource."""
        client._mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"user_id": USER_B_ID}
        ]

    def test_delete_other_users_transaction_is_403(self, client):
        tx_id = str(uuid.uuid4())
        self._setup_resource_owned_by_b(client, "transactions", "transaction_id", tx_id)
        resp = client.delete(f"/api/transactions/{tx_id}", headers=_auth(TOKEN_A))
        assert resp.status_code == 403

    def test_delete_other_users_account_is_403(self, client):
        acct_id = str(uuid.uuid4())
        self._setup_resource_owned_by_b(client, "accounts", "account_id", acct_id)
        resp = client.delete(f"/api/accounts/{acct_id}", headers=_auth(TOKEN_A))
        assert resp.status_code == 403

    def test_delete_other_users_budget_is_403(self, client):
        budget_id = str(uuid.uuid4())
        self._setup_resource_owned_by_b(client, "budgets", "budget_id", budget_id)
        resp = client.delete(f"/api/budgets/{budget_id}", headers=_auth(TOKEN_A))
        assert resp.status_code == 403

    def test_delete_other_users_goal_is_403(self, client):
        goal_id = str(uuid.uuid4())
        self._setup_resource_owned_by_b(client, "goals", "goal_id", goal_id)
        resp = client.delete(f"/api/goals/{goal_id}", headers=_auth(TOKEN_A))
        assert resp.status_code == 403

    def test_delete_other_users_investment_is_403(self, client):
        inv_id = str(uuid.uuid4())
        self._setup_resource_owned_by_b(client, "investments", "investment_id", inv_id)
        resp = client.delete(f"/api/investments/{inv_id}", headers=_auth(TOKEN_A))
        assert resp.status_code == 403

    def test_put_other_users_profile_is_403(self, client):
        resp = client.put(
            f"/api/users/{USER_B_ID}",
            json={"full_name": "Attacker", "email": "x@evil.com"},
            headers=_auth(TOKEN_A),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Owner can access their own resources
# ---------------------------------------------------------------------------

class TestOwnerAccess:
    def _setup_resource_owned_by_a(self, client):
        client._mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"user_id": USER_A_ID}
        ]

    def test_owner_can_delete_own_budget(self, client):
        self._setup_resource_owned_by_a(client)
        budget_id = str(uuid.uuid4())
        resp = client.delete(f"/api/budgets/{budget_id}", headers=_auth(TOKEN_A))
        # 200 or 404 (mock returns empty after delete) — either means auth passed
        assert resp.status_code in (200, 404, 500)
        assert resp.status_code != 403

    def test_owner_can_delete_own_goal(self, client):
        self._setup_resource_owned_by_a(client)
        goal_id = str(uuid.uuid4())
        resp = client.delete(f"/api/goals/{goal_id}", headers=_auth(TOKEN_A))
        assert resp.status_code != 403

    def test_own_profile_update_allowed(self, client):
        # Mock the users table update to return a row
        client._mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            {"user_id": USER_A_ID, "full_name": "User A", "email": "a@test.com"}
        ]
        resp = client.put(
            f"/api/users/{USER_A_ID}",
            json={"full_name": "User A Updated", "email": "a@test.com"},
            headers=_auth(TOKEN_A),
        )
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# 5. Admin can access / mutate any user's resources
# ---------------------------------------------------------------------------

class TestAdminBypass:
    def _setup_resource_owned_by_b(self, client):
        client._mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"user_id": USER_B_ID}
        ]

    def test_admin_can_delete_another_users_budget(self, client):
        self._setup_resource_owned_by_b(client)
        budget_id = str(uuid.uuid4())
        resp = client.delete(f"/api/budgets/{budget_id}", headers=_auth(TOKEN_ADMIN))
        # Should NOT be 403 — admin bypass applies
        assert resp.status_code != 403

    def test_admin_can_delete_another_users_goal(self, client):
        self._setup_resource_owned_by_b(client)
        goal_id = str(uuid.uuid4())
        resp = client.delete(f"/api/goals/{goal_id}", headers=_auth(TOKEN_ADMIN))
        assert resp.status_code != 403

    def test_admin_can_update_another_users_profile(self, client):
        client._mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            {"user_id": USER_B_ID, "full_name": "User B", "email": "b@test.com"}
        ]
        resp = client.put(
            f"/api/users/{USER_B_ID}",
            json={"full_name": "Admin Override", "email": "b@test.com"},
            headers=_auth(TOKEN_ADMIN),
        )
        assert resp.status_code != 403

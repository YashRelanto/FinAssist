"""Tests for auth error mapping and profile service helpers."""

import pytest

from app.services.user_profile_service import auth_error_detail


def test_auth_error_invalid_credentials():
    exc = Exception("Invalid login credentials")
    status, detail = auth_error_detail(exc)
    assert status == 401
    assert "password" in detail.lower()


def test_auth_error_email_not_confirmed():
    exc = Exception("Email not confirmed")
    status, detail = auth_error_detail(exc)
    assert status == 400
    assert detail == "email_not_confirmed"


def test_auth_error_rls_maps_to_safe_message():
    exc = Exception(
        "{'message': 'new row violates row-level security policy for table \"users\"', "
        "'code': '42501'}"
    )
    status, detail = auth_error_detail(exc)
    assert status == 500
    assert "setup failed" in detail.lower()

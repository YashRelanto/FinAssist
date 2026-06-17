"""Tests for tab-scoped logging config."""

from app.core.config import Settings, _env_bool


def test_env_bool_parses_truthy_values():
    import os

    os.environ["TEST_TAB_LOG_FLAG"] = "true"
    assert _env_bool("TEST_TAB_LOG_FLAG", False) is True
    os.environ["TEST_TAB_LOG_FLAG"] = "yes"
    assert _env_bool("TEST_TAB_LOG_FLAG", False) is True
    os.environ["TEST_TAB_LOG_FLAG"] = "false"
    assert _env_bool("TEST_TAB_LOG_FLAG", True) is False
    del os.environ["TEST_TAB_LOG_FLAG"]


def test_is_tab_log_enabled_defaults():
    s = Settings()
    assert s.is_tab_log_enabled("analytics") is s.LOG_TAB_ANALYTICS
    assert s.is_tab_log_enabled("unknown_tab") is False

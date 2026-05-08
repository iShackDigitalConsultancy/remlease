"""
Test that benchmarks._bootstrap unconditionally overrides
DATABASE_URL and ENVIRONMENT, even when production values are
already in os.environ.

Background: A pre-fix bootstrap used os.environ.setdefault,
which yields to existing environment values. This caused a
production-database near-miss on 2026-05-08 when the operator
sourced lexichat-api/.env (which sets DATABASE_URL to the
Railway production URL) before invoking the benchmark. The
insert was rejected by a FK constraint (no write completed),
but the connection and query happened.

The fix: unconditional os.environ["KEY"] = value assignment.
These tests verify both the adversarial case (env pre-polluted
with production values) and the clean-shell case.

See STANDING_RULES.md Rule 8.
"""
import importlib
import os

import pytest


def test_bootstrap_overrides_production_database_url():
    """
    Adversarial case: bootstrap must override DATABASE_URL even
    when a production PostgreSQL URL is already exported in the
    shell environment.

    This is the exact failure mode that triggered the 2026-05-08
    near-miss: os.environ.setdefault left the production URL in
    place because it was already set.
    """
    # Simulate a polluted shell environment with a production URL
    os.environ["DATABASE_URL"] = "postgresql://prod:5432/prod_db"
    os.environ["ENVIRONMENT"] = "production"

    # Re-import bootstrap to trigger its override logic
    from benchmarks import _bootstrap
    importlib.reload(_bootstrap)

    # Bootstrap MUST have overridden both regardless of prior values
    assert os.environ["DATABASE_URL"] == "sqlite:///:memory:", (
        f"Bootstrap did not override DATABASE_URL — got "
        f"{os.environ['DATABASE_URL']!r}, expected 'sqlite:///:memory:'"
    )
    assert os.environ["ENVIRONMENT"] == "development", (
        f"Bootstrap did not override ENVIRONMENT — got "
        f"{os.environ['ENVIRONMENT']!r}, expected 'development'"
    )


def test_bootstrap_sets_values_when_environment_clean():
    """
    Clean-shell case: bootstrap sets DATABASE_URL and ENVIRONMENT
    when neither is present in the environment.
    """
    # Simulate a clean shell with no DB or environment vars set
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("ENVIRONMENT", None)

    from benchmarks import _bootstrap
    importlib.reload(_bootstrap)

    assert os.environ["DATABASE_URL"] == "sqlite:///:memory:", (
        "Bootstrap did not set DATABASE_URL in a clean environment"
    )
    assert os.environ["ENVIRONMENT"] == "development", (
        "Bootstrap did not set ENVIRONMENT in a clean environment"
    )


def test_bootstrap_assertion_fires_if_override_fails(monkeypatch):
    """
    Defense-in-depth: the assertion inside _bootstrap.py must
    raise AssertionError if the override somehow fails. This test
    verifies the assertion is present and operative by monkeypatching
    os.environ.__setitem__ to be a no-op for DATABASE_URL, then
    confirming the assertion fires.

    If this test fails (the AssertionError is NOT raised), it means
    the in-module assertion was removed — a regression.
    """
    original_setitem = os.environ.__class__.__setitem__

    def selective_noop(self, key, value):
        if key == "DATABASE_URL":
            # Silently drop the assignment — simulates override failure
            return
        original_setitem(self, key, value)

    monkeypatch.setattr(os.environ.__class__, "__setitem__", selective_noop)

    # Ensure DATABASE_URL starts with a wrong value
    original_setitem(os.environ, "DATABASE_URL", "postgresql://bad/db")

    with pytest.raises(AssertionError, match="Bootstrap failed: DATABASE_URL"):
        from benchmarks import _bootstrap
        importlib.reload(_bootstrap)

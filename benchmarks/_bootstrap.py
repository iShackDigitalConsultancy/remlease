"""
Bootstrap module for the benchmark harness.

MUST be imported FIRST by every benchmarks module that
transitively depends on lexichat-api. Unconditionally overrides
DATABASE_URL to an in-memory SQLite engine before any production
code is imported.

IMPORTANT — uses hard assignment (os.environ["KEY"] = value), NOT
os.environ.setdefault. setdefault yields to existing environment
values, which defeats the purpose of isolation. If an operator has
sourced a production .env file (e.g. lexichat-api/.env which sets
DATABASE_URL to the Railway production URL), setdefault would leave
the production URL in place and the benchmark would hit production.

Background: a production-database near-miss occurred on 2026-05-08
when the operator sourced lexichat-api/.env before invoking the
benchmark. The insert was rejected by a FK constraint (no write
completed), but the connection and query happened. This hard-override
pattern prevents recurrence regardless of shell environment state.

See STANDING_RULES.md Rule 8.

Usage at top of every benchmarks module:
    from benchmarks import _bootstrap  # noqa: F401
"""
import os

# Hard override — benchmarks must NEVER pick up production
# DATABASE_URL even if it was exported in the shell. The
# benchmark's purpose is isolation; setdefault would defeat
# that purpose. See STANDING_RULES.md Rule 8 and the
# IMPL-EXT-003b post-merge defect (production DB connection
# near-miss on 2026-05-08).
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENVIRONMENT"] = "development"

# Defense-in-depth: confirm the override took effect
assert os.environ["DATABASE_URL"] == "sqlite:///:memory:", \
    "Bootstrap failed: DATABASE_URL was not overridden to SQLite"
assert os.environ["ENVIRONMENT"] == "development", \
    "Bootstrap failed: ENVIRONMENT was not overridden"

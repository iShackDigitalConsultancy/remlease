"""
Bootstrap module for the benchmark harness.

MUST be imported FIRST by every benchmarks module that 
transitively depends on lexichat-api. Sets DATABASE_URL to 
an in-memory SQLite engine before any production code is 
imported.

Usage at top of every benchmarks module:
    from benchmarks import _bootstrap  # noqa: F401
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")

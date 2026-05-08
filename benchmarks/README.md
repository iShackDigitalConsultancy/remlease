# REM-Leases Local Benchmark Harness

This harness executes the core extraction pipeline locally against a set of input documents without requiring a live PostgreSQL connection or FastAPI server instance. It provisions an ephemeral, in-memory SQLite schema, isolates document assets into discrete run directories, and mints benchmark-specific vector namespaces to prevent production data pollution. 

## Quick Start
To validate configuration without invoking external APIs:
```bash
python -m benchmarks.run --doc-limit 1 --dry-run
```

To run a single-document smoke test (skipping embeddings to preserve isolation in `003b`):
```bash
python -m benchmarks.run --doc-limit 1
```

To run against the entire `inputs/` corpus:
```bash
python -m benchmarks.run
```

## How the harness avoids importing production state
To prevent the production database connection string (`DATABASE_URL`) from enforcing a hard crash on missing credentials, every file in the benchmark harness that relies on `lexichat-api` must declare the following as its very first import:

```python
from benchmarks import _bootstrap  # noqa: F401
```
The `_bootstrap.py` module injects a mock `sqlite:///:memory:` connection string into the environment *before* `database.py` is loaded, satisfying its checks while preserving total isolation.

## Required Environment Variables
The following secrets must be available in the environment (or a populated `.env` file):
- `GROQ_API_KEY` (Used for extraction tasks)
- `VOYAGE_API_KEY` (Used for vector embeddings, though skipped by default in `003b`)
- `LLAMA_CLOUD_API_KEY` (Used for premium OCR parsing, falls back to PyMuPDF if missing)

## Run Artifacts
Each invocation generates a timestamped directory (e.g. `benchmarks/runs/2026-05-08T12-00-00Z_default/`) containing:
- `manifest.json`: A detailed schema capturing run metadata, document processing statuses, stage latencies, and sanitized secret fingerprints.
- `workspace_summary.json`: A rolling count of successfully processed documents.
- `docs/<doc_id>/`: A per-document subdirectory housing all intermediate caches, extracted JSON fragments, and the final generated intelligence report.

## Pending Implementation Details
The current version (`003b`) is the skeleton. The following features are actively deferred:
- **Cost Controls and Premium Mode Toggling** (Deferred to `IMPL-EXT-003c`)
- **Parsing Health Score Metrics** (Deferred to `IMPL-EXT-003d`)
- **Full Corpus Distribution and Manifest Hashing** (Deferred to `IMPL-EXT-003e`)
- **Vector Space Integration** (Currently mocked via `--skip-embeddings=True`. Real Pinecone namespace isolation will be implemented in `IMPL-EXT-003c`.)

## Namespace Cleanup
If a benchmark run fails catastrophically or crashes before `cleanup_benchmark_namespace` is invoked, Pinecone vectors may be left orphaned in the newly minted `benchmark-<run_id>` namespace. (Not applicable in `003b` as embeddings are skipped). Operators can manually delete the namespace via the Pinecone UI by searching for the corresponding run UUID.

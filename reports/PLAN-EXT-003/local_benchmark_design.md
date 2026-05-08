# Local Benchmark Environment Design Proposal
## Ticket: PLAN-EXT-003

## SECTION 1 — REQUIREMENTS

### MUST-HAVE
1. **Single Command Runner:** A unified entry point (e.g., `python -m benchmarks.run`) to process all PDFs in `benchmarks/inputs/` through the full production pipeline (ingestion, parsing, chunking, embedding, intelligence extraction, verification).
2. **Deterministic Artefact Layout:** All intermediate artefacts (PDF, MD, caches, vector payloads, trace logs) must be written to `benchmarks/runs/{run_id}/` in a clean, git-ignorable structure.
3. **LlamaParse Configurability:** Toggle `premium_mode` (and potentially other args) via a single CLI flag or JSON config file (e.g. `--premium`).
4. **Code Path Parity:** The benchmark must invoke the exact functions used by production (`ingestion_service.py`, `intelligence_service.py`, `intelligence_engine.py`) via dependency-injected seams rather than duplicated logic.
5. **Idempotent / Isolated Re-runs:** Subsequent runs must not corrupt previous runs. Vectors must be sent to an isolated Pinecone namespace (e.g., `benchmark-{run_id}`) to prevent index pollution.
6. **Cost Transparency:** Produce a `cost_summary.json` aggregating LlamaParse page counts, Voyage/OpenAI embedding tokens, and Groq inference tokens with estimated USD costs.
7. **Reproducibility Manifest:** Produce a `manifest.json` detailing git hash, LlamaParse config, model versions/temperatures, PDF SHA256 hashes, and timestamp.
8. **Mocked/Ephemeral Database:** The pipeline must use a clean, ephemeral SQLite database (or isolated test DB schema) so it doesn't pollute the production Postgres instance with benchmark workspaces.

### SHOULD-HAVE
1. **Parallel Processing:** Ability to run documents concurrently (e.g., via `asyncio.gather`) to reduce total benchmark time, considering the pipeline takes minutes per document.
2. **Selective Execution (Skip Embeddings):** A flag `--skip-embeddings` to bypass Voyage and Pinecone if the benchmark is strictly evaluating deterministic extraction or parsing quality.
3. **Diff/Compare Tool:** A utility script `python -m benchmarks.compare run_A run_B` to automatically compute regressions/improvements between two benchmark runs.

---

## SECTION 2 — ARCHITECTURE PROPOSAL

### 2.1 Entry Point
**Proposed:** A Python CLI tool (`benchmarks/run.py`).
**Justification:** A Python CLI natively integrates with the existing FastAPI backend, shares the same virtual environment, allows direct importing of SQLAlchemy models and service functions, and elegantly handles asynchronous orchestration via `asyncio.run()`. Makefiles and Bash scripts struggle with Python's async context and DB session management.

### 2.2 Pipeline Orchestration
1. **CLI Invocation:** `python -m benchmarks.run --config benchmark_basic.json`
2. **Initialization:** CLI creates `benchmarks/runs/{run_id}/` directory. Initializes a temporary SQLite DB session in memory. Determines Pinecone namespace.
3. **Seeding:** Generates a synthetic `Workspace` in the temporary DB.
4. **Ingestion (`ingestion_service.py`):** 
   - CLI iterates over PDFs in `benchmarks/inputs/`.
   - Calls a refactored `process_local_file(file_path, doc_id, ...)` which wraps the core logic previously coupled to `UploadFile` and background tasks.
5. **Extraction (`intelligence_engine.py` & `intelligence_service.py`):**
   - Calls `intelligence_service.extract_expiries` and `extract_timeline` sequentially, passing the isolated DB session and overriding the `UPLOAD_DIR` to point to the run's `docs/{doc_id}/` directory.
   - Computes `generate_intelligence_report`.
6. **Finalization:** Writes `manifest.json` and `cost_summary.json`.

### 2.3 Output Layout
```text
benchmarks/
  inputs/
    n1_franchise.pdf
    eikestad_lease.pdf
  runs/
    2026-05-08_14-30-00_basic/
      manifest.json
      cost_summary.json
      workspace_summary.json
      docs/
        n1_franchise/
          source.pdf
          document.md
          ingestion_status.json
          fundamental_terms.json
          expiries.json
          intelligence_report.json
          trace.log
```

---

## SECTION 3 — PRODUCTION CODE REFACTORS REQUIRED

### 3.1 `ingestion_service.py`
- **Current Issue:** `upload_pdf` strictly expects an `UploadFile` from FastAPI and spawns a `BackgroundTasks` thread. The file saving path is hardcoded to `config.UPLOAD_DIR`.
- **Refactor Proposal:** Extract the core logic of `upload_pdf` and `process_document_background` into a synchronous/awaitable pure function `ingest_document(pdf_bytes, doc_id, workspace_id, db, upload_dir, llamaparse_config)`. The FastAPI route becomes a simple wrapper that reads the `UploadFile` and passes the bytes to `ingest_document`.
- **Risk Level:** **LOW-MEDIUM**. Touches the primary file I/O path but conceptually just extracts a helper function.

### 3.2 `intelligence_service.py`
- **Current Issue:** Functions like `extract_expiries` extract `Depends(get_db)` and `current_user`. They also construct file paths by hardcoding `os.path.join(UPLOAD_DIR, ...)`.
- **Refactor Proposal:** Modify the internal core engines (which are largely in `intelligence_engine.py`) to accept an explicit `cache_dir` parameter. In `intelligence_service.py`, allow the `db` parameter to be passed explicitly by the benchmark script instead of relying on `Depends`.
- **Risk Level:** **LOW**. Python default arguments natively support passing explicit `db` objects instead of using `Depends()` when called outside FastAPI.

### 3.3 `intelligence_engine.py`
- **Current Issue:** The intelligence engine uses hardcoded `os.path.join(UPLOAD_DIR, ...)` to load `.md` and cache files.
- **Refactor Proposal:** Pass a `working_dir` or `cache_dir` string to `generate_intelligence_report` and `load_workspace_caches`.
- **Risk Level:** **LOW**. Pure code reorganization.

---

## SECTION 4 — LLAMAPARSE MODE CONFIGURABILITY

### 4.1 Cleanest Configuration Method
Modify `ingest_document` to accept a `parsing_config: dict`. The FastAPI route will pass a default dictionary `{"premium_mode": "false", "result_type": "markdown"}`. The benchmark CLI will inject values from a local config file.

### 4.2 Premium Mode Defaults
Production should remain `premium_mode=false` for now. **Trade-offs:** Premium mode is significantly more expensive per page, requires longer latency, and consumes premium API quota rapidly. We should only flip production to true *after* the benchmark framework proves mathematically that the accuracy delta justifies the 10x cost increase.

### 4.3 Other Configurable Parameters
According to LlamaParse vendor docs, we should expose:
- `parsing_instruction` (str): Custom prompt to guide the extraction structure.
- `language` (str): Forces OCR language (e.g., `"en"`).
- `vendor_multimodal_api_key` (str): Allows routing images to GPT-4o for complex chart/table parsing.
- `disable_ocr` (bool): Force text-layer only extraction for speed.

### 4.4 Parsing Health Score
To detect silent degradation between basic and premium:
- **Markdown Size Ratio:** `len(md) / len(raw_pdf_text)`.
- **Table Count:** `md_text.count("|---|")`.
- **Heading Hierarchy:** Ratio of `#` vs `##` tags.
- **Garbage Character Ratio:** Count of `[^\w\s\.,;:!?\-\(\)\[\]\{\}"'\|#\*/\]` vs total length.

---

## SECTION 5 — ISOLATION FROM PRODUCTION

### 5.1 Pinecone Isolation
The benchmark CLI will generate a unique UUID namespace (e.g., `benchmark-run-202605081430`) and pass it down the pipeline. `index.upsert(vectors=..., namespace=namespace_id)`. Code guard: If `is_benchmark=True`, an exception is raised if `namespace` is empty or equals the production default.

### 5.2 PostgreSQL Isolation
Use an in-memory SQLite database (`sqlite:///:memory:`) initialized via SQLAlchemy's `Base.metadata.create_all(bind=engine)` at the start of the benchmark. This guarantees absolute isolation, 0 latency, and auto-cleanup.

### 5.3 Filesystem Isolation
The refactored services will accept an `upload_dir` argument. The benchmark will pass `benchmarks/runs/{run_id}/docs/` instead of the global `config.UPLOAD_DIR`. This physically sandboxes all intermediate writes.

### 5.4 Cost Controls
- **Rate Limits:** Implement a semaphore or simple `asyncio.sleep` throttle between external API calls.
- **Circuit Breaker:** The benchmark CLI tracks cumulative token usage. If `cumulative_cost > $10.00`, it immediately raises a `CostThresholdExceededError` and aborts.

---

## SECTION 6 — SEED CORPUS AND GIT HYGIENE

### 6.1 Starter Corpus Organization
```text
benchmarks/inputs/
  bootlegger_n1_franchise.pdf
  bootlegger_n1_lease.pdf
  bootlegger_rosmead_lease.pdf
  bootlegger_rosmead_franchise.pdf
  bootlegger_eikestad_lease.pdf
  bootlegger_eikestad_franchise.pdf
  control_digital_standard_lease.pdf
  control_scanned_legacy_lease.pdf
```

### 6.2 Version Control for Confidential PDFs
**Proposal:** Do NOT store real lease PDFs in git or git-lfs. They contain sensitive client PI. 
Store the benchmark corpus in an encrypted AWS S3 bucket. Include a simple `benchmarks/sync_corpus.py` script that downloads them locally using AWS SSO credentials. `benchmarks/inputs/*.pdf` must be strictly listed in `.gitignore`.

### 6.3 Gitignore Patterns
```gitignore
# Local benchmark artefacts
benchmarks/inputs/*.pdf
benchmarks/runs/*
!benchmarks/runs/.keep

# Exceptions for golden runs
!benchmarks/runs/golden_v1.0/*
```

### 6.4 Golden Runs
Yes, `benchmarks/runs/` should be ignored, EXCEPT for designated "golden runs" which represent the approved production baseline. These are committed (without the raw `.pdf` files, only the `.md` and `.json` outputs) so regression tests can diff against them in CI.

---

## SECTION 7 — DETERMINISM, TEMPERATURE, AND RUN COMPARISON

### 7.1 Current Groq Temperature Audit
- `intelligence_service.py:60` (`analyze_document_brief_background`): `temperature=0.1`
- `intelligence_service.py:231, 367, 572, 1312`: `temperature=0.0`
- `intelligence_engine.py:63, 311`: `temperature=0.0`
The vast majority of extraction pipelines strictly use `temperature=0.0`.

### 7.2 Temperature Recommendation
Benchmark runs MUST force `temperature=0.0` across the entire pipeline. Determinism is required to diff extraction runs; otherwise, semantic variance makes automated regressions impossible to detect. 

### 7.3 Comparing Non-Deterministic Results
Even at `T=0.0`, API changes or network routing can occasionally induce slight variance. A fair comparison script should check for exact matches, but allow N=3 runs if variance is detected.

### 7.4 Equivalence Rules
- **Numeric/Dates:** Exact ISO matching required. `2024-01-01` vs `2024-01-01`.
- **Enums/Types:** Exact string matching required.
- **Evidence Quotes:** Allowed a 10% Levenshtein distance variance, provided the core clause numbers remain identical.
- **Regression:** A field goes from `extracted` to `null`, or an ISO date changes fundamentally.

---

## SECTION 8 — OBSERVABILITY AND TRACING

### 8.1 Per-Document Trace Log
`trace.log` will capture:
- Timestamp of stage entry/exit.
- Exact vendor payloads (excluding massive prompt text to save space).
- Number of chunks generated.
- Token usage headers from HTTP responses.

### 8.2 Prompt Capture
Yes. Prompts will be saved to `docs/{doc_id}/prompts/` as individual JSON or txt files: `prompt_expiries.txt`, `prompt_fundamental.txt`. This allows debugging hallucinations line-by-line.

### 8.3 Lineage Correlation
Modify the intelligence engine to inject an `extraction_trace_id` alongside the output values. This ID maps directly to the specific prompt file and markdown chunk index that produced the answer. 

---

## SECTION 9 — FAILURE MODES AND THEIR HANDLING

### 9.1 LlamaParse 5xx / Timeout
Catch `requests.exceptions.HTTPError`. Log `[ERROR] LlamaParse failed for {doc}` in the manifest. Move to the next document. Do NOT crash the entire benchmark suite.

### 9.2 Groq Rate Limit (429)
Implement `tenacity` library retries. Backoff exponentially (2s, 4s, 8s). If it fails 3 times, fail loudly and abort the run (rate limits imply systemic queue issues, not a bad document).

### 9.3 Voyage Rate Limit
Same as Groq. Retry with backoff, abort if persistent.

### 9.4 Pinecone Unavailable
Fail loudly and immediately abort.

### 9.5 Malformed JSON from LLM
The validator will catch it. Log as `[ERROR] Malformed output for {field}` inside the output JSON. Mark the field as `null`. Continue pipeline. This is a legitimate extraction failure we *want* the benchmark to catch.

### 9.6 Disk Space Exhausted
Fail loudly. `OSError` will crash the CLI.

### 9.7 Host Machine Sleeps
Network requests will timeout. Handled by standard HTTP timeout wrappers (fail document, continue).

---

## SECTION 10 — INTEGRATION WITH FUTURE EVAL FRAMEWORK

### 10.1 Schema Contract
The benchmark must output a `workspace_summary.json` structured as:
```json
{
  "run_id": "2026-05-08_14-30-00",
  "documents": {
    "doc_n1": {
      "expiries": { "commencement_date": "2025-10-01" },
      "fundamental_terms": { "escalation_rate": "8%" }
    }
  }
}
```

### 10.2 Eval Diffing Approach
The future Eval framework will ingest two `workspace_summary.json` files and compute a deterministic diff. Any field mismatch is flagged. The LLM-as-judge is only invoked when strings mismatch but might be semantically identical (e.g., "Five Percent" vs "5%").

### 10.3 Eval API Surface
The eval framework only needs:
1. `benchmarks.runner.get_latest_run()` -> path string.
2. The schema of `workspace_summary.json` to remain completely backwards-compatible with the production `ExtractionFieldOverride` payload format.

---

## SECTION 11 — IMPLEMENTATION TICKET PREVIEW

### IMPL-EXT-003a: Production code refactor
- **Scope:** Introduce `cache_dir` params to engines. Extract `ingest_document` from FastAPI route.
- **Time:** 1 hour.
- **Risk:** Low. Reversible via standard git revert.

### IMPL-EXT-003b: Local benchmark harness skeleton
- **Scope:** Build `run.py`. Implement in-memory SQLite setup. Implement dummy iteration over inputs.
- **Time:** 2 hours.

### IMPL-EXT-003c: LlamaParse mode & Config isolation
- **Scope:** Build JSON config loader. Pipe `premium_mode` through to the LlamaParse `requests.post` call.
- **Time:** 1 hour.

### IMPL-EXT-003d: Observability & Artifact writing
- **Scope:** Write logic to dump `manifest.json`, `cost_summary.json`, and prompt text.
- **Time:** 2 hours.

### IMPL-EXT-003e: Seed corpus sync script
- **Scope:** Write `sync_corpus.py` (boto3) and update `.gitignore`.
- **Time:** 1 hour.

### IMPL-EXT-003f: End-to-end smoke test
- **Scope:** Run the 6 documents on `premium=false`, review logs, declare victory.
- **Time:** 1 hour.

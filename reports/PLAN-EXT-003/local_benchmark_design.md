# Local Benchmark Environment Design Proposal
## Ticket: PLAN-EXT-003-REV1

### Revision History
- **REV1**: Revisions to cost controls (5.4), Pinecone isolation guards (5.1), determinism & equivalence rules (7.3, 7.4), seed corpus storage phases (6.2), realistic implementation estimates (11), parsing health score (4.4), plus new sections for Secrets Management (12), CI Integration (13), and Schema Versioning (14).

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
To deeply detect degradation without circular dependencies, the benchmark produces a per-document parsing health record.

```json
  "parsing_health": {
    "pages_total": 45,
    "pages_with_extractable_text": 45,
    "characters_total": 108122,
    "characters_per_page_min": 150,
    "characters_per_page_max": 4200,
    "characters_per_page_median": 2100,
    "tables_detected": 4,
    "headings_detected": 15,
    "annexures_referenced": 4,
    "schedules_referenced": 0,
    "definitions_section_present": true,
    "docusign_envelopes_detected": 2,
    "garbled_char_runs": 0,
    "single_letter_word_count": 12,
    "suspected_ocr_artifacts": 3
  }
```

**Computation Rules:**
- `pages_total`: Computed by invoking the lightweight external binary `pdfinfo`.
- `pages_with_extractable_text`: Use `pdftotext` to check if a text layer natively exists per page.
- `characters_per_page`: Derived from splitting the LlamaParse markdown by its `<!-- PAGE X START -->` tags.
- `tables_detected`: Count markdown tables `|---|`.
- `headings_detected`: Regex count of `# ` to `#### ` markers in the markdown.
- `garbled_char_runs`: Regex `[^\x00-\x7F]{3,}` or sequences of `�` on the markdown.
- `single_letter_word_count`: Regex `\b[a-zA-Z]\b`. Spikes indicate OCR spacing failures.
- `annexures_referenced`: Case-insensitive regex count for "annexure".
- `schedules_referenced`: Case-insensitive regex count for "schedule".
- `definitions_section_present`: True if heading "definitions" or "interpretation" is found.
- `docusign_envelopes_detected`: Regex count of "DocuSign Envelope ID".
- `suspected_ocr_artifacts`: Heuristic count of weird symbols often produced by bad OCR.

**Degraded Threshold Definition:**
A parse is flagged as "Degraded" for human review if ANY of the following are met:
1. `characters_total` < `(pages_total * 200)` (indicates massive dropouts).
2. `garbled_char_runs` > 5 (indicates bad OCR charset).
3. `single_letter_word_count` > `(characters_total * 0.05)` (indicates total spacing failure).
4. `definitions_section_present` == false (for commercial leases > 15 pages, this is highly suspicious).

---|")`.
- **Heading Hierarchy:** Ratio of `#` vs `##` tags.
- **Garbage Character Ratio:** Count of `[^\w\s\.,;:!?\-\(\)\[\]\{\}"'\|#\*/\]` vs total length.

---

## SECTION 5 — ISOLATION FROM PRODUCTION

### 5.1 Pinecone Isolation
To ensure the benchmark never pollutes production Pinecone, we enforce a defense-in-depth isolation approach:

1. **Production Guard (`index.upsert` wrapper):** Must assert that the configured namespace EXACTLY matches the production environment constant. If not, raise `ProductionNamespaceViolation`.
2. **Benchmark Guard:** Must assert that the namespace starts with the prefix `"benchmark-"`. If the production namespace is passed, raise `BenchmarkNamespaceViolation`.
3. **Lowest-Layer Enforcement:** Both assertions must live inside the centralized Pinecone client wrapper/dependency (`dependencies.py` or equivalent), ensuring no upstream caller can bypass them.
4. **Cleanup Step:** The `benchmarks/run.py` harness MUST call `index.delete(namespace="benchmark-{run_id}")` at the end of every run. If this API call fails, the `manifest.json` logs `cleanup_failed: true`.
5. **Billing Impact:** Pinecone bills by compute/storage pods, not strictly by namespace existence. However, accumulated vectors in abandoned namespaces consume index storage capacity, potentially forcing a costly pod upgrade. Cleanup is mandatory.
6. **Orphan Sweeper:** A periodic cron task (e.g., weekly) will list all namespaces via the Pinecone API, filter for `benchmark-*`, and execute `index.delete` for any namespace older than 7 days.

**Assertion Contract:**
```python
def safe_upsert(vectors, namespace):
    if is_production():
        assert namespace == PROD_NAMESPACE, "ProductionNamespaceViolation"
    else:
        assert namespace.startswith("benchmark-"), "BenchmarkNamespaceViolation"
    index.upsert(vectors=vectors, namespace=namespace)
```

### 5.2 PostgreSQL Isolation
Use an in-memory SQLite database (`sqlite:///:memory:`) initialized via SQLAlchemy's `Base.metadata.create_all(bind=engine)` at the start of the benchmark. This guarantees absolute isolation, 0 latency, and auto-cleanup.

### 5.3 Filesystem Isolation
The refactored services will accept an `upload_dir` argument. The benchmark will pass `benchmarks/runs/{run_id}/docs/` instead of the global `config.UPLOAD_DIR`. This physically sandboxes all intermediate writes.

### 5.4 Cost Controls
We use a deterministic, model-backed cost control system tracked in real-time.

**5.4.1 Cost Model**
*Prices cited as of May 2026:*
- **LlamaParse:** Basic is $0.003 / page. Premium is $0.01 / page.
- **Groq (llama-3.3-70b):** $0.59 / 1M input tokens. $0.79 / 1M output tokens.
- **Voyage (voyage-law-2):** $0.12 / 1M tokens.
- **Pinecone:** Serverless reads/writes cost ~$0.002 per 1000 operations.

**5.4.2 Pre-flight Projection**
Before any API calls, the benchmark CLI projects the maximum cost:
- Runs `pdfinfo` to count pages -> calculates LlamaParse cost.
- Estimates tokens based on average 4.5 characters per token ratio (OpenAI standard heuristic).
- Calculates maximum Voyage token spend.
- Prints projection to CLI. If the projection > $5 USD, pauses and requires explicit operator `[Y/n]` confirmation.

**5.4.3 In-flight Tracking**
Tracking is accumulated progressively. The harness records costs immediately after receiving API responses. The run can abort cleanly between documents to save incurred costs.

**5.4.4 Per-vendor Caps**
Configuration in `benchmark_config.json`:
```json
"cost_caps_usd": {
  "llamaparse": 3.00,
  "groq": 5.00,
  "voyage": 1.00,
  "pinecone": 0.50,
  "total": 8.00
}
```
If cumulative tracked spend crosses any cap, `CostThresholdExceededError` aborts the remaining documents.

**5.4.5 Output Summary**
`cost_summary.json` logs the actual spend vs. projected spend per vendor and per document. A discrepancy > 1.5x on any vendor triggers an explicit warning log.

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
Real lease PDFs contain sensitive PI and must NEVER be committed to Git or Git LFS.

**Phase 1 (Current: 6-15 documents):**
- Documents are manually placed in a local directory `~/.rem-leases-benchmarks/inputs/` (outside the repo).
- A Git-tracked manifest at `benchmarks/inputs/MANIFEST.txt` specifies the expected filenames and SHA256 hashes.
- If the local files' SHA256 hashes don't perfectly match the manifest, the benchmark explicitly refuses to run.

**Phase 2 (15-100 documents):**
- When the corpus grows beyond what is easily shareable securely (e.g., via 1Password), documents move to a private encrypted AWS S3 bucket (or R2, Backblaze, encrypted Dropbox).
- A `sync_corpus.py` script authenticates via AWS SSO and mirrors the bucket into the local inputs folder.

**Phase 3 (100+ documents):**
- Full secrets-managed pipeline with rigorous access auditing (out of scope for this design).

*We will proceed with Phase 1 for this implementation.*

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
- **Default Check:** The standard benchmark does `N=1` run per config, forces `temperature=0.0`, and uses a fixed `seed` where supported by Groq.
- **Determinism Check Mode:** Periodically (e.g., weekly), an operator passes `--determinism-check` to run `N=3` times.
- **Variance Logging:** If `--determinism-check` finds ANY extraction variance across the 3 runs, it does not silently pick a median. It writes a `variance_report.json` logging the exact fields, runs, and differing values, throwing a loud warning flag.

### 7.4 Equivalence Rules
- **Exact Match Required:** Numeric fields, dates, currencies, percentages, addresses, registration numbers, and party names MUST match EXACTLY (after whitespace trimming/normalization).
- **Evidence Quotes:** MUST match EXACTLY (100% char-for-char). If an LLM reformats a quote by dropping commas or correcting grammar, it is a regression.
- **Free-Text Fields:** Summaries and recommendations are evaluated for semantic equivalence by an LLM-as-judge. Levenshtein distance is strictly prohibited for legal text.
- **Regression Severity Definitions:**
  - **CRITICAL:** A previously extracted non-null value becomes `null`.
  - **HIGH:** An extracted value changes (e.g. `2025-10-01` -> `2025-10-02`).
  - **MEDIUM:** Extraction value is identical, but confidence score drops by > 0.2.
  - **LOW:** Semantic difference detected in a free-text field.

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

We will execute IMPL-EXT-003 in independently reviewable and deployable sub-tickets. Estimates account for implementation, unit/smoke testing, code review, documentation, and rollback verification.

### IMPL-EXT-003a: Production Code Refactor
- **Scope:** Extract `cache_dir` params to decouple `intelligence_engine.py` from `UPLOAD_DIR`. Extract pure file-processing function from FastAPI route in `ingestion_service.py`. Implement Pinecone lowest-layer isolation assertions.
- **Time Estimate:** 4-6 hours (High rigor required for production I/O changes).

### IMPL-EXT-003b: Local Benchmark Harness & Storage
- **Scope:** Build `run.py` CLI. Setup ephemeral SQLite database seeding. Enforce input SHA256 manifest checks (Phase 1 corpus).
- **Time Estimate:** 4-6 hours.

### IMPL-EXT-003c: Orchestration, Cost, & Config Isolation
- **Scope:** Pipe `premium_mode` configurations. Implement the `cost_summary.json` logic, Pre-flight Projection, and real-time vendor spend caps. 
- **Time Estimate:** 6-8 hours.

### IMPL-EXT-003d: Observability, Trace, & Health Score
- **Scope:** Implement the `trace.log`, Prompt captures, and the `parsing_health` record calculation using `pdfinfo`.
- **Time Estimate:** 4-6 hours.

### IMPL-EXT-003e: Determinism & Smoke Test
- **Scope:** Implement the `--determinism-check` logic. Generate `workspace_summary.json` with `schema_version`. Run the full end-to-end smoke test on the local corpus.
- **Time Estimate:** 4-5 hours.


---

## SECTION 12 — SECRETS MANAGEMENT

### 12.1 Key Provenance
**Recommendation:** We will use **Separate development keys** exclusively. 
Using production keys risks polluting production billing metrics, exposing enterprise quotas to local loops, and hitting rate limits that crash the live platform.

### 12.2 Injection Strategy
Keys are provided exclusively via a local `.env` file (strictly `gitignored`). This scales well for our current team size and avoids the overhead of AWS Secrets Manager for local workstation testing.

### 12.3 Manifest Logging
The `manifest.json` will NEVER record key values. It will record:
- Used Environment Variables: `["GROQ_API_KEY", "LLAMA_CLOUD_API_KEY"]`
- Fingerprints: `sha256(key)[:8]` to allow debugging if a run failed due to a rotated/stale key without exposing the secret.

### 12.4 Key Rotation Hygiene
Rotating a key does **not** invalidate golden runs. The golden run evaluates the system's deterministic logic. If the underlying LLM weights haven't changed (because we pin model versions like `llama-3.3-70b`), the API key itself has no bearing on outputs.

---

## SECTION 13 — CI INTEGRATION PLAN

### 13.1 CI Provider
GitHub Actions.

### 13.2 Workflow Structure
- `.github/workflows/benchmark-smoke.yml`: Triggers on PR to `main`. Runs a subset of 3 critical documents. Fails the build if any CRITICAL or HIGH regression occurs against the Golden Run.
- `.github/workflows/benchmark-full.yml`: Triggers nightly via cron. Runs the full benchmark corpus and commits `workspace_summary.json` to a dedicated `benchmark-results` branch (or posts a slack webhook summary).

### 13.3 CI Corpus Procurement
In Phase 1, the CI workflow will decrypt an encrypted ZIP file containing the corpus (using a repository secret as the decryption key). This keeps the raw PDFs out of standard source control while allowing CI native access.

### 13.4 CI Secrets
GitHub Repository Secrets will supply: `DEV_GROQ_API_KEY`, `DEV_LLAMA_CLOUD_API_KEY`, `DEV_VOYAGE_API_KEY`.

### 13.5 CI Cost Caps
A strict budget cap configuration of **$3.00 USD total per run** will be passed to the CLI inside GitHub actions. If it exceeds this, the CI step safely aborts and fails.

### 13.6 Merge Blockers
- **CRITICAL / HIGH Regression:** Blocks PR merge automatically.
- **MEDIUM Regression:** Requires an explicit PR review approval specifically citing "Approved confidence drop".
- **LOW Regression:** Will not block merge, but will output as a warning annotation in the GitHub PR UI.

---

## SECTION 14 — OUTPUT SCHEMA VERSIONING

### 14.1 Embedded Schema Keys
Every output JSON artifact (`manifest.json`, `cost_summary.json`, `workspace_summary.json`, `intelligence_report.json`) must include a root-level `"schema_version": "1.0.0"`.

### 14.2 Versioning Policy
**Semantic Versioning (SemVer)**. 
- Major (1.x): Breaking schema changes.
- Minor (x.1): Additive fields.
- Patch (x.x.1): Typo fixes or description changes.

### 14.3 Breaking vs Additive Changes
- **Breaking:** Renaming an existing key, nesting previously flat fields, changing a data type (e.g., date string to unix timestamp), or removing a field.
- **Additive:** Adding a new metric to `parsing_health` or adding a new field to extract in `fundamental_terms`.

### 14.4 Migration Policy
When a major `schema_version` bumps (e.g., v1 -> v2), the operator must explicitly trigger a pipeline re-baseline by running `make benchmark --baseline-run`. Old golden runs will fail parsing validation if an eval tries to diff v1 against v2. We do NOT write automated schema migration scripts for JSON dumps; we just re-run the pipeline to generate fresh truth.

### 14.5 Canonical Definition
Pydantic models housed within `lexichat-api/models/schemas.py` or a dedicated `benchmarks/schemas/` module will serve as the canonical definitions, providing automatic JSON-Schema generation and runtime validation during benchmark output generation.

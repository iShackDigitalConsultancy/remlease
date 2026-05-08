from benchmarks import _bootstrap  # noqa: F401
import os
import sys

# Ensure lexichat-api is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lexichat-api")))

import argparse
from datetime import datetime, timezone
from benchmarks.harness.manifest import ManifestBuilder
from benchmarks.harness.sqlite_session import ephemeral_session
from benchmarks.harness.pinecone_namespace import mint_benchmark_namespace, cleanup_benchmark_namespace
from benchmarks.harness.orchestrator import process_documents
from dependencies import index

def main():
    parser = argparse.ArgumentParser(description="REM-Leases Local Benchmark Harness")
    parser.add_argument("--input-dir", type=str, default="benchmarks/inputs/", help="Path to input directory")
    parser.add_argument("--output-root", type=str, default="benchmarks/runs/", help="Path to output root directory")
    parser.add_argument("--run-tag", type=str, default="default", help="Tag for the run")
    parser.add_argument("--skip-embeddings", action="store_true", default=True, help="Skip embeddings (must be True for 003b)")
    parser.add_argument("--no-skip-embeddings", dest="skip_embeddings", action="store_false", help="Do not skip embeddings (Disabled)")
    parser.add_argument("--doc-limit", type=int, default=None, help="Cap the number of documents to process")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Validate config and inputs but do not execute APIs")
    
    args = parser.parse_args()

    if not args.skip_embeddings:
        raise NotImplementedError(
            "--skip-embeddings=False is not supported in IMPL-EXT-003b. "
            "Real Pinecone integration with namespace isolation is "
            "implemented in IMPL-EXT-003c. See PLAN-EXT-003-REV1 "
            "Section 5.1 for the design."
        )

    timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_id = f"{timestamp_iso}_{args.run_tag}"
    run_dir = os.path.join(args.output_root, run_id)
    os.makedirs(run_dir, exist_ok=True)
    
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory {args.input_dir} does not exist.")
        sys.exit(1)
        
    pdf_files = [f for f in os.listdir(args.input_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"Error: No PDF files found in {args.input_dir}.")
        sys.exit(1)
        
    print("MANIFEST verification skipped \u2014 implemented in 003e")
    
    # Get git commit hash
    git_commit = "unknown"
    try:
        import subprocess
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("ascii").strip()
    except Exception:
        pass

    started_at = datetime.now(timezone.utc)
    
    manifest_builder = ManifestBuilder(
        run_id=run_id,
        run_tag=args.run_tag,
        started_at=started_at,
        git_commit=git_commit,
        input_dir=args.input_dir,
        output_dir=run_dir,
        doc_limit=args.doc_limit,
        skip_embeddings=args.skip_embeddings,
        dry_run=args.dry_run
    )
    
    if args.dry_run:
        manifest_builder.finish(datetime.now(timezone.utc), 0.0)
        print(f"Dry run completed successfully. Output in {run_dir}")
        sys.exit(0)

    namespace = mint_benchmark_namespace(run_id)
    
    try:
        with ephemeral_session() as db:
            llamaparse_config = {"premium_mode": "false", "result_type": "markdown"}
            
            process_documents(
                input_dir=args.input_dir,
                run_dir=run_dir,
                db=db,
                manifest_builder=manifest_builder,
                doc_limit=args.doc_limit,
                skip_embeddings=args.skip_embeddings,
                llamaparse_config=llamaparse_config
            )
            
    except Exception as e:
        print(f"Run failed fatally: {e}")
        raise
    finally:
        # Cleanup pinecone
        cleanup_result = cleanup_benchmark_namespace(index, namespace)
        manifest_builder.update_pinecone_cleanup(
            attempted=True,
            succeeded=cleanup_result["cleaned"],
            error=cleanup_result["error"]
        )
        
        manifest_builder.finish(
            completed_at=datetime.now(timezone.utc),
            wall_clock_seconds=(datetime.now(timezone.utc) - started_at).total_seconds()
        )
        print(f"Run {run_id} completed. Output in {run_dir}")

if __name__ == "__main__":
    main()

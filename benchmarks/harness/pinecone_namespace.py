"""
Pinecone Namespace Helpers

Production data is never touched by this module. The production namespace 
is rejected by safe_upsert / safe_query at the dependencies.py layer 
if used inappropriately.
"""

def mint_benchmark_namespace(run_id: str) -> str:
    """
    Returns a benchmark-specific namespace for Pinecone isolation.
    """
    return f"benchmark-{run_id}"

def cleanup_benchmark_namespace(index, namespace: str) -> dict:
    """
    Cleans up all vectors within the benchmark namespace.
    If the cleanup fails, it catches the exception and returns the error string.
    """
    try:
        index.delete(delete_all=True, namespace=namespace)
        return {"namespace": namespace, "cleaned": True, "error": None}
    except Exception as e:
        return {"namespace": namespace, "cleaned": False, "error": str(e)}

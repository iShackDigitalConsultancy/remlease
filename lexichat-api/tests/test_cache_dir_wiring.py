import tempfile
import asyncio
from pathlib import Path
import pytest
from services import intelligence_service
from dependencies import UPLOAD_DIR
import inspect

class DummyPayload:
    def __init__(self):
        self.doc_id = "test_doc"
        self.doc_ids = ["test_doc"]
        self.policy = "test"
        self.force_refresh = False
        self.doc_id_a = "doc_a"
        self.doc_id_b = "doc_b"

class DummyRequest:
    pass

class DummyUser:
    id = "test_user"
    firm_id = "test_firm"

class DummyDoc:
    def __init__(self):
        self.workspace_id = "test_workspace"
        self.pinecone_doc_id = "test_doc"
        self.id = "test_doc"
        self.filename = "test.pdf"

class DummyWorkspace:
    id = "test_workspace"
    firm_id = "test_firm"

class DummyDB:
    def query(self, model, *args, **kwargs):
        class DummyQuery:
            def join(self, *args, **kwargs): return self
            def filter(self, *args, **kwargs): return self
            def first(self): 
                if model.__name__ == "Workspace":
                    return DummyWorkspace()
                return DummyDoc()
            def all(self): 
                if model.__name__ == "Workspace":
                    return [DummyWorkspace()]
                return [DummyDoc()]
        return DummyQuery()

FUNCTIONS_TO_TEST = [
    (intelligence_service.analyze_document_brief, ["test_doc", "test.pdf", "sample text"]),
    (intelligence_service.get_document_brief, ["test_doc"]),
    (intelligence_service.document_audit, [DummyPayload()]),
    (intelligence_service.extract_timeline, [DummyPayload()]),
    (intelligence_service.extract_expiries, [DummyPayload()]),
    (intelligence_service.portfolio_overview, []),
    (intelligence_service.document_compare, [DummyPayload()]),
    (intelligence_service.chat_with_pdf, [DummyRequest()])
]

@pytest.mark.parametrize("func_info", FUNCTIONS_TO_TEST)
def test_cache_dir_wiring(func_info):
    func, positional_args = func_info
    db = DummyDB()
    user = DummyUser()
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            # We expect this to fail gracefully with an HTTPException or return something,
            # but NOT fail with TypeError regarding cache_dir
            # Touch the dummy document so that the functions can find it and don't fail early
            with open(Path(tmp_dir) / "test_doc.md", "w") as f:
                f.write("Dummy text for testing purposes.")
                
            kwargs = {"cache_dir": tmp_dir}
            
            # Also pass current_user and db if in signature to avoid dependency errors
            sig = inspect.signature(func)
            if "current_user" in sig.parameters:
                kwargs["current_user"] = user
            if "db" in sig.parameters:
                kwargs["db"] = db
                
            if inspect.iscoroutinefunction(func):
                asyncio.run(func(*positional_args, **kwargs))
            else:
                func(*positional_args, **kwargs)
        except Exception as e:
            if type(e).__name__ == "TypeError" and "cache_dir" in str(e):
                pytest.fail(f"{func.__name__} does not accept cache_dir kwarg: {e}")
            # We ignore other errors like HTTPException since we just want to test wiring
            pass
            
        # Verify it didn't leak into UPLOAD_DIR
        production_leaked = list(Path(UPLOAD_DIR).glob(f"*test_workspace*")) + list(Path(UPLOAD_DIR).glob(f"*test_doc*"))
        assert len(production_leaked) == 0, f"{func.__name__} leaked files to UPLOAD_DIR"

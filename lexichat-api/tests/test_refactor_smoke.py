import os
import json
from unittest.mock import MagicMock
from services.ingestion_service import ingest_document

def test_ingest_document_smoke():
    with open("tests/fixtures/smoke_test.pdf", "rb") as f:
        pdf_bytes = f.read()
    
    mock_db = MagicMock()
    mock_upload_dir = "tests/fixtures/mock_uploads"
    os.makedirs(mock_upload_dir, exist_ok=True)
    
    doc_id = "test-smoke-id"
    workspace_id = "test-ws"
    
    # Run the extracted pure function
    result = ingest_document(
        pdf_bytes=pdf_bytes,
        doc_id=doc_id,
        workspace_id=workspace_id,
        db=mock_db,
        upload_dir=mock_upload_dir,
        llamaparse_config={"premium_mode": "false", "result_type": "markdown"},
        filename="smoke_test.pdf",
        firm_id_meta="none"
    )
    
    # Assert
    assert result is not None
    assert "status" in result
    
    # Check if files were created in the isolated directory
    assert os.path.exists(os.path.join(mock_upload_dir, f"{doc_id}.pdf"))
    
    # Clean up
    import shutil
    shutil.rmtree(mock_upload_dir)

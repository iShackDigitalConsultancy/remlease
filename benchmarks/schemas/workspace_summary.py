from pydantic import BaseModel

class WorkspaceSummary(BaseModel):
    # Skeleton schema. Full enrichment to be added in IMPL-EXT-003e
    workspace_id: str
    doc_count: int

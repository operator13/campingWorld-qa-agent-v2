"""FastAPI app with broken RBAC — checks role but not resource ownership."""
from fastapi import FastAPI, Depends, HTTPException, Header

app = FastAPI()

# In-memory store for demonstration
DOCUMENTS = {
    1: {"id": 1, "title": "Project Plan", "owner_id": 10, "content": "Secret plan..."},
    2: {"id": 2, "title": "Budget", "owner_id": 20, "content": "Financial data..."},
}


def get_current_user(x_user_id: int = Header(...), x_user_role: str = Header(...)):
    return {"id": x_user_id, "role": x_user_role}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int, user=Depends(get_current_user)):
    """Get a document. Checks that user is authenticated and has 'viewer' role,
    but does NOT check that the user owns or has access to this specific document."""
    if user["role"] not in ("viewer", "editor", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient role")

    doc = DOCUMENTS.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    # BUG: No check that user["id"] == doc["owner_id"] or is in an ACL
    return doc


@app.put("/api/documents/{doc_id}")
def update_document(doc_id: int, content: str, user=Depends(get_current_user)):
    """Update document content. Checks editor role but not ownership."""
    if user["role"] not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient role")

    doc = DOCUMENTS.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    # BUG: Any editor can modify any document regardless of ownership
    doc["content"] = content
    return {"status": "updated"}

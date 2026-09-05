"""Secure file serving with path validation and symlink protection."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
UPLOAD_DIR = Path("/var/app/uploads").resolve()


@app.get("/api/files/{filename:path}")
def download_file(filename: str):
    """Download a file with proper path traversal protection."""
    # Construct and resolve the full path
    requested = (UPLOAD_DIR / filename).resolve()

    # Ensure resolved path is within UPLOAD_DIR (blocks ../ and symlinks)
    if not str(requested).startswith(str(UPLOAD_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")

    # Reject symlinks explicitly
    if requested.is_symlink():
        raise HTTPException(status_code=403, detail="Symlinks not allowed")

    if not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(requested))


@app.post("/api/files/upload")
async def upload_file(filename: str, content: bytes):
    """Upload a file with name sanitization."""
    safe_name = Path(filename).name  # Strip any directory components
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(content)
    return {"status": "uploaded", "filename": safe_name}

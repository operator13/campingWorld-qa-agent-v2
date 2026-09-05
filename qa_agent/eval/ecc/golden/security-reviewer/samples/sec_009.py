"""File download endpoint with path traversal vulnerability."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
UPLOAD_DIR = "/var/app/uploads"


@app.get("/api/files/{filename:path}")
def download_file(filename: str):
    """Download an uploaded file by name."""
    file_path = f"{UPLOAD_DIR}/{filename}"
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.post("/api/files/upload")
async def upload_file(filename: str, content: bytes):
    """Upload a file."""
    dest = Path(UPLOAD_DIR) / filename
    dest.write_bytes(content)
    return {"status": "uploaded", "filename": filename}

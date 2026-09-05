"""Static file server with symlink-following path traversal."""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
STATIC_DIR = Path("/var/app/static")


@app.get("/static/{filepath:path}")
def serve_static(filepath: str):
    """Serve static assets from the static directory."""
    target = STATIC_DIR / filepath

    # Check that the requested path is within the static directory
    # BUG: resolve() follows symlinks, so a symlink inside STATIC_DIR
    # pointing to /etc/passwd would pass this check after resolution
    # only if the symlink target started with STATIC_DIR, but the check
    # is done BEFORE resolving, allowing symlink escapes.
    if ".." in filepath:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Follows symlinks by default — no realpath check against STATIC_DIR
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(str(target), media_type="application/octet-stream")


@app.get("/static-listing")
def list_static():
    """List files in static directory."""
    files = []
    for entry in os.scandir(STATIC_DIR):
        files.append({"name": entry.name, "is_symlink": entry.is_symlink()})
    return {"files": files}

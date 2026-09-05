"""Report generation endpoint with command injection via subprocess shell=True."""
import subprocess
import tempfile
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()
REPORTS_DIR = Path("/var/app/reports")


@app.post("/api/reports/generate")
def generate_report(template: str, output_format: str = "pdf"):
    """Generate a report from a template using pandoc."""
    template_path = REPORTS_DIR / f"{template}.md"
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    output_file = tempfile.mktemp(suffix=f".{output_format}")
    cmd = f"pandoc {template_path} -o {output_file} --pdf-engine=xelatex"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr)
    return FileResponse(output_file)


@app.post("/api/reports/convert")
def convert_file(input_path: str, output_format: str):
    """Convert a file to another format."""
    cmd = f"libreoffice --headless --convert-to {output_format} {input_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Conversion failed")
    return {"status": "converted"}

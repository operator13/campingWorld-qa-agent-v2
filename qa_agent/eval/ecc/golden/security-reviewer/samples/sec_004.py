"""Flask endpoint with XSS via direct HTML interpolation."""
from flask import Flask, request

app = Flask(__name__)


@app.route("/search")
def search():
    query = request.args.get("q", "")
    results = perform_search(query)
    html = f"""
    <html>
    <body>
        <h1>Search results for: {query}</h1>
        <ul>
        {"".join(f"<li>{r}</li>" for r in results)}
        </ul>
    </body>
    </html>
    """
    return html


def perform_search(query: str) -> list[str]:
    """Stub search function."""
    return [f"Result for '{query}' #1", f"Result for '{query}' #2"]


@app.route("/health")
def health():
    return {"status": "ok"}

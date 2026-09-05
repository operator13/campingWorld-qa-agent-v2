"""Flask app with proper HTML escaping using Jinja2 autoescaping."""
from flask import Flask, request, render_template_string
from markupsafe import escape

app = Flask(__name__)

SEARCH_TEMPLATE = """
<!DOCTYPE html>
<html>
<body>
    <h1>Search results for: {{ query }}</h1>
    <ul>
    {% for result in results %}
        <li>{{ result }}</li>
    {% endfor %}
    </ul>
</body>
</html>
"""


@app.route("/search")
def search():
    query = request.args.get("q", "")
    results = perform_search(query)
    return render_template_string(SEARCH_TEMPLATE, query=query, results=results)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "")
    safe_query = escape(query)
    results = perform_search(str(safe_query))
    return {"query": str(safe_query), "results": results}


def perform_search(query: str) -> list[str]:
    return [f"Result for '{query}' #1", f"Result for '{query}' #2"]

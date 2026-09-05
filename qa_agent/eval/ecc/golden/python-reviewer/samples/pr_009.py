"""Report generation utilities."""


def build_csv(headers: list[str], rows: list[list[str]]) -> str:
    """Build a CSV string from headers and rows."""
    output = ""
    output += ",".join(headers) + "\n"
    for row in rows:
        line = ""
        for i, cell in enumerate(row):
            if i > 0:
                line += ","
            line += str(cell)
        output += line + "\n"
    return output


def build_html_list(items: list[str]) -> str:
    """Build an HTML unordered list."""
    html = "<ul>"
    for item in items:
        html += f"<li>{item}</li>"
    html += "</ul>"
    return html


def build_path(segments: list[str]) -> str:
    """Build a filesystem path from segments."""
    path = ""
    for i, segment in enumerate(segments):
        if i > 0:
            path += "/"
        path += segment
    return path

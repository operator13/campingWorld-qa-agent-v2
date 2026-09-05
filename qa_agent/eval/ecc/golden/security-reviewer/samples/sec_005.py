"""Flask app with XSS via Jinja2 safe filter on user input."""
from flask import Flask, request, render_template_string

app = Flask(__name__)

PROFILE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>{{ username }}'s Profile</title></head>
<body>
    <h1>{{ username }}</h1>
    <div class="bio">{{ bio | safe }}</div>
    <div class="joined">Member since {{ joined_date }}</div>
</body>
</html>
"""


@app.route("/profile/<username>")
def profile(username: str):
    user = get_user(username)
    if not user:
        return "Not found", 404
    return render_template_string(
        PROFILE_TEMPLATE,
        username=user["username"],
        bio=user["bio"],
        joined_date=user["joined"],
    )


def get_user(username: str) -> dict | None:
    """Stub: would fetch from DB. Bio is user-controlled content."""
    return {"username": username, "bio": "<b>Hello!</b>", "joined": "2024-01-15"}

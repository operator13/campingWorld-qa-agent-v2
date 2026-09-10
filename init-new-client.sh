#!/usr/bin/env bash
#
# Initialize the QA Agent Framework for a new client.
# Run once after cloning to clear campingworld-specific data
# and configure for your target site.
#
# Usage:
#   ./init-new-client.sh --url https://www.example.com --name "Example Corp"
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

CLIENT_URL=""
CLIENT_NAME=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --url) CLIENT_URL="$2"; shift 2 ;;
    --name) CLIENT_NAME="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: ./init-new-client.sh --url https://www.example.com --name \"Example Corp\""
      echo ""
      echo "Options:"
      echo "  --url   Target site URL (required)"
      echo "  --name  Client/project name (required)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$CLIENT_URL" || -z "$CLIENT_NAME" ]]; then
  echo "Error: --url and --name are required"
  echo "Usage: ./init-new-client.sh --url https://www.example.com --name \"Example Corp\""
  exit 1
fi

echo "=========================================="
echo "  QA Agent Framework — New Client Setup"
echo "=========================================="
echo "  Client: $CLIENT_NAME"
echo "  URL:    $CLIENT_URL"
echo "=========================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Clear client-specific test data
# ---------------------------------------------------------------------------

echo "[1/7] Clearing test specs and page objects..."
rm -rf tests_generated/*.spec.ts
rm -rf page_objects/*.ts
echo "  ✓ Cleared tests_generated/ and page_objects/"

# ---------------------------------------------------------------------------
# 2. Clear health reports and test results
# ---------------------------------------------------------------------------

echo "[2/7] Clearing health reports and test results..."
rm -rf health-reports/*.json health-reports/*.md
rm -rf test-results/*/
echo "  ✓ Cleared health-reports/ and test-results/"

# ---------------------------------------------------------------------------
# 3. Clear eval reports
# ---------------------------------------------------------------------------

echo "[3/7] Clearing eval reports..."
find qa_agent/eval/reports -name "*.json" -delete 2>/dev/null || true
find qa_agent/eval/reports -name "*.md" -delete 2>/dev/null || true
find qa_agent/eval/ecc/reports -name "*.json" -delete 2>/dev/null || true
echo "  ✓ Cleared qa_agent/eval/reports/ and qa_agent/eval/ecc/reports/"

# ---------------------------------------------------------------------------
# 4. Clear memory files (keep structure)
# ---------------------------------------------------------------------------

echo "[4/7] Resetting memory files..."
for f in memory/*.md; do
  if [[ -f "$f" && "$(basename "$f")" != "README.md" ]]; then
    # Keep header, clear content
    head -3 "$f" > "$f.tmp" 2>/dev/null || echo "# $(basename "$f" .md)" > "$f.tmp"
    mv "$f.tmp" "$f"
  fi
done
rm -rf memory/audit_runs/*.json
rm -rf memory/locators/*
rm -rf memory/retrospectives/*
echo "  ✓ Reset memory/ files"

# ---------------------------------------------------------------------------
# 5. Update playwright.config.ts
# ---------------------------------------------------------------------------

echo "[5/7] Updating playwright.config.ts..."
if [[ -f playwright.config.ts ]]; then
  sed -i.bak "s|baseURL: '.*'|baseURL: '${CLIENT_URL}'|" playwright.config.ts
  rm -f playwright.config.ts.bak
  echo "  ✓ Set baseURL to $CLIENT_URL"
else
  echo "  ⚠ playwright.config.ts not found"
fi

# ---------------------------------------------------------------------------
# 6. Update dashboard domain list and allowed specs
# ---------------------------------------------------------------------------

echo "[6/7] Clearing dashboard domain config..."

# Clear DOMAINS array in app.js (replace with empty placeholder)
if [[ -f qa_agent/dashboard/static/app.js ]]; then
  # Replace the DOMAINS array with an empty one
  python3 -c "
import re
with open('qa_agent/dashboard/static/app.js', 'r') as f:
    content = f.read()
# Replace DOMAINS array
content = re.sub(
    r'const DOMAINS = \[.*?\];',
    'const DOMAINS = [\n    // Add your domains here:\n    // {spec: \"example.spec.ts\", label: \"Example\", tests: 0, critical: false},\n  ];',
    content, flags=re.DOTALL)
with open('qa_agent/dashboard/static/app.js', 'w') as f:
    f.write(content)
"
  echo "  ✓ Cleared DOMAINS array in app.js"
fi

# Clear ALLOWED_SPECS in server.py and worker.py
for f in qa_agent/dashboard/server.py qa_agent/dashboard/worker.py; do
  if [[ -f "$f" ]]; then
    python3 -c "
import re
with open('$f', 'r') as fh:
    content = fh.read()
content = re.sub(
    r'ALLOWED_SPECS = \{[^}]*\}',
    'ALLOWED_SPECS = {\n    # Add your spec filenames here\n}',
    content)
with open('$f', 'w') as fh:
    fh.write(content)
"
  fi
done
echo "  ✓ Cleared ALLOWED_SPECS in server.py and worker.py"

# ---------------------------------------------------------------------------
# 7. Update project metadata
# ---------------------------------------------------------------------------

echo "[7/7] Updating project metadata..."

# Update pyproject.toml name
if [[ -f pyproject.toml ]]; then
  sed -i.bak "s|name = \"qa-agent\"|name = \"qa-agent-$(echo "$CLIENT_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')\"|" pyproject.toml
  rm -f pyproject.toml.bak
fi

# Clear .ecc_eval_status.json
rm -f .ecc_eval_status.json

# Clear screenshots
rm -f screenshots/*.png 2>/dev/null || true

echo "  ✓ Updated project metadata"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Copy your .env file with ANTHROPIC_API_KEY"
echo "  2. Generate test specs for $CLIENT_URL:"
echo "     qa-agent run --source figma:FILE/NODE"
echo "     qa-agent run --source jira:TICKET-123"
echo "  3. Or manually create specs in tests_generated/"
echo "  4. Update DOMAINS in qa_agent/dashboard/static/app.js"
echo "  5. Update ALLOWED_SPECS in server.py and worker.py"
echo "  6. Run: docker compose up -d"
echo "  7. Open: http://localhost:8080"
echo ""

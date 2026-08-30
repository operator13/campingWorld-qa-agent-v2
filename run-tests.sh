#!/bin/bash
# Run Playwright tests, compute health, auto-heal failures, and push to GitHub

TIMESTAMP=$(date +%m_%d_%Y_%H-%M-%S)
DEST="./test-results/${TIMESTAMP}"

# Clean temp dir from previous run
rm -rf ./test-results-tmp

# Run tests (pass through all arguments)
npx playwright test "$@"
EXIT_CODE=$?

# Move results into timestamped folder
if [ -d "./test-results-tmp" ]; then
  mkdir -p "$DEST"
  mv ./test-results-tmp/* "$DEST/" 2>/dev/null
  rm -rf ./test-results-tmp
  echo ""
  echo "Results saved to: ${DEST}"

  # Compute site health score if results.json exists
  if [ -f "$DEST/results.json" ]; then
    python3 -m qa_agent.health "$DEST/results.json" --output "$DEST"

    # Copy health reports to tracked location and push to GitHub
    mkdir -p ./health-reports
    cp "$DEST/health.json" "./health-reports/${TIMESTAMP}.json" 2>/dev/null
    cp "$DEST/health.md" "./health-reports/${TIMESTAMP}.md" 2>/dev/null

    git add ./health-reports/ 2>/dev/null
    git commit -m "Health report: ${TIMESTAMP} — $(python3 -c "
import json
d=json.load(open('$DEST/health.json'))
print(f\"{d['overall_score']*100:.1f}% {d['overall_status']} ({d['total_passed']}/{d['total_tests']} passed)\")
" 2>/dev/null || echo 'unknown')" 2>/dev/null
    git push 2>/dev/null && echo "Health report pushed to GitHub"

    # Self-healing: if tests failed, triage and heal
    if [ $EXIT_CODE -ne 0 ]; then
      echo ""
      python3 -m qa_agent.triage_runner "$DEST/results.json"
    fi
  fi
fi

exit $EXIT_CODE

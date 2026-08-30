#!/bin/bash
# Run Playwright tests, archive results, and compute site health score

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
  fi
fi

exit $EXIT_CODE

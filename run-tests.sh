#!/bin/bash
# Run Playwright tests and archive results into a timestamped folder

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
fi

exit $EXIT_CODE

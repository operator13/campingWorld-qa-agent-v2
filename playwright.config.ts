import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests_generated',
  outputDir: './test-results-tmp/artifacts',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  retries: 1,
  workers: 4,
  reporter: [
    ['html', { open: 'never', outputFolder: './test-results-tmp/html-report' }],
    ['json', { outputFile: './test-results-tmp/results.json' }],
    ['list'],
  ],
  use: {
    baseURL: 'https://www.campingworld.com',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    launchOptions: {
      args: [
        '--disable-session-crashed-bubble',
        '--hide-crash-restore-bubble',
        '--disable-infobars',
        '--no-first-run',
        '--disable-features=InfiniteSessionRestore,TranslateUI',
        '--disable-popup-blocking',
        '--noerrdialogs',
      ],
    },
    storageState: undefined,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});

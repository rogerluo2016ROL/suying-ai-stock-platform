import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: true,
    include: ['src/__tests__/**/*.test.{ts,tsx}', 'tests/sit/**/*.test.{ts,tsx}'],
    // AC-6: 8 AntD Form tests in one file OOM'd the worker (ERR_WORKER_OUT_OF_MEMORY
    // at ~407s) because RTL didn't cleanup() between tests → DOM/components
    // accumulated. Real fix is afterEach(cleanup) in the test; forks pool keeps
    // vitest globals injected (threads/​singleFork broke `beforeAll`); testTimeout
    // surfaces any remaining hang as a clear 20s failure instead of a worker crash.
    pool: 'forks',
    testTimeout: 20000,
    hookTimeout: 20000,
  },
})

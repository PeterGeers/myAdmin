/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(async ({ command }) => {
  // rollup-plugin-visualizer is ESM-only, so dynamic import is needed
  const visualizerPlugin = process.env.ANALYZE
    ? (await import('rollup-plugin-visualizer')).visualizer({
        open: true,
        filename: 'build/stats.html',
        gzipSize: true,
      })
    : null;

  return {
    plugins: [
      react(),
      visualizerPlugin,
    ].filter(Boolean),

    // base path only for production builds (GitHub Pages deploys to /myAdmin)
    // In dev (command === 'serve'), keep '/' so the proxy can intercept /api requests
    base: command === 'build' ? '/myAdmin' : '/',

    // Replace package.json "proxy" field
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://localhost:5000',
          changeOrigin: true,
          timeout: 300000, // 5 minutes for streaming/SSE endpoints
        },
      },
    },

    // Path alias: @/ → ./src/
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },

    // Production build settings
    build: {
      outDir: 'build',
      target: 'es2020',
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: undefined,
        },
      },
    },

    // Vitest configuration
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/setupTests.ts',
      css: true,
      include: ['src/**/*.{test,spec}.{ts,tsx}', 'tests/**/*.{test,spec}.{ts,tsx}'],
      exclude: ['tests/e2e/**', 'node_modules/**', 'build/**'],
      alias: {
        '@chakra-ui/react': path.resolve(__dirname, './src/__mocks__/chakra-ui-react.tsx'),
        '@chakra-ui/icons': path.resolve(__dirname, './src/__mocks__/chakra-ui-icons.tsx'),
      },
      // Worker-pool concurrency cap. The suite (~3660 tests / 264 files) flakily
      // OOM-crashed the nightly Frontend job (JS heap out of memory) with ZERO
      // failing assertions -- a forks worker died, vitest reported it as an
      // unhandled error, reddening the run (e.g. runs #62 2026-10-12 and #64
      // 2026-10-13; #63 2026-10-11 passed with ~the same suite -> intermittent).
      //
      // ROOT CAUSE (measured, not guessed): running the whole suite SEQUENTIALLY in
      // one isolated worker with --logHeapUsage shows per-file retained heap
      // oscillating ~60-380 MB and GC-ing back down every few files -- NO monotonic
      // climb, NO OOM. So there is no cross-file leak; `isolate` already reclaims
      // per-file state. The crash is AGGREGATE CONCURRENCY: the forks pool defaults
      // to one worker per CPU, and on a many-vCPU CI runner N workers each holding
      // 100-400 MB (plus Vite transform/module caches) sum past the heap ceiling.
      // Which worker gets over-committed depends on scheduling -> the flakiness.
      //
      // FIX: cap worker concurrency. NOTE the shape -- this project is on vitest 4,
      // where `test.poolOptions.{forks}` was REMOVED (it prints a DEPRECATED warning
      // and is silently ignored); the knobs are now TOP-LEVEL `maxWorkers`/
      // `minWorkers` (verified against node_modules/vitest config types). An earlier
      // poolOptions.forks.maxForks attempt was a no-op for exactly this reason.
      // 2 workers => ~2 x ~400 MB peak, well under the ceiling; NODE_OPTIONS in CI
      // (.github/workflows/full-test-suite.yml) stays as belt-and-suspenders.
      pool: 'forks',
      maxWorkers: 2,
      minWorkers: 1,
      // isolate (default true in vitest 4) already reclaims per-file module state --
      // the sequential heap trace confirms no cross-file accumulation to fix here.
      isolate: true,
    },
  };
});

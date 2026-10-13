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
      // Worker-pool memory sizing. The suite grew to ~3660 tests / 264 files and a
      // forks worker OOM-crashed the nightly run (JS heap out of memory) with zero
      // failing assertions. Root cause is cross-file memory accumulation inside a
      // reused forks worker (a worker runs a batch of files and heap grows across
      // them), NOT a single pathological file -- so the levers that actually help are:
      //
      //  - isolate: true -- reset each file's module registry/context so module-level
      //    state (the classic leak: a module-level Map/Set that grows per file) does
      //    not pin memory for the whole worker lifetime. This is the primary guard.
      //  - maxForks cap -- bound concurrency so the aggregate heap across workers fits
      //    the runner RAM (the forks pool otherwise spawns one worker per CPU).
      //
      // NOTE on the per-worker heap ceiling: vitest does NOT forward a custom
      // `execArgv` (e.g. --max-old-space-size) to pool workers -- that was verified to
      // be a no-op here (the worker launched without the flag). The worker heap is
      // instead raised via NODE_OPTIONS on the test *process*, which the workers DO
      // inherit; that budget is pinned in CI in .github/workflows/full-test-suite.yml.
      // If accumulation ever outgrows a reasonable NODE_OPTIONS budget, the next
      // structural lever is `fileParallelism: false` (serialise files so a worker
      // recycles) or the `vmForks` pool (vmMemoryLimit recycles a worker when it
      // exceeds the limit) -- deferred because both carry speed / sandbox tradeoffs.
      pool: 'forks',
      poolOptions: {
        forks: {
          // Cap concurrency so total heap across workers stays bounded on
          // high-core CI runners (default = one fork per CPU).
          maxForks: 4,
          minForks: 1,
        },
      },
      // Reset each file's module registry/context between files -- the primary guard
      // against cross-file module-state accumulation in a reused worker.
      isolate: true,
    },
  };
});

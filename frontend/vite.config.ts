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
    },
  };
});

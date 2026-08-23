import { defineConfig } from 'vite';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: __dirname,
  resolve: {
    alias: {
      '@': resolve(__dirname, 'ts'),
    },
  },
  build: {
    // 注意：FastAPI 把 src/frontend/ 挂到 /static/ 路径，
    // bundle 必须输出到 src/frontend/ 才能被 /static/baa-core-bundle.iife.js 命中
    outDir: resolve(__dirname),
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, 'ts/main.ts'),
      formats: ['iife'],
      name: 'BAACore',
      fileName: (format) => `baa-core-bundle.${format}.js`,
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/collab': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
});
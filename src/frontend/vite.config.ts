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
    outDir: resolve(__dirname),
    emptyOutDir: false,
    minify: false, // P125: 开发期可读，方便定位问题
    sourcemap: true, // P125: 保留 source map，前端报错可直接跳到 TS 源码
    target: 'es2020',
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

import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'ts'),
    },
  },
  test: {
    // jsdom 环境：所有测试均可访问 document/window
    environment: 'jsdom',
    include: ['ts/**/*.test.ts'],
    globals: true,
    reporters: 'default',
    setupFiles: [],
    poolOptions: {
      threads: { singleThread: true },
    },
  },
});

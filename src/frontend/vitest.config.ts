import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

// P126: Vitest 配置 — 独立于 vite.config.ts，避免影响构建产物
const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'ts'),
    },
  },
  test: {
    environment: 'node', // 纯函数测试，无需 jsdom
    include: ['ts/**/*.test.ts'],
    globals: false,
    reporters: 'default',
  },
});

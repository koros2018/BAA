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
    // 纯函数测试默认 node 环境
    environment: 'node',
    include: ['ts/**/*.test.ts'],
    globals: false,
    reporters: 'default',
    // jsdom 配置：仅用于需要 DOM 的组件测试
    poolOptions: {
      threads: { singleThread: true },
    },
  },
});

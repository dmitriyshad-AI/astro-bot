import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: resolve(__dirname),
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  base: '/',
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});

import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      '/api': { target: process.env.DEFUSE_API ?? 'http://localhost:8000', changeOrigin: true }
    }
  }
});

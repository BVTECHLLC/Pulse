import { defineConfig } from 'vite';
export default defineConfig({
  base: '/kart/',
  server: {
    host: '0.0.0.0', port: 5173,
    proxy: {'/kart/ws': {target:'ws://localhost:3108', ws:true}, '/kart/health': 'http://localhost:3108'}
  },
  build: {target: 'es2020', outDir: 'dist', sourcemap: false}
});

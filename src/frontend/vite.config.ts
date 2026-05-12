import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // 서버 배포 시 VITE_ENV_DIR 환경변수로 config/ 경로 지정, 로컬은 기본값(.) 사용
  envDir: process.env.VITE_ENV_DIR || '.',
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})

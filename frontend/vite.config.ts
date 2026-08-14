import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // 所有后端 API 路径统一代理（用正则覆盖 chat/auth/user/knowledge/notes/mbti/interview/dashboard/obsidian/models/health 等）
      '^/(chat|auth|user|knowledge|notes|mbti|interview|dashboard|obsidian|models|health)(/.*)?$': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

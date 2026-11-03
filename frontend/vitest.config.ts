import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [react(), VitePWA({ injectRegister: false })],
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], globals: true },
})

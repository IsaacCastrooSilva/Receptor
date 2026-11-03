import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,
      includeAssets: ['logo.png', 'icon-192.png', 'icon-512.png'],
      manifest: {
        id: '/', name: 'Receptor — apoio à comunicação', short_name: 'Receptor',
        description: 'Expresse sua mensagem com texto, frases e voz.',
        lang: 'pt-BR', start_url: '/', scope: '/', display: 'standalone',
        background_color: '#ffffff', theme_color: '#ffffff',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/icon-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}'],
        navigateFallbackDenylist: [/^\/api(?:\/|$)/, /^\/docs/, /^\/openapi\.json/],
        // No runtime caching: uploads, API responses and messages stay out of Cache Storage.
        runtimeCaching: [],
        cleanupOutdatedCaches: true,
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    port: 5173, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  preview: { port: 4173, strictPort: true },
})

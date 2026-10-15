import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({ plugins: [react()], build: { outDir: 'dist-live', rollupOptions: { input: 'live-prototype.html' } } })

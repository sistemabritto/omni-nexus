import { defineConfig, type IndexHtmlTransformContext, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Replaces the __CSP_PLACEHOLDER__ in index.html with a CSP that differs
// between dev and prod. ctx.server is only set when transformIndexHtml runs
// under `vite dev` — never under `vite build` — so this is the one signal
// that reliably tells dev and prod apart at HTML-transform time (unlike
// NODE_ENV, which build tooling doesn't consistently set here).
function cspPlugin(): Plugin {
  return {
    name: 'csp-connect-src',
    transformIndexHtml(html: string, ctx: IndexHtmlTransformContext) {
      const isDev = Boolean(ctx.server)
      const connectSrc = isDev ? "connect-src 'self' ws://localhost:5173" : "connect-src 'self'"
      const csp = [
        "default-src 'self'",
        connectSrc,
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "frame-ancestors 'self'",
        "base-uri 'self'",
      ].join('; ')
      return html.replace('__CSP_PLACEHOLDER__', csp)
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), cspPlugin()],
  server: { proxy: { '/api': 'http://localhost:8080' } }
})

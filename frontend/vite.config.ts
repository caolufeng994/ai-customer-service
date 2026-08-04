import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE 流式支持：http-proxy 默认会缓冲响应体,导致浏览器(及 fetch 客户端)
        // 收不到逐块推送(思考过程/逐字回复一次性到达),表现为"无流式"。
        // 通过 configure 钩子在收到上游响应头时立即 flush,并强制 identity 编码、
        // 关闭缓存与代理缓冲,确保 SSE 帧实时透传给前端。
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            // 关闭 Accept-Encoding,避免任何压缩层对 SSE 分块做整体缓冲
            proxyReq.setHeader('accept-encoding', 'identity')
          })
          proxy.on('proxyRes', (proxyRes, _req, res) => {
            proxyRes.headers['cache-control'] = 'no-cache, no-transform'
            proxyRes.headers['x-accel-buffering'] = 'no'
            proxyRes.headers['content-type'] = 'text/event-stream; charset=utf-8'
            // 关键：收到上游首字节后立即把响应头 flush 给浏览器,
            // 避免 http-proxy 攒齐响应体再发,从而让 SSE 帧实时到达。
            if (typeof (res as any).flushHeaders === 'function') {
              ;(res as any).flushHeaders()
            }
          })
        },
      },
    },
  },
})

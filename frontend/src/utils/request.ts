import axios from 'axios'
import { message } from 'antd'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * 从后端错误响应体中提取可读提示。
 *
 * 后端统一错误信封为 `{"detail": {"code": "...", "message": "..."}}`（见 docs/API文档.md），
 * 参数校验失败（422）则是 FastAPI 默认的 `{"detail": [{loc, msg, type}, ...]}`。
 * 直接读 `data.message` 两种都取不到，会把真实原因（如“账号不存在 / 密码错误”）
 * 吞掉并统一显示为 "Request failed"。
 */
function extractErrorMessage(data: any, fallback = 'Request failed'): string {
  if (!data) return fallback
  const detail = data.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // 422：拼出「字段: 原因」，只取第一条，避免提示过长
    const first = detail[0]
    if (first) {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : ''
      return field ? `${field}: ${first.msg}` : first.msg || fallback
    }
    return fallback
  }
  if (detail && typeof detail === 'object' && detail.message) return detail.message
  return data.message || fallback
}

/**
 * Capture the backend TraceId from response headers so it can be surfaced to users
 * for bug reports. Handles both axios headers (plain object) and fetch Headers (.get()).
 */
function captureTraceId(headers: any): void {
  if (!headers) return
  const traceId = headers['x-trace-id'] ?? headers.get?.('X-Trace-Id')
  if (traceId) lastTraceId = traceId
}

// Response interceptor
request.interceptors.response.use(
  (response) => {
    // Capture the backend TraceId so it can be surfaced to users for bug reports.
    captureTraceId(response.headers)
    const { data } = response
    if (data.success === false) {
      message.error(data.message || 'Request failed')
      return Promise.reject(new Error(data.message || 'Request failed'))
    }
    return data
  },
  (error) => {
    // Capture TraceId even on failure paths.
    captureTraceId(error?.response?.headers)
    if (error.response) {
      const { status, data } = error.response
      const onLoginPage = window.location.pathname.startsWith('/login')
      if (status === 401) {
        // 登录页上的 401 是“账号或密码错误”，不能清 token 并整页跳转：
        // 跳转会重载页面、销毁 antd message，用户只看到页面闪一下、拿不到任何提示。
        if (onLoginPage) {
          message.error(extractErrorMessage(data, 'Invalid phone/email or password'))
        } else {
          message.error('Unauthorized, please login again')
          localStorage.removeItem('token')
          window.location.href = '/login'
        }
      } else if (status === 429) {
        message.error(extractErrorMessage(data, 'Daily quota exceeded'))
      } else {
        const msg = extractErrorMessage(data)
        // 把追踪 ID 一并透出，方便用户反馈时带上，后端据此查全链路。
        message.error(lastTraceId ? `${msg} (追踪ID: ${lastTraceId})` : msg)
      }
    } else {
      message.error('Network error')
    }
    return Promise.reject(error)
  }
)

// Latest TraceId observed from the backend (for copy/paste into the Traces page).
export let lastTraceId: string | null = null
export function getLastTraceId(): string | null {
  return lastTraceId
}

// SSE streaming request
export async function postStream(
  url: string,
  body: any,
  options: {
    onEvent?: (event: any) => void
    onError?: (error: Error) => void
    onDone?: () => void
    headers?: Record<string, string>
    signal?: AbortSignal
  } = {}
) {
  const { onEvent, onError, onDone, headers: customHeaders, signal } = options
  const controller = new AbortController()
  const abortSignal = signal ?? controller.signal
  const token = localStorage.getItem('token')
  
  try {
    const response = await fetch(`/api${url}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
        ...customHeaders,
      },
      body: JSON.stringify(body),
      signal: abortSignal,
    })

    // Capture TraceId from the SSE response headers (chat streaming path).
    captureTraceId(response.headers)

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    
    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('Response body is not readable')
    }
    
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        break
      }
      
      buffer += decoder.decode(value, { stream: true })
      
      // Split by \n\n to get SSE frames
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || '' // Keep incomplete frame in buffer
      
      for (const line of lines) {
        if (line.trim() === '') continue
        
        // Parse SSE format: data: {...}
        const match = line.match(/^data:\s*(.+)$/)
        if (match) {
          try {
            const data = JSON.parse(match[1])
            onEvent?.(data)
          } catch (e) {
            console.error('Failed to parse SSE data:', match[1], e)
          }
        }
      }
    }
    
    onDone?.()
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }
    onError?.(error as Error)
  }
  
  return controller
}

export default request

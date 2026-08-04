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

// Response interceptor
request.interceptors.response.use(
  (response) => {
    const { data } = response
    if (data.success === false) {
      message.error(data.message || 'Request failed')
      return Promise.reject(new Error(data.message || 'Request failed'))
    }
    return data
  },
  (error) => {
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
        message.error(extractErrorMessage(data))
      }
    } else {
      message.error('Network error')
    }
    return Promise.reject(error)
  }
)

// SSE streaming request
//
// 使用 XMLHttpRequest + onprogress 实现流式接收,而非 fetch + ReadableStream。
// 原因:fetch 的响应体在部分浏览器/运行环境下会被整体缓冲(只有连接结束时才一次性
// 交付),导致"思考过程/逐字回复"无法实时呈现、思考与引用来源一闪而过;而 XHR 的
// onprogress 在分块数据到达时即触发,responseText 持续累加,是各浏览器中最稳定的
// 流式方案(尤其适配本项目基于 POST 的 SSE 接口)。
export function postStream(
  url: string,
  body: any,
  options: {
    onEvent?: (event: any) => void
    onError?: (error: Error) => void
    onDone?: () => void
    headers?: Record<string, string>
    signal?: AbortSignal
  } = {}
): Promise<void> {
  const { onEvent, onError, onDone, headers: customHeaders, signal } = options
  const token = localStorage.getItem('token')

  return new Promise<void>((resolve) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api${url}`)
    xhr.setRequestHeader('Content-Type', 'application/json')
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    if (customHeaders) {
      for (const [k, v] of Object.entries(customHeaders)) xhr.setRequestHeader(k, v)
    }

    let offset = 0 // 已消费的 responseText 长度,用于增量截取新增文本
    let buffer = '' // 未解析完的 SSE 帧

    const flushBuffer = () => {
      // 只解析到最后一个完整的 \n\n 分隔帧,剩余不完整的留在 buffer 下次处理
      const sep = buffer.lastIndexOf('\n\n')
      if (sep === -1) return
      const complete = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      for (const frame of complete.split('\n\n')) {
        if (!frame.trim()) continue
        const m = frame.match(/^data:\s*([\s\S]+)$/)
        if (m) {
          try {
            onEvent?.(JSON.parse(m[1]))
          } catch (e) {
            console.error('Failed to parse SSE data:', m[1], e)
          }
        }
      }
    }

    xhr.onprogress = () => {
      // responseText 已累计全部收到内容;截取本次新增部分拼入 buffer 并实时解析。
      // 按 \n\n 边界切片不会切断多字节字符,安全。
      const text = xhr.responseText
      buffer += text.slice(offset)
      offset = text.length
      flushBuffer()
    }

    xhr.onload = () => {
      // 收尾:处理尾部可能残留的帧(后端每个帧均以 \n\n 结尾,通常会被上面的 flush 覆盖)
      const text = xhr.responseText
      buffer += text.slice(offset)
      offset = text.length
      flushBuffer()
      if (xhr.status >= 200 && xhr.status < 300) {
        onDone?.()
      } else {
        onError?.(new Error(`HTTP error! status: ${xhr.status}`))
      }
      resolve()
    }

    xhr.onerror = () => {
      onError?.(new Error('Network error'))
      resolve()
    }

    xhr.onabort = () => {
      resolve()
    }

    if (signal) {
      if (signal.aborted) {
        xhr.abort()
      } else {
        signal.addEventListener('abort', () => xhr.abort(), { once: true })
      }
    }

    xhr.send(JSON.stringify(body))
  })
}

export default request

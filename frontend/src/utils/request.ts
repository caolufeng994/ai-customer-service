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
      if (status === 401) {
        message.error('Unauthorized, please login again')
        localStorage.removeItem('token')
        window.location.href = '/login'
      } else if (status === 429) {
        message.error('Daily quota exceeded')
      } else {
        message.error(data?.message || 'Request failed')
      }
    } else {
      message.error('Network error')
    }
    return Promise.reject(error)
  }
)

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

import { useState, useEffect, useRef } from 'react'
import { Layout, List, Input, Button, Card, Tag, message } from 'antd'
import { SendOutlined, PlusOutlined } from '@ant-design/icons'
import request, { postStream } from '../utils/request'

const { Header, Content, Sider } = Layout

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

interface Session {
  id: number
  title: string
  updated_at: string
}

export default function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSession, setCurrentSession] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const streamingRef = useRef('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingContent])

  const loadSessions = async () => {
    try {
      const response = await request.get('/sessions')
      setSessions(response.data)
      if (response.data.length > 0 && !currentSession) {
        setCurrentSession(response.data[0].id)
        loadMessages(response.data[0].id)
      }
    } catch (error) {
      // Error handled by interceptor
    }
  }

  const loadMessages = async (sessionId: number) => {
    try {
      const response = await request.get(`/sessions/${sessionId}`)
      setMessages(response.data.messages || [])
    } catch (error) {
      // Error handled by interceptor
    }
  }

  const createSession = async () => {
    try {
      const response = await request.post('/sessions', { title: '新对话' })
      setSessions([response.data, ...sessions])
      setCurrentSession(response.data.id)
      setMessages([])
    } catch (error) {
      // Error handled by interceptor
    }
  }

  const sendMessage = async () => {
    if (!input.trim() || !currentSession) return

    const userMessage = input
    setInput('')
    setMessages([...messages, { id: Date.now(), role: 'user', content: userMessage, created_at: new Date().toISOString() }])
    setLoading(true)
    setStreamingContent('')
    streamingRef.current = ''

    try {
      postStream(
        '/chat/stream',
        {
          session_id: currentSession,
          message: userMessage,
          kb_id: 'default',
        },
        {
          onEvent: (event) => {
            if (event.type === 'session_id') {
              setCurrentSession(event.data)
            } else if (event.type === 'status') {
              console.log('Status:', event.data)
            } else if (event.type === 'content') {
              streamingRef.current += event.data
              setStreamingContent(streamingRef.current)
            } else if (event.type === 'done') {
              const assistantMessage = {
                id: event.data.message_id || Date.now() + 1,
                role: 'assistant' as const,
                content: streamingRef.current,
                created_at: new Date().toISOString(),
              }
              setMessages((prev) => [...prev, assistantMessage])
              setStreamingContent('')
              streamingRef.current = ''
              console.log('Done with sources:', event.data.sources)
            } else if (event.type === 'error') {
              message.error(event.data || 'An error occurred')
            }
          },
          onError: (error) => {
            message.error(error.message || 'Stream error occurred')
          },
          onDone: () => {
            setLoading(false)
          },
        }
      )
    } catch (error) {
      message.error('Failed to send message')
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSessions()
  }, [])

  return (
    <Layout>
      <Sider width={250} theme="light">
        <div className="sider-header">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            onClick={createSession}
          >
            New Chat
          </Button>
        </div>
        <List
          dataSource={sessions}
          renderItem={(session) => (
            <List.Item
              onClick={() => {
                setCurrentSession(session.id)
                loadMessages(session.id)
              }}
            >
              <List.Item.Meta
                title={session.title}
                description={new Date(session.updated_at).toLocaleDateString()}
              />
            </List.Item>
          )}
        />
      </Sider>
      <Layout>
        <Header>
          <h2>AI Customer Service</h2>
        </Header>
        <Content>
          <div className="content-container">
            <div className="messages-container">
              {messages.map((msg) => (
                <Card key={msg.id}>
                  <Tag color={msg.role === 'user' ? 'blue' : 'green'}>
                    {msg.role === 'user' ? 'You' : 'AI'}
                  </Tag>
                  <p>{msg.content}</p>
                </Card>
              ))}
              {streamingContent && (
                <Card>
                  <Tag color="green">AI</Tag>
                  <p>{streamingContent}</p>
                </Card>
              )}
              <div ref={messagesEndRef} />
            </div>
            <Input
              placeholder="Type your question..."
              size="large"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={sendMessage}
              disabled={loading}
              suffix={
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={sendMessage}
                  loading={loading}
                >
                  Send
                </Button>
              }
            />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}

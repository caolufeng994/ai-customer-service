import { useState, useEffect, useRef } from 'react'
import { Layout, List, Input, Button, Card, Tag, message, Modal } from 'antd'
import { SendOutlined, PlusOutlined, LikeOutlined, DislikeOutlined } from '@ant-design/icons'
import request, { postStream } from '../utils/request'

const { Header, Content, Sider } = Layout

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sources?: Array<{
    doc_id: number
    chunk_id: string
    score: number
    snippet: string
  }>
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
  const abortRef = useRef<AbortController | null>(null)
  const [feedbackModalVisible, setFeedbackModalVisible] = useState(false)
  const [selectedMessageId, setSelectedMessageId] = useState<number | null>(null)
  const [feedbackType, setFeedbackType] = useState<'like' | 'dislike' | null>(null)
  const [feedbackComment, setFeedbackComment] = useState('')

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
      setSessions((prev) => [response.data, ...prev])
      setCurrentSession(response.data.id)
      setMessages([])
    } catch (error) {
      // Error handled by interceptor
    }
  }

  const handleFeedback = (messageId: number, type: 'like' | 'dislike') => {
    setSelectedMessageId(messageId)
    setFeedbackType(type)
    setFeedbackComment('')
    setFeedbackModalVisible(true)
  }

  const submitFeedback = async () => {
    if (!selectedMessageId || !feedbackType) return

    try {
      await request.post('/feedback', {
        message_id: selectedMessageId,
        rating: feedbackType === 'like' ? 1 : -1,
        comment: feedbackComment
      })
      message.success('Feedback submitted successfully')
      setFeedbackModalVisible(false)
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
      const controller = new AbortController()
      abortRef.current = controller
      postStream(
        '/chat/stream',
        {
          session_id: currentSession,
          message: userMessage,
          kb_id: 'default',
        },
        {
          signal: controller.signal,
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
                sources: event.data.sources,
              }
              setMessages((prev) => [...prev, assistantMessage])
              setStreamingContent('')
              streamingRef.current = ''
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
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  return (
    <Layout>
      <Sider width={280} theme="light">
        <div className="sider-header">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            size="large"
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
              className={currentSession === session.id ? 'active-session' : ''}
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
                <Card key={msg.id} className={msg.role === 'user' ? 'user-message' : 'ai-message'}>
                  <div className="message-header">
                    <Tag color={msg.role === 'user' ? 'blue' : 'green'}>
                      {msg.role === 'user' ? 'You' : 'AI'}
                    </Tag>
                    <span className="message-time">
                      {new Date(msg.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p>{msg.content}</p>
                  {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                    <div className="message-sources">
                      <div className="sources-title">引用来源:</div>
                      {msg.sources.map((source, index) => (
                        <div key={index} className="source-item">
                          <Tag color="blue">相关度: {(source.score * 100).toFixed(1)}%</Tag>
                          <span className="source-snippet">{source.snippet}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.role === 'assistant' && (
                    <div className="message-feedback">
                      <Button
                        type="text"
                        icon={<LikeOutlined />}
                        size="small"
                        onClick={() => handleFeedback(msg.id, 'like')}
                      >
                        有帮助
                      </Button>
                      <Button
                        type="text"
                        icon={<DislikeOutlined />}
                        size="small"
                        onClick={() => handleFeedback(msg.id, 'dislike')}
                      >
                        无帮助
                      </Button>
                    </div>
                  )}
                </Card>
              ))}
              {streamingContent && (
                <Card className="ai-message streaming">
                  <div className="message-header">
                    <Tag color="green">AI</Tag>
                    <span className="message-time">Typing...</span>
                  </div>
                  <p>{streamingContent}</p>
                </Card>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="input-container">
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
                    size="large"
                  >
                    Send
                  </Button>
                }
              />
            </div>
          </div>
        </Content>
      </Layout>

      <Modal
        title="提交反馈"
        open={feedbackModalVisible}
        onOk={submitFeedback}
        onCancel={() => setFeedbackModalVisible(false)}
        okText="提交"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <p>您选择了: {feedbackType === 'like' ? '👍 有帮助' : '👎 无帮助'}</p>
        </div>
        <Input.TextArea
          placeholder="可选：添加您的评论..."
          value={feedbackComment}
          onChange={(e) => setFeedbackComment(e.target.value)}
          rows={4}
        />
      </Modal>
    </Layout>
  )
}

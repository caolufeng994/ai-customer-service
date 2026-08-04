import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Layout, List, Input, Button, Card, Tag, message, Modal } from 'antd'
import { SendOutlined, PlusOutlined, LikeOutlined, DislikeOutlined } from '@ant-design/icons'
import request, { postStream } from '../utils/request'

const { Header, Content, Sider } = Layout

// 答案中的 [K编号] 引用在召回来源中一一对应: [K3] -> sources[k_index=3]。
// 这里把 [K编号] 渲染成可点击的高亮标记, 点击后平滑滚动到对应的来源卡片,
// 实现"引用 -> 来源"的双向绑定, 让用户一眼看清每段结论的出处。
const K_REF_RE = /\[K(\d+)\]/g

function renderAnswer(content: string): ReactNode {
  if (!content) return null
  const parts: React.ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  K_REF_RE.lastIndex = 0
  while ((m = K_REF_RE.exec(content)) !== null) {
    if (m.index > last) parts.push(content.slice(last, m.index))
    const idx = Number(m[1])
    parts.push(
      <span
        key={`k-${m.index}`}
        className="k-ref"
        title="查看引用来源"
        onClick={() => {
          const el = document.getElementById(`source-card-${idx}`)
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }}
      >
        [K{idx}]
      </span>
    )
    last = m.index + m[0].length
  }
  if (last < content.length) parts.push(content.slice(last))
  return <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{parts}</p>
}

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sources?: Array<{
    doc_id: number
    doc_name?: string | null
    chunk_id: string
    chunk_index?: number | null
    k_index?: number | null
    score: number
    snippet?: string | null
  }>
  thinking?: string
  // 防编造自检结果: grounded=false 表示答案经纠正仍含无法被知识库支撑的内容
  grounded?: boolean
  unsupported_claims?: string[]
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
  // Agent 思维链(CoT)实时展示状态:thinkingRef 累积流式思考文本,isThinking 标记思考阶段。
  const [thinking, setThinking] = useState('')
  const thinkingRef = useRef('')
  const [isThinking, setIsThinking] = useState(false)
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
    setThinking('')
    thinkingRef.current = ''
    setIsThinking(false)

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
            } else if (event.type === 'thinking_start') {
              // 思考状态实时更新:进入思考阶段。
              setIsThinking(true)
              thinkingRef.current = ''
              setThinking('')
            } else if (event.type === 'thought') {
              // 思维链内容流式输出:逐块累积。
              thinkingRef.current += event.data
              setThinking(thinkingRef.current)
            } else if (event.type === 'thinking_end') {
              // 思考完成后的状态切换:退出思考阶段,准备接收正式回答。
              setIsThinking(false)
            } else if (event.type === 'status') {
              console.log('Status:', event.data)
              // 进入正式回答阶段(generating)时,确保思考面板已关闭。
              if (event.data === 'generating') setIsThinking(false)
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
                // 防编造自检结果: grounded=false 时前端展示告警
                grounded: event.data.grounded,
                unsupported_claims: event.data.unsupported_claims || [],
                // 将本次对话的思考链一并持久化,历史记录中也可回看 agent 推理过程。
                thinking: thinkingRef.current || undefined,
              }
              setMessages((prev) => [...prev, assistantMessage])
              setStreamingContent('')
              streamingRef.current = ''
              setThinking('')
              thinkingRef.current = ''
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
                  {msg.role === 'assistant' && msg.thinking && (
                    <div style={{ marginBottom: 8, padding: '8px 12px', background: '#f5f7fa', borderLeft: '3px solid #b37feb', borderRadius: 4, color: '#5c5c5c', fontSize: 13, whiteSpace: 'pre-wrap' }}>
                      <div style={{ fontWeight: 600, marginBottom: 4, color: '#722ed1' }}>💭 思考过程</div>
                      {msg.thinking}
                    </div>
                  )}
                  {renderAnswer(msg.content)}
                  {msg.role === 'assistant' && msg.grounded === false && (
                    <div className="grounded-warning">
                      <div className="gw-title">⚠️ 部分内容未经知识库佐证</div>
                      {msg.unsupported_claims && msg.unsupported_claims.length > 0 && (
                        <ul className="gw-list">
                          {msg.unsupported_claims.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      )}
                      <div className="gw-hint">已自动剔除/修正无法被知识库支撑的陈述，仍建议谨慎采信。</div>
                    </div>
                  )}
                  {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                    <div className="message-sources">
                      <div className="sources-title">引用来源 (点击回答中的 [K编号] 可跳转):</div>
                      {msg.sources.map((source, index) => (
                        <div
                          key={index}
                          id={`source-card-${source.k_index ?? index + 1}`}
                          className="source-item"
                        >
                          <Tag color="blue">{source.k_index != null ? `[K${source.k_index}]` : `来源${index + 1}`}</Tag>
                          <Tag color="geekblue">{(source.score * 100).toFixed(0)}%</Tag>
                          <span className="source-name">{source.doc_name || `doc ${source.doc_id}`}</span>
                          <span className="source-snippet" title={source.snippet || ''}>{source.snippet}</span>
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
              {(streamingContent || thinking) && (
                <Card className="ai-message streaming">
                  <div className="message-header">
                    <Tag color="green">AI</Tag>
                    <span className="message-time">{isThinking ? '思考中...' : 'Typing...'}</span>
                  </div>
                  {thinking && (
                    <div style={{ marginBottom: streamingContent ? 8 : 0, padding: '8px 12px', background: '#f5f7fa', borderLeft: '3px solid #b37feb', borderRadius: 4, color: '#5c5c5c', fontSize: 13, whiteSpace: 'pre-wrap' }}>
                      <div style={{ fontWeight: 600, marginBottom: 4, color: '#722ed1' }}>💭 思考过程</div>
                      {thinking}
                    </div>
                  )}
                  {streamingContent && <p>{streamingContent}</p>}
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

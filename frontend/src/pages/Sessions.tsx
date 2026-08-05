import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Layout, List, Input, Button, Card, Tag, message, Modal, Popconfirm, Select } from 'antd'
import { SendOutlined, PlusOutlined, LikeOutlined, DislikeOutlined, DeleteOutlined } from '@ant-design/icons'
import request, { postStream } from '../utils/request'

const { Header, Content, Sider } = Layout

// 答案中的 [K编号] 与下方"引用来源"列表一一对应: [K3] -> sources[k_index=3]。
// [K编号] 仅作为引用标记展示(不可点击跳转), 真正的来源内容见下方来源列表。
const K_REF_RE = /\[K(\d+)\]/g

// 从回答文本解析被引用的 [K编号], 用于只展示真正被引用的来源, 避免罗列全部召回块。
function citedKIndices(content: string): Set<number> {
  const set = new Set<number>()
  if (!content) return set
  const re = /\[K(\d+)\]/g
  let m: RegExpExecArray | null
  while ((m = re.exec(content)) !== null) set.add(Number(m[1]))
  return set
}

function renderAnswer(
  content: string,
  sources?: Array<{ k_index?: number | null; snippet?: string | null }>
): ReactNode {
  if (!content) return null
  // 建立 [K编号] -> 原文片段 映射, 用于给引用标记加悬停提示, 让用户随时查看原文。
  const kIndexToSnippet: Record<number, string> = {}
  if (sources) {
    for (const s of sources) {
      if (s.k_index != null) kIndexToSnippet[s.k_index] = s.snippet || ''
    }
  }
  const parts: React.ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  K_REF_RE.lastIndex = 0
  while ((m = K_REF_RE.exec(content)) !== null) {
    if (m.index > last) parts.push(content.slice(last, m.index))
    const idx = Number(m[1])
    const tip = kIndexToSnippet[idx]
    // 纯展示高亮; tooltip 显示对应原文片段, 清晰区分"原文引用"与"模型新增内容"。
    parts.push(
      <span
        key={`k-${m.index}`}
        className="k-ref"
        title={tip ? `原文：${tip}` : undefined}
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
  // 追问引导: 回答结束后由后端生成的 2-3 个相关追问建议, 点击可直接发送
  suggestions?: string[]
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
  const [feedbackReason, setFeedbackReason] = useState<string | undefined>(undefined)

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

  const deleteSession = async (sessionId: number, event: React.MouseEvent) => {
    event.stopPropagation()
    try {
      await request.delete(`/sessions/${sessionId}`)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
      if (currentSession === sessionId) {
        setCurrentSession(null)
        setMessages([])
        if (sessions.length > 1) {
          const remaining = sessions.filter((s) => s.id !== sessionId)
          if (remaining.length > 0) {
            setCurrentSession(remaining[0].id)
            loadMessages(remaining[0].id)
          }
        }
      }
      message.success('会话删除成功')
    } catch (error) {
      // Error handled by interceptor
    }
  }

  // 首次对话用用户首条消息的前 20 字(去空白)作为会话标题, 取代默认的"新对话"。
  const titleSession = async (sessionId: number, text: string) => {
    const trimmed = text.replace(/\s+/g, ' ').trim()
    const title = trimmed.length > 20 ? `${trimmed.slice(0, 20)}…` : trimmed || '新对话'
    try {
      await request.put(`/sessions/${sessionId}`, { title })
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title } : s))
      )
    } catch (error) {
      // 标题更新失败不影响对话主流程
    }
  }

  // 智能标题: 调用后端 LLM 接口, 基于当前会话上下文生成/刷新贴切标题并写回。
  // 首次回复后生成贴切标题, 后续回复随上下文动态更新(后端在标题不变时跳过写库)。
  const refreshSmartTitle = async (sessionId: number) => {
    try {
      const res = await request.post(`/sessions/${sessionId}/title`)
      const updated = res.data as Session
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: updated.title } : s))
      )
    } catch (error) {
      // 标题刷新失败(如 LLM 不可用)不影响对话主流程, 沿用既有标题
    }
  }

  const handleFeedback = (messageId: number, type: 'like' | 'dislike') => {
    setSelectedMessageId(messageId)
    setFeedbackType(type)
    setFeedbackComment('')
    setFeedbackReason(undefined)
    setFeedbackModalVisible(true)
  }

  const submitFeedback = async () => {
    if (!selectedMessageId || !feedbackType) return

    try {
      await request.post('/feedback', {
        message_id: selectedMessageId,
        rating: feedbackType === 'like' ? 1 : -1,
        comment: feedbackComment,
        reason: feedbackReason
      })
      message.success('反馈提交成功')
      setFeedbackModalVisible(false)
      setFeedbackComment('')
      setFeedbackReason(undefined)
    } catch (error) {
      // Error handled by interceptor
    }
  }

  const sendMessage = async (presetText?: string) => {
    const userMessage = presetText ?? input
    if (!userMessage.trim() || !currentSession) return
    const sid = currentSession
    // 若该会话仍是默认标题"新对话", 用首条消息自动生成即时标题(与系统机制一致)
    const cur = sessions.find((s) => s.id === sid)
    if (cur && cur.title === '新对话') {
      titleSession(sid, userMessage)
    }
    setInput('')
    setMessages([...messages, { id: Date.now(), role: 'user', content: userMessage, created_at: new Date().toISOString() }])
    setLoading(true)
    setStreamingContent('')
    streamingRef.current = ''
    setThinking('')
    thinkingRef.current = ''
    setIsThinking(false)
    // 发送消息后立即滚动到底部，确保能看到思考过程
    setTimeout(() => scrollToBottom(), 100)

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
              // 思考开始时滚动到底部，确保用户能看到思考过程
              setTimeout(() => scrollToBottom(), 100)
            } else if (event.type === 'thought') {
              // 思维链内容流式输出:逐块累积。
              thinkingRef.current += event.data
              setThinking(thinkingRef.current)
            } else if (event.type === 'thinking_end') {
              // 思考完成后的状态切换:退出思考阶段,准备接收正式回答。
              setIsThinking(false)
            } else if (event.type === 'status') {
              console.log('Status:', event.data)
              // 进入正式回答阶段(generating)时,标记不再是"思考中";
              // 思考文本暂时保留,直到第一个 content 到达再清除,避免空白闪烁。
              if (event.data === 'generating') setIsThinking(false)
            } else if (event.type === 'content') {
              // 正式回复开始输出:清除思考过程(过渡态),仅保留并流式展示最终回复
              if (thinkingRef.current !== '' || thinking !== '') {
                thinkingRef.current = ''
                setThinking('')
              }
              setIsThinking(false)
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
                // 追问引导: 后端在 done 事件中附带的 2-3 个相关追问建议
                suggestions: event.data.suggestions || [],
              }
              setMessages((prev) => [...prev, assistantMessage])
              setStreamingContent('')
              streamingRef.current = ''
              setThinking('')
              thinkingRef.current = ''
              // 回复完成 -> 基于上下文智能生成/刷新会话标题(侧栏即时更新)
              refreshSmartTitle(sid)
            } else if (event.type === 'error') {
              message.error(event.data || '发生错误')
            }
          },
          onError: (error) => {
            message.error(error.message || '流传输出错')
          },
          onDone: () => {
            setLoading(false)
          },
        }
      )
    } catch (error) {
      message.error('发送消息失败')
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
            新建对话
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
              actions={[
                <Popconfirm
                  title="确认删除"
                  description="确定要删除这个会话吗？"
                  onConfirm={(e) => deleteSession(session.id, e as React.MouseEvent)}
                  okText="确定"
                  cancelText="取消"
                >
                  <Button
                    type="text"
                    icon={<DeleteOutlined />}
                    danger
                    size="small"
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              ]}
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
          <h2>AI 客服</h2>
        </Header>
        <Content>
          <div className="content-container">
            <div className="messages-container">
              {messages.map((msg) => (
                <Card key={msg.id} className={msg.role === 'user' ? 'user-message' : 'ai-message'}>
                  <div className="message-header">
                    <Tag color={msg.role === 'user' ? 'blue' : 'green'}>
                      {msg.role === 'user' ? '用户' : 'AI'}
                    </Tag>
                    <span className="message-time">
                      {new Date(msg.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  {renderAnswer(msg.content, msg.sources)}
                  {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (() => {
                    // 只展示回答中真正被 [K编号] 引用的来源, 让引用精确对应需求内容;
                    // 若回答里没有任何 [K编号](异常/纯直答), 退回展示全部来源以免信息丢失。
                    // 若 LLM 标注的 [K编号] 与可用来源的 k_index 不完全对齐(如越界/错位),
                    // 过滤结果为空时同样退回展示全部来源, 避免"明明有来源却一处都不显示"。
                    const cited = citedKIndices(msg.content)
                    const filtered = cited.size > 0
                      ? msg.sources.filter((s) => s.k_index != null && cited.has(s.k_index))
                      : msg.sources
                    const shown = filtered.length > 0 ? filtered : msg.sources
                    if (shown.length === 0) return null
                    return (
                      <div className="message-sources">
                        <div className="sources-title">引用来源（「」内为知识库原文）：</div>
                        {shown.map((source, index) => (
                          <div key={index} className="source-item">
                            <Tag color="blue">{source.k_index != null ? `[K${source.k_index}]` : `来源${index + 1}`}</Tag>
                            <span className="source-name">{source.doc_name || `doc ${source.doc_id}`}</span>
                            <span
                              className="source-snippet"
                              style={{ display: 'block', marginTop: 4, padding: '4px 8px', background: '#f6f8fa', borderLeft: '3px solid #1890ff', borderRadius: 4, color: '#333', fontSize: 12, whiteSpace: 'pre-wrap' }}
                              title={source.snippet || ''}
                            >
                              {source.snippet ? `「${source.snippet}」` : ''}
                            </span>
                          </div>
                        ))}
                      </div>
                    )
                  })()}
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
                  {msg.role === 'assistant' && msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="message-suggestions">
                      <div className="suggestions-title">你可能还想问：</div>
                      <div className="suggestion-chips">
                        {msg.suggestions.map((s, i) => (
                          <Button
                            key={i}
                            size="small"
                            className="suggestion-chip"
                            onClick={() => sendMessage(s)}
                          >
                            {s}
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
              ))}
              {(streamingContent || thinking) && (
                <Card className="ai-message streaming">
                  <div className="message-header">
                    <Tag color="green">AI</Tag>
                    <span className="message-time">{isThinking ? '思考中...' : '输入中...'}</span>
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
                placeholder="请输入您的问题..."
                size="large"
                value={input}
                maxLength={500}
                showCount
                onChange={(e) => setInput(e.target.value)}
                onPressEnter={() => sendMessage()}
                disabled={loading}
                suffix={
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={() => sendMessage()}
                    loading={loading}
                    size="large"
                  >
                    发送
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
        onCancel={() => {
          setFeedbackModalVisible(false)
          setFeedbackComment('')
          setFeedbackReason(undefined)
        }}
        okText="提交"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <p>您选择了: {feedbackType === 'like' ? '👍 有帮助' : '👎 无帮助'}</p>
        </div>
        {feedbackType === 'dislike' && (
          <div style={{ marginBottom: 16 }}>
            <p style={{ marginBottom: 8 }}>问题类型（可选）：</p>
            <Select
              style={{ width: '100%' }}
              placeholder="选择问题类型，便于我们优化"
              allowClear
              value={feedbackReason}
              onChange={(v) => setFeedbackReason(v)}
              options={[
                { value: '答非所问', label: '答非所问' },
                { value: '事实错误', label: '事实错误' },
                { value: '没召回', label: '没召回相关内容' },
                { value: '太啰嗦', label: '回答太啰嗦' },
                { value: '其他', label: '其他' },
              ]}
            />
          </div>
        )}
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

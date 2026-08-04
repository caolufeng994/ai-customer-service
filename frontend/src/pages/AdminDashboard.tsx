import { useState, useEffect } from 'react'
import {
  Card,
  Statistic,
  Table,
  Spin,
  message,
  Tabs,
  Select,
  Input,
  DatePicker,
  Space,
  Tag,
  Button,
  Empty,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import request from '../utils/request'

interface Overview {
  total_sessions: number
  total_messages: number
  total_feedbacks: number
  like_count: number
  dislike_count: number
}

interface DailyPoint {
  date: string
  count: number
}

interface SessionRow {
  id: number
  title: string
  user_id: number
  msg_count: number
  updated_at: string | null
}

interface FeedbackRow {
  id: number
  message_id: number
  user_id: number
  rating: number
  comment: string | null
  reason: string | null
  created_at: string
  session_id: number | null
  session_title: string | null
  user_account: string | null
  message_content: string | null
  message_role: string | null
}

const REASON_OPTIONS = ['答非所问', '事实错误', '没召回', '太啰嗦', '其他']

/**
 * 纯 SVG 折线图：根据日均问答量数据绘制，不引入额外图表依赖。
 * 缺失日期由后端补 0，因此数据点连续、折线不会断裂。
 */
function LineChart({ data }: { data: DailyPoint[] }) {
  const W = 760
  const H = 240
  const padX = 44
  const padY = 28
  const max = Math.max(1, ...data.map((d) => d.count))
  const n = data.length
  const xAt = (i: number) => padX + (i * (W - 2 * padX)) / Math.max(1, n - 1)
  const yAt = (v: number) => H - padY - (v * (H - 2 * padY)) / max

  const linePts = data.map((d, i) => `${xAt(i)},${yAt(d.count)}`).join(' ')
  const areaPts = `${padX},${H - padY} ${linePts} ${W - padX},${H - padY}`
  const step = Math.max(1, Math.ceil(n / 7))

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W }} role="img" aria-label="日均问答量折线图">
      {[0, 0.5, 1].map((t) => {
        const y = H - padY - t * (H - 2 * padY)
        return <line key={t} x1={padX} y1={y} x2={W - padX} y2={y} stroke="#eef0f4" strokeWidth={1} />
      })}
      <text x={padX} y={H - padY - max * (H - 2 * padY) - 4} fontSize={10} fill="#8c98a8">峰值 {max}</text>
      <polygon points={areaPts} fill="rgba(91,140,255,0.10)" />
      <polyline points={linePts} fill="none" stroke="#5b8cff" strokeWidth={2} />
      {data.map((d, i) => (
        <circle key={i} cx={xAt(i)} cy={yAt(d.count)} r={3} fill="#5b8cff" />
      ))}
      {data.map((d, i) =>
        i % step === 0 ? (
          <text key={i} x={xAt(i)} y={H - 8} fontSize={10} fill="#8c98a8" textAnchor="middle">
            {d.date.slice(5)}
          </text>
        ) : null
      )}
    </svg>
  )
}

export default function AdminDashboard() {
  const [loading, setLoading] = useState(true)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [daily, setDaily] = useState<DailyPoint[]>([])
  const [sessions, setSessions] = useState<SessionRow[]>([])

  // ---- 用户反馈模块状态 ----
  const [feedback, setFeedback] = useState<FeedbackRow[]>([])
  const [fbLoading, setFbLoading] = useState(false)
  const [fbTotal, setFbTotal] = useState(0)
  const [fbPage, setFbPage] = useState(1)
  const [fbPageSize, setFbPageSize] = useState(10)
  const [fRating, setFRating] = useState<number | undefined>(undefined)
  const [fReason, setFReason] = useState<string | undefined>(undefined)
  const [fKeyword, setFKeyword] = useState('')
  const [fRange, setFRange] = useState<any>(null)

  useEffect(() => {
    ;(async () => {
      try {
        const [o, d, s] = await Promise.all([
          request.get('/stats/overview'),
          request.get('/stats/daily-qa'),
          request.get('/stats/sessions'),
        ])
        setOverview(o.data)
        setDaily(d.data)
        setSessions(s.data.items || [])
      } catch {
        message.error('加载统计数据失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const fetchFeedback = async (page = fbPage, pageSize = fbPageSize, keywordOverride?: string) => {
    setFbLoading(true)
    try {
      const params: Record<string, unknown> = {
        skip: (page - 1) * pageSize,
        limit: pageSize,
      }
      if (fRating !== undefined) params.rating = fRating
      if (fReason) params.reason = fReason
      const kw = keywordOverride !== undefined ? keywordOverride : fKeyword
      if (kw.trim()) params.keyword = kw.trim()
      if (fRange && fRange[0] && fRange[1]) {
        params.start_date = fRange[0].format('YYYY-MM-DD')
        params.end_date = fRange[1].format('YYYY-MM-DD')
      }
      const res: any = await request.get('/admin/feedbacks', { params })
      setFeedback(res.data || [])
      setFbTotal(res.meta?.total ?? 0)
    } catch {
      message.error('加载反馈数据失败')
    } finally {
      setFbLoading(false)
    }
  }

  useEffect(() => {
    fetchFeedback(1, fbPageSize)
    // 仅在挂载时拉取首屏反馈数据；筛选/翻页由各自处理函数触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const resetFilters = () => {
    setFRating(undefined)
    setFReason(undefined)
    setFKeyword('')
    setFRange(null)
  }

  const sessionColumns = [
    { title: '会话ID', dataIndex: 'id', key: 'id', width: 90 },
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '用户ID', dataIndex: 'user_id', key: 'user_id', width: 90 },
    { title: '问答数', dataIndex: 'msg_count', key: 'msg_count', width: 90 },
    {
      title: '最后更新',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
  ]

  const feedbackColumns: ColumnsType<FeedbackRow> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 64 },
    {
      title: '用户',
      key: 'user',
      width: 150,
      render: (_, r) => (
        <div>
          <div>{r.user_account || '-'}</div>
          <div style={{ color: '#999', fontSize: 12 }}>UID {r.user_id}</div>
        </div>
      ),
    },
    {
      title: '类型',
      dataIndex: 'rating',
      key: 'rating',
      width: 90,
      render: (v: number) =>
        v === 1 ? <Tag color="green">点赞</Tag> : <Tag color="red">点踩</Tag>,
    },
    {
      title: '原因',
      dataIndex: 'reason',
      key: 'reason',
      width: 110,
      render: (v: string | null) =>
        v ? <Tag color="orange">{v}</Tag> : <span style={{ color: '#bbb' }}>-</span>,
    },
    {
      title: '反馈内容',
      dataIndex: 'comment',
      key: 'comment',
      ellipsis: true,
      render: (v: string | null) =>
        v || <span style={{ color: '#bbb' }}>(无文字反馈)</span>,
    },
    {
      title: '关联消息',
      key: 'msg',
      ellipsis: true,
      render: (_, r) => (
        <div>
          <div style={{ color: '#666', fontSize: 12 }}>{r.session_title || '会话'}</div>
          <div className="fb-msg-snippet">{r.message_content || '-'}</div>
        </div>
      ),
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
  ]

  const overviewPane = (
    <Spin spinning={loading}>
      <div className="stat-cards">
        <Card>
          <Statistic title="总会话数" value={overview?.total_sessions ?? 0} />
        </Card>
        <Card>
          <Statistic title="总消息数" value={overview?.total_messages ?? 0} />
        </Card>
        <Card>
          <Statistic title="总反馈数" value={overview?.total_feedbacks ?? 0} />
        </Card>
        <Card>
          <Statistic
            title="点赞 / 点踩"
            value={`${overview?.like_count ?? 0} / ${overview?.dislike_count ?? 0}`}
          />
        </Card>
      </div>

      <Card title="日均问答量（近 14 天）" className="chart-card">
        {daily.length > 0 ? <LineChart data={daily} /> : <div className="empty-hint">暂无数据</div>}
      </Card>

      <Card title="全量会话记录" className="table-card">
        <Table
          rowKey="id"
          columns={sessionColumns}
          dataSource={sessions}
          pagination={{ pageSize: 10 }}
          size="middle"
        />
      </Card>
    </Spin>
  )

  const feedbackPane = (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          placeholder="全部类型"
          style={{ width: 130 }}
          allowClear
          value={fRating}
          onChange={(v) => setFRating(v)}
          options={[
            { value: 1, label: '点赞' },
            { value: -1, label: '点踩' },
          ]}
        />
        <Select
          placeholder="全部原因"
          style={{ width: 150 }}
          allowClear
          value={fReason}
          onChange={(v) => setFReason(v)}
          options={REASON_OPTIONS.map((r) => ({ value: r, label: r }))}
        />
        <Input.Search
          placeholder="搜索反馈内容"
          allowClear
          style={{ width: 220 }}
          value={fKeyword}
          onChange={(e) => setFKeyword(e.target.value)}
          onSearch={(v) => fetchFeedback(1, fbPageSize, v)}
        />
        <DatePicker.RangePicker value={fRange} onChange={(dates) => setFRange(dates)} />
        <Button
          type="primary"
          onClick={() => {
            setFbPage(1)
            fetchFeedback(1, fbPageSize)
          }}
        >
          查询
        </Button>
        <Button
          onClick={() => {
            resetFilters()
            setFbPage(1)
            fetchFeedback(1, fbPageSize)
          }}
        >
          重置
        </Button>
      </Space>

      <Table<FeedbackRow>
        rowKey="id"
        loading={fbLoading}
        columns={feedbackColumns}
        dataSource={feedback}
        pagination={{
          current: fbPage,
          pageSize: fbPageSize,
          total: fbTotal,
          showSizeChanger: true,
          onChange: (page, pageSize) => {
            setFbPage(page)
            setFbPageSize(pageSize)
            fetchFeedback(page, pageSize)
          },
        }}
        size="middle"
        expandable={{
          expandedRowRender: (record) => (
            <div className="fb-detail">
              <div>
                <b>反馈内容：</b>
                {record.comment || <span style={{ color: '#bbb' }}>(无文字反馈)</span>}
              </div>
              <div style={{ marginTop: 8 }}>
                <b>关联消息（{record.message_role || '-'}）：</b>
                <div className="fb-detail-msg">{record.message_content || '-'}</div>
              </div>
            </div>
          ),
        }}
        locale={{ emptyText: <Empty description="暂无反馈数据" /> }}
      />
    </div>
  )

  return (
    <div className="admin-container">
      <h2 className="admin-title">管理后台</h2>
      <Tabs
        defaultActiveKey="overview"
        items={[
          { key: 'overview', label: '数据概览', children: overviewPane },
          { key: 'feedback', label: '用户反馈', children: feedbackPane },
        ]}
      />
    </div>
  )
}

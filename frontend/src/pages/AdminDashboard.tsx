import { useState, useEffect } from 'react'
import { Card, Statistic, Table, Spin, message } from 'antd'
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

  const columns = [
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

  return (
    <div className="admin-container">
      <h2 className="admin-title">管理后台</h2>
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
            columns={columns}
            dataSource={sessions}
            pagination={{ pageSize: 10 }}
            size="middle"
          />
        </Card>
      </Spin>
    </div>
  )
}

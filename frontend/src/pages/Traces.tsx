import { useEffect, useState } from 'react'
import { Card, Table, Tag, Spin, Typography, Input, Space, Empty, Tooltip } from 'antd'
import request, { getLastTraceId } from '../utils/request'

const { Title, Text } = Typography

interface TraceSummary {
  trace_id: string
  root_name: string
  span_count: number
  total_ms: number
  status: string
  start_ms: number
}

interface SpanNode {
  span_id: string
  parent_span_id: string | null
  name: string
  start_offset_ms: number
  duration_ms: number
  end_offset_ms: number
  status: string
  error: string | null
  attributes: Record<string, any>
  children: SpanNode[]
}

interface TraceDetail extends Omit<TraceSummary, 'start_ms'> {
  base_ms: number
  spans: SpanNode[]
}

function flatten(spans: SpanNode[], depth = 0): Array<{ node: SpanNode; depth: number }> {
  const out: Array<{ node: SpanNode; depth: number }> = []
  for (const s of spans) {
    out.push({ node: s, depth })
    out.push(...flatten(s.children, depth + 1))
  }
  return out
}

function statusColor(status: string) {
  return status === 'error' ? '#ff4d4f' : status === 'ok' ? '#52c41a' : '#faad14'
}

export default function Traces() {
  const [list, setList] = useState<TraceSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [traceId, setTraceId] = useState('')
  const [detail, setDetail] = useState<TraceDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const loadList = async () => {
    setLoading(true)
    try {
      const res = await request.get('/traces?limit=100')
      setList(res.data || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadList()
    const last = getLastTraceId()
    if (last) setTraceId(last)
  }, [])

  const openTrace = async (id: string) => {
    setTraceId(id)
    setDetailLoading(true)
    try {
      const res = await request.get(`/traces/${id}`)
      setDetail(res.data)
    } catch (e: any) {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const rows = detail ? flatten(detail.spans) : []
  const maxEnd = detail ? detail.total_ms : 1

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>全链路追踪 (Trace)</Title>
      <Text type="secondary">
        每次请求都会生成 TraceId 并贯穿所有服务节点；点击列表中的某条追踪即可查看各节点的耗时与状态瀑布图。
        页面报错时提示的「追踪ID」可直接粘贴到下方输入框查看。
      </Text>

      <Space style={{ margin: '16px 0', display: 'flex', flexWrap: 'wrap' }}>
        <Input.Search
          placeholder="输入 TraceId 查看"
          allowClear
          value={traceId}
          onChange={(e) => setTraceId(e.target.value)}
          onSearch={(v) => v && openTrace(v)}
          style={{ width: 360 }}
        />
        <a onClick={loadList}>刷新列表</a>
      </Space>

      <Card title="最近追踪" size="small" style={{ marginBottom: 16 }}>
        <Table<TraceSummary>
          rowKey="trace_id"
          size="small"
          loading={loading}
          dataSource={list}
          pagination={{ pageSize: 10 }}
          columns={[
            {
              title: 'TraceId',
              dataIndex: 'trace_id',
              render: (v: string) => <Text copyable={{ text: v }}>{v.slice(0, 12)}…</Text>,
            },
            { title: '入口', dataIndex: 'root_name' },
            { title: '节点数', dataIndex: 'span_count', width: 90 },
            {
              title: '总耗时(ms)',
              dataIndex: 'total_ms',
              width: 120,
              render: (v: number) => <Text strong>{v}</Text>,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 90,
              render: (s: string) => <Tag color={statusColor(s)}>{s}</Tag>,
            },
            {
              title: '操作',
              width: 90,
              render: (_: any, r: TraceSummary) => <a onClick={() => openTrace(r.trace_id)}>查看</a>,
            },
          ]}
        />
      </Card>

      <Card title={detail ? `瀑布图 · ${detail.trace_id}` : '瀑布图'} size="small">
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : detail ? (
          <div>
            <Space style={{ marginBottom: 12 }}>
              <Tag color={statusColor(detail.status)}>{detail.status}</Tag>
              <Text>总耗时 <Text strong>{detail.total_ms}</Text> ms</Text>
            </Space>
            <div style={{ fontFamily: 'monospace', fontSize: 12 }}>
              {rows.map(({ node, depth }) => {
                const left = (node.start_offset_ms / maxEnd) * 100
                const width = Math.max((node.duration_ms / maxEnd) * 100, 0.5)
                return (
                  <div key={node.span_id} style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
                    <div style={{ width: 24 * depth, flexShrink: 0 }} />
                    <div style={{ width: 200, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={node.name}>
                      {node.name}
                    </div>
                    <div style={{ position: 'relative', flex: 1, height: 18, background: '#f5f5f5', borderRadius: 3 }}>
                      <Tooltip title={`${node.duration_ms}ms${node.error ? ' · ' + node.error : ''}`}>
                        <div
                          style={{
                            position: 'absolute',
                            left: `${left}%`,
                            width: `${width}%`,
                            top: 2,
                            height: 14,
                            background: statusColor(node.status),
                            borderRadius: 2,
                          }}
                        />
                      </Tooltip>
                    </div>
                    <div style={{ width: 70, textAlign: 'right', flexShrink: 0, color: '#666' }}>{node.duration_ms}ms</div>
                  </div>
                )
              })}
            </div>
            {detail.spans.map((s) => (
              <div key={s.span_id} style={{ marginTop: 8 }}>
                <Text strong>{s.name}</Text> 属性：
                {Object.entries(s.attributes || {}).map(([k, v]) => (
                  <Tag key={k} style={{ margin: 2 }}>{k}={String(v)}</Tag>
                ))}
                {s.error && <Tag color="red">{s.error}</Tag>}
              </div>
            ))}
          </div>
        ) : (
          <Empty description="选择一条追踪查看瀑布图" />
        )}
      </Card>
    </div>
  )
}

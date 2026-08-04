import { useState, useEffect } from 'react'
import { Table, Button, Upload, Tag, message, Modal } from 'antd'
import { UploadOutlined, DeleteOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import request from '../utils/request'

interface Document {
  id: number
  name: string
  file_type: string
  size: number
  chunk_count: number
  status: 'processing' | 'ready' | 'failed' | 'deleting'
  error_msg?: string
  created_at: string
}

// 后端返回的状态值为英文枚举, 这里映射为中文展示
const STATUS_TEXT: Record<string, string> = {
  processing: '处理中',
  ready: '已就绪',
  failed: '失败',
  deleting: '删除中',
}

const STATUS_COLOR: Record<string, string> = {
  processing: 'blue',
  ready: 'green',
  failed: 'red',
  deleting: 'orange',
}

export default function KnowledgeBase() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(false)
  const [fileList, setFileList] = useState<UploadFile[]>([])

  const loadDocuments = async () => {
    setLoading(true)
    try {
      const response = await request.get('/kb/documents')
      setDocuments(response.data)
    } catch (error) {
      // Error handled by interceptor
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async () => {
    if (fileList.length === 0) {
      message.warning('请先选择文件')
      return
    }

    const formData = new FormData()
    fileList.forEach((file) => {
      formData.append('file', file.originFileObj as File)
    })

    try {
      await request.post('/kb/documents', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      message.success('文档上传成功')
      setFileList([])
      loadDocuments()
    } catch (error) {
      // Error handled by interceptor
    }
  }

  const handleDelete = async (id: number) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除该文档吗？删除后其切片将一并从知识库中移除。',
      okText: '删除',
      cancelText: '取消',
      onOk: async () => {
        try {
          await request.delete(`/kb/documents/${id}`)
          message.success('文档删除成功')
          loadDocuments()
        } catch (error) {
          // Error handled by interceptor
        }
      },
    })
  }

  useEffect(() => {
    loadDocuments()
  }, [])

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '类型',
      dataIndex: 'file_type',
      key: 'file_type',
      width: 100,
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      render: (size: number) => `${(size / 1024).toFixed(1)} KB`,
    },
    {
      title: '分块数',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 90,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => (
        <Tag color={STATUS_COLOR[status]}>{STATUS_TEXT[status] ?? status}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: any, record: Document) => (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleDelete(record.id)}
        >
          删除
        </Button>
      ),
    },
  ]

  return (
    <div className="kb-page">
      <div className="kb-header">
        <div>
          <h2>知识库</h2>
          <p className="kb-subtitle">管理用于 AI 智能回答的文档</p>
        </div>
        <div className="kb-actions">
          <Upload
            fileList={fileList}
            onChange={({ fileList }) => setFileList(fileList)}
            beforeUpload={() => false}
            accept=".txt,.md,.pdf,.docx"
          >
            <Button icon={<UploadOutlined />} size="large">
              选择文件
            </Button>
          </Upload>
          <Button
            type="primary"
            onClick={handleUpload}
            disabled={fileList.length === 0}
            size="large"
          >
            上传
          </Button>
        </div>
      </div>
      <Table
        columns={columns}
        dataSource={documents}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
      />
    </div>
  )
}

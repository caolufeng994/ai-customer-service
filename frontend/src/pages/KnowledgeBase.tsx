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
      message.warning('Please select a file')
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
      message.success('Document uploaded successfully')
      setFileList([])
      loadDocuments()
    } catch (error) {
      // Error handled by interceptor
    }
  }

  const handleDelete = async (id: number) => {
    Modal.confirm({
      title: 'Confirm Delete',
      content: 'Are you sure you want to delete this document?',
      onOk: async () => {
        try {
          await request.delete(`/kb/documents/${id}`)
          message.success('Document deleted successfully')
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
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Type',
      dataIndex: 'file_type',
      key: 'file_type',
      width: 100,
    },
    {
      title: 'Size',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      render: (size: number) => `${(size / 1024).toFixed(1)} KB`,
    },
    {
      title: 'Chunks',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 80,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const colors: Record<string, string> = {
          processing: 'blue',
          ready: 'green',
          failed: 'red',
          deleting: 'orange',
        }
        return <Tag color={colors[status]}>{status}</Tag>
      },
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 100,
      render: (_: any, record: Document) => (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleDelete(record.id)}
        >
          Delete
        </Button>
      ),
    },
  ]

  return (
    <div className="kb-page">
      <div className="kb-header">
        <div>
          <h2>Knowledge Base</h2>
          <p className="kb-subtitle">Manage your documents for AI-powered responses</p>
        </div>
        <div className="kb-actions">
          <Upload
            fileList={fileList}
            onChange={({ fileList }) => setFileList(fileList)}
            beforeUpload={() => false}
            accept=".txt,.md,.pdf"
          >
            <Button icon={<UploadOutlined />} size="large">
              Select File
            </Button>
          </Upload>
          <Button
            type="primary"
            onClick={handleUpload}
            disabled={fileList.length === 0}
            size="large"
          >
            Upload
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

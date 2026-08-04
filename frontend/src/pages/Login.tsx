import { useState } from 'react'
import { Form, Input, Button, Card, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import request from '../utils/request'

interface LoginForm {
  /** 手机号或邮箱，字段名需与后端 LoginRequest 保持一致（见 docs/API文档.md 登录接口） */
  phone_or_email: string
  password: string
}

export default function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const onFinish = async (values: LoginForm) => {
    setLoading(true)
    try {
      // 显式构造请求体，不直接透传表单 values：
      // 避免表单字段名与接口契约字段名的隐式耦合（历史上这里因表单叫 phone 而接口要
      // phone_or_email，导致登录恒返回 422）。手机号/邮箱顺带 trim，防止首尾空格误判为账号不存在。
      const payload = {
        phone_or_email: values.phone_or_email?.trim(),
        password: values.password,
      }
      const response = await request.post('/auth/login', payload)
      localStorage.setItem('token', response.data.token)
      message.success('登录成功')
      navigate('/sessions')
    } catch (error) {
      // Error handled by interceptor
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <Card
        title="AI 智能客服"
        className="login-card"
      >
        <div className="login-subtitle">
          <p>欢迎回来！请登录以继续</p>
        </div>
        <Form
          name="login"
          onFinish={onFinish}
          autoComplete="off"
          layout="vertical"
        >
          <Form.Item
            label="手机号或邮箱"
            name="phone_or_email"
            rules={[{ required: true, message: '请输入手机号或邮箱！' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="请输入手机号或邮箱"
              size="large"
            />
          </Form.Item>

          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码！' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入密码"
              size="large"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={loading}
            >
              登录
            </Button>
          </Form.Item>

          <div style={{ textAlign: 'center', marginTop: 4 }}>
            还没有账号？<a onClick={() => navigate('/register')}>立即注册</a>
          </div>
        </Form>
      </Card>
    </div>
  )
}

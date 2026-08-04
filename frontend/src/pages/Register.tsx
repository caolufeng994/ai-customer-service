import { useState } from 'react'
import { Form, Input, Button, Card, message } from 'antd'
import { LockOutlined, MobileOutlined, MailOutlined } from '@ant-design/icons'
import { useNavigate, Link } from 'react-router-dom'
import request from '../utils/request'

interface RegisterForm {
  phone?: string
  email?: string
  password: string
  confirm: string
}

export default function Register() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const onFinish = async (values: RegisterForm) => {
    // 后端 RegisterRequest 要求 phone / email 至少提供其一，前端先做友好拦截，
    // 避免把空表单直接打到接口再拿 422。
    if (!values.phone?.trim() && !values.email?.trim()) {
      message.error('请至少填写手机号或邮箱之一')
      return
    }

    setLoading(true)
    try {
      // 只发送用户实际填写的字段，未填写的不传（保持与 RegisterRequest 的 Optional 契约一致）。
      const payload: { phone?: string; email?: string; password: string } = {
        password: values.password,
      }
      if (values.phone?.trim()) payload.phone = values.phone.trim()
      if (values.email?.trim()) payload.email = values.email.trim()

      await request.post('/auth/register', payload)
      message.success('注册成功，请登录')
      navigate('/login')
    } catch (error) {
      // 失败提示由响应拦截器统一处理（extractErrorMessage 提取后端 message）
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <Card title="创建账号" className="login-card">
        <div className="login-subtitle">
          <p>注册一个新账号以使用 AI 客服</p>
        </div>
        <Form
          name="register"
          onFinish={onFinish}
          autoComplete="off"
          layout="vertical"
        >
          <Form.Item
            label="手机号"
            name="phone"
            rules={[{ pattern: /^1[3-9]\d{9}$/, message: '请输入有效的手机号' }]}
          >
            <Input
              prefix={<MobileOutlined />}
              placeholder="手机号（与邮箱至少填一项）"
              size="large"
            />
          </Form.Item>

          <Form.Item
            label="邮箱"
            name="email"
            rules={[{ type: 'email', message: '请输入有效的邮箱' }]}
          >
            <Input
              prefix={<MailOutlined />}
              placeholder="邮箱（与手机号至少填一项）"
              size="large"
            />
          </Form.Item>

          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, min: 6, message: '密码至少 6 位' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="设置密码（至少 6 位）"
              size="large"
            />
          </Form.Item>

          <Form.Item
            label="确认密码"
            name="confirm"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="再次输入密码"
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
              注册
            </Button>
          </Form.Item>

          <div style={{ textAlign: 'center' }}>
            已有账号？<Link to="/login">返回登录</Link>
          </div>
        </Form>
      </Card>
    </div>
  )
}

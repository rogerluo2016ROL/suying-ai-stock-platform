import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, Alert } from 'antd'
import { StockOutlined, MailOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '../../contexts/AuthContext'

const { Title, Text } = Typography

export default function RegisterPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { register, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  // Already logged in → redirect to home
  if (isAuthenticated) {
    navigate('/', { replace: true })
    return null
  }

  const onFinish = async (values: { name: string; email: string; password: string; confirmPassword: string }) => {
    setError(null)
    setLoading(true)
    try {
      await register(values.name, values.email, values.password)
      navigate('/', { replace: true })
    } catch (err: any) {
      setError(err.message || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
      <div style={{
        minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center',
        background: 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)',
      }}>
        <Card
          style={{
            width: 400, maxWidth: '90vw',
            background: '#1f1f1f',
            borderColor: '#303030',
            boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
          }}
          styles={{ body: { padding: '32px 40px' } }}
        >
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <StockOutlined style={{ fontSize: 36, color: '#1677ff', marginBottom: 12 }} />
            <Title level={3} style={{ margin: 0, color: '#e8e8e8' }}>速赢AI</Title>
            <Text type="secondary">创建您的账号</Text>
          </div>

          {error && (
            <Alert message={error} type="error" showIcon closable
              onClose={() => setError(null)}
              style={{ marginBottom: 24 }}
            />
          )}

          <Form onFinish={onFinish} layout="vertical" size="large">
            <Form.Item
              name="name"
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 2, max: 20, message: '用户名为 2-20 个字符' },
              ]}
            >
              <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="name" />
            </Form.Item>

            <Form.Item
              name="email"
              rules={[
                { required: true, message: '请输入邮箱地址' },
                { type: 'email', message: '请输入有效的邮箱地址' },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="邮箱" autoComplete="email" />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少 8 位，需包含大写字母和数字' },
                { pattern: /^(?=.*[A-Z])(?=.*\d)/, message: '密码需包含至少一个大写字母和一个数字' },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="new-password" />
            </Form.Item>

            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve()
                    }
                    return Promise.reject(new Error('两次密码输入不一致'))
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="确认密码" autoComplete="new-password" />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                注册
              </Button>
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'center' }}>
            <Text type="secondary">
              已有账号？
              <Link to="/login" style={{ marginLeft: 4 }}>去登录</Link>
            </Text>
          </div>
        </Card>
      </div>
  )
}

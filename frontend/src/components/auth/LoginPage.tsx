import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, Alert } from 'antd'
import { StockOutlined, MailOutlined, LockOutlined } from '@ant-design/icons'
import { useAuth } from '../../contexts/AuthContext'

const { Title, Text } = Typography

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Already logged in → redirect to home
  if (isAuthenticated) {
    navigate('/', { replace: true })
    return null
  }

  const onFinish = async (values: { email: string; password: string }) => {
    setError(null)
    setLoading(true)
    try {
      await login(values.email, values.password)
      const redirect = searchParams.get('redirect') || '/'
      navigate(redirect, { replace: true })
    } catch (err: any) {
      setError(err.message || '登录失败')
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
            <Text type="secondary">登录您的账号</Text>
          </div>

          {error && (
            <Alert message={error} type="error" showIcon closable
              onClose={() => setError(null)}
              style={{ marginBottom: 24 }}
            />
          )}

          <Form onFinish={onFinish} layout="vertical" size="large">
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
              <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                登录
              </Button>
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'center' }}>
            <Text type="secondary">
              还没有账号？
              <Link to="/register" style={{ marginLeft: 4 }}>去注册</Link>
            </Text>
          </div>
        </Card>
      </div>
  )
}

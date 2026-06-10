import { Navigate, useLocation } from 'react-router-dom'
import { Spin, Result, Button } from 'antd'
import { useAuth, type Role } from '../../contexts/AuthContext'

interface ProtectedRouteProps {
  children: React.ReactNode
  roles?: Role[]
}

export default function ProtectedRoute({ children, roles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, hasRole } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        height: '60vh',
      }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!isAuthenticated) {
    const redirect = location.pathname + location.search
    return <Navigate to={`/login?redirect=${encodeURIComponent(redirect)}`} replace />
  }

  if (roles && !hasRole(...roles)) {
    return (
      <Result
        status="403"
        title="403"
        subTitle="您没有权限访问此页面"
        extra={
          <Button type="primary" onClick={() => window.location.href = '/'}>
            返回首页
          </Button>
        }
      />
    )
  }

  return <>{children}</>
}

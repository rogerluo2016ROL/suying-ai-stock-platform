import { Navigate, useLocation } from 'react-router-dom'
import { Spin, Result, Button } from 'antd'
import { useAuth, type PermissionKey, type Role } from '../../contexts/AuthContext'

interface ProtectedRouteProps {
  children: React.ReactNode
  roles?: Role[]
  permission?: PermissionKey
}

export default function ProtectedRoute({ children, roles, permission }: ProtectedRouteProps) {
  const { user, isAuthenticated, isLoading, hasRole, hasPermission } = useAuth()
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

  const hasBackendPermissions = (user?.permissions?.length || 0) > 0
  const deniedByPermission = permission && hasBackendPermissions && !hasPermission(permission)
  const deniedByRole = roles && !hasBackendPermissions && !hasRole(...roles)

  if (deniedByPermission || deniedByRole) {
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

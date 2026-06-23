import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, type ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider, useTheme } from './contexts/ThemeContext'
import ErrorBoundary from './components/ErrorBoundary'
import App from './App'
import './index.css'

// P1-05: token + component overrides shared between light/dark; the algorithm
// is swapped by ThemeProvider based on the persisted user choice.
const baseToken: ThemeConfig['token'] = {
  colorPrimary: '#1677ff',
  borderRadius: 6,
  fontFamily: `-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`,
  fontSize: 14,
}

const baseComponents: ThemeConfig['components'] = {
  Layout: {
    siderBg: '#ffffff',
    headerBg: '#ffffff',
    bodyBg: '#f5f5f5',
  },
  Menu: {
    itemBg: '#ffffff',
    itemColor: 'rgba(0,0,0,0.65)',
    itemHoverBg: '#f5f5f5',
    itemSelectedBg: '#e6f7ff',
    itemSelectedColor: '#1677ff',
    itemHeight: 40,
    itemMarginInline: 4,
    iconSize: 16,
    fontSize: 14,
    darkItemBg: '#ffffff',
    darkItemColor: 'rgba(0,0,0,0.65)',
    darkItemSelectedBg: '#e6f7ff',
  },
  Card: { paddingLG: 24 },
}

function ThemedRoot() {
  const { themeConfig } = useTheme()
  return (
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  )
}

// FE-P1 review S-1: 最外层 ErrorBoundary 在 ConfigProvider / ThemeProvider 之外，
// 默认 antd <Result> fallback 在 provider 自身抛错时无 antd 上下文（locale/theme 缺失）。
// 根级兜底改用纯 HTML fallback（不依赖 antd），确保最坏情况下仍渲染可读错误页。
function rootFallback() {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        gap: 12,
        fontFamily: `-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, sans-serif`,
        color: '#434343',
        background: '#f5f5f5',
      }}
    >
      <h1 style={{ fontSize: 20, margin: 0 }}>应用崩溃</h1>
      <p style={{ margin: 0, color: 'rgba(0,0,0,0.45)' }}>页面初始化失败，请刷新重试。</p>
      <a
        href="/"
        style={{
          padding: '6px 16px',
          background: '#1677ff',
          color: '#fff',
          borderRadius: 6,
          textDecoration: 'none',
        }}
      >
        刷新页面
      </a>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary fallback={rootFallback}>
      <ThemeProvider baseToken={baseToken} baseComponents={baseComponents}>
        <ThemedRoot />
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)

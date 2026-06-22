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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider baseToken={baseToken} baseComponents={baseComponents}>
        <ThemedRoot />
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)

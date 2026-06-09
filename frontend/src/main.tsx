import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
          fontFamily: `-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`,
          fontSize: 14,
        },
        components: {
          Layout: {
            siderBg: '#001529',
            headerBg: '#ffffff',
            bodyBg: '#f5f5f5',
          },
          Menu: {
            darkItemBg: '#001529',
            darkItemSelectedBg: '#1677ff',
            darkItemColor: 'rgba(255,255,255,0.65)',
          },
          Card: { paddingLG: 24 },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)

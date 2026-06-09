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
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)

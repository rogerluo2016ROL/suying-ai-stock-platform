import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfigProvider, Radio } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { ThemeProvider, useTheme } from '../contexts/ThemeContext'

// A consumer that renders the current mode + a switch, mirroring the Settings Drawer usage.
function ThemeProbe() {
  const { mode, setMode } = useTheme()
  return (
    <div>
      <span data-testid="mode-label">{mode}</span>
      <Radio.Group value={mode} onChange={e => setMode(e.target.value)}>
        <Radio.Button value="light">浅色</Radio.Button>
        <Radio.Button value="dark">暗色</Radio.Button>
      </Radio.Group>
    </div>
  )
}

function renderWithProvider(initialStorage: string | null = null) {
  if (initialStorage === null) {
    localStorage.removeItem('app_theme_mode')
  } else {
    localStorage.setItem('app_theme_mode', initialStorage)
  }
  return render(
    <ConfigProvider locale={zhCN}>
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>
    </ConfigProvider>,
  )
}

describe('P1-05: ThemeProvider 主题切换真实生效 + 持久化', () => {
  afterEach(() => localStorage.removeItem('app_theme_mode'))

  it('默认浅色模式', () => {
    renderWithProvider(null)
    expect(screen.getByTestId('mode-label').textContent).toBe('light')
  })

  it('点击暗色 → 切换为 dark 并写入 localStorage', async () => {
    const user = userEvent.setup()
    renderWithProvider(null)

    await user.click(screen.getByText('暗色'))

    expect(screen.getByTestId('mode-label').textContent).toBe('dark')
    expect(localStorage.getItem('app_theme_mode')).toBe('dark')
  })

  it('从 localStorage 恢复 dark 偏好（持久化跨刷新）', () => {
    renderWithProvider('dark')
    expect(screen.getByTestId('mode-label').textContent).toBe('dark')
  })

  it('非法 localStorage 值回退到 light（白名单）', () => {
    renderWithProvider('hacked-value')
    expect(screen.getByTestId('mode-label').textContent).toBe('light')
  })

  it('切换时在 <html data-theme> 反映（供 CSS key）', async () => {
    const user = userEvent.setup()
    renderWithProvider(null)

    await user.click(screen.getByText('暗色'))

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})

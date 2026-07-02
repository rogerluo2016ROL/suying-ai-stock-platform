import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { theme as antdTheme, type ThemeConfig } from 'antd'
import { lightTokens, darkTokens } from '../styles/tokens'

// P1-05: lift the dark/light choice into a real provider so the Settings Drawer
// switches are live controls (not dead props), with localStorage persistence.
// M0 (token 收口): themeConfig 在此按 mode 组装，token 单一真值源来自 styles/tokens.ts
// （与 suying-app.css :root 同值），消除旧 main.tsx baseToken 硬编码与 CSS 的漂移。

export type ThemeMode = 'light' | 'dark'

interface ThemeContextValue {
  mode: ThemeMode
  setMode: (m: ThemeMode) => void
  /** antd ConfigProvider theme config derived from mode (for the caller). */
  themeConfig: ThemeConfig
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

const STORAGE_KEY = 'app_theme_mode'

function readStoredMode(): ThemeMode {
  const m = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
  return m === 'dark' ? 'dark' : 'light'
}

// 按 mode 组装 antd themeConfig：token + components + algorithm 全部随明暗切换。
// colorSuccess/colorError 刻意保留 antd 默认（操作反馈语义），不映射 A 股 up/down。
function buildThemeConfig(mode: ThemeMode): ThemeConfig {
  const t = mode === 'dark' ? darkTokens : lightTokens
  return {
    token: {
      colorPrimary: t.accent,
      colorLink: t.accent,
      colorBgLayout: t.bg,
      colorBgContainer: t.surface,
      colorBgElevated: t.elevated,
      colorBorder: t.border,
      colorBorderSecondary: t.border2,
      colorText: t.fg,
      colorTextSecondary: t.fg2,
      colorTextTertiary: t.muted,
      borderRadius: t.radius,
      fontFamily: t.fontSans,
      fontSize: 14,
    },
    components: {
      Layout: {
        siderBg: t.surface,
        headerBg: t.surface,
        bodyBg: t.bg,
      },
      Menu: {
        itemBg: t.surface,
        itemColor: t.fg2,
        itemHoverBg: t.elevated,
        itemSelectedBg: t.accentDim,
        itemSelectedColor: t.accent,
        itemHeight: 40,
        itemMarginInline: 4,
        iconSize: 16,
        fontSize: 14,
        darkItemBg: darkTokens.surface,
        darkItemColor: darkTokens.fg2,
        darkItemSelectedBg: darkTokens.accentDim,
        darkItemSelectedColor: darkTokens.accent,
      },
      Card: { paddingLG: 24 },
    },
    algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode)

  const setMode = (m: ThemeMode) => {
    setModeState(m)
    try {
      localStorage.setItem(STORAGE_KEY, m)
    } catch {
      /* ignore quota */
    }
  }

  // Reflect the choice onto <html data-theme> for any CSS that keys off it.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode)
  }, [mode])

  const themeConfig = buildThemeConfig(mode)

  return (
    <ThemeContext.Provider value={{ mode, setMode, themeConfig }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}

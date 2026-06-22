import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { theme as antdTheme, type ThemeConfig } from 'antd'

// P1-05: lift the dark/light choice into a real provider so the Settings Drawer
// switches are live controls (not dead props), with localStorage persistence.

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

export function ThemeProvider({ children, baseToken, baseComponents }: {
  children: ReactNode
  baseToken: ThemeConfig['token']
  baseComponents: ThemeConfig['components']
}) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode)

  const setMode = (m: ThemeMode) => {
    setModeState(m)
    try { localStorage.setItem(STORAGE_KEY, m) } catch { /* ignore quota */ }
  }

  // Reflect the choice onto <html data-theme> for any CSS that keys off it.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode)
  }, [mode])

  const themeConfig: ThemeConfig = {
    token: baseToken,
    components: baseComponents,
    algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  }

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

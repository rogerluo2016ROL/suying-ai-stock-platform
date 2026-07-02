// 设计 token 单一真值源（JS 侧）。与 src/styles/suying-app.css 的 :root 段一一对应。
// Ant Design ConfigProvider 的 token 在 JS 层解析、不吃 CSS 变量字符串，故在此导出 JS 常量桥接。
// 改色时本文件与 suying-app.css 必须同步——两处是同一组值的两种表达。
//
// 注意 A 股色彩惯例：红涨绿跌（--up 红 / --down 绿）只用于「行情方向」展示（价格/涨跌幅/图表，
// 业务组件里用 .up/.down className）。antd 的 colorSuccess/colorError 保留通用语义（操作反馈），
// 不映射到 up/down，避免「绿=跌」与「绿=成功」语义冲突。

export const lightTokens = {
  bg: '#f4f6fa',
  surface: '#ffffff',
  surface2: '#f7f9fc',
  elevated: '#eef2f8',
  border: '#e6eaf0',
  border2: '#d4dbe6',
  fg: '#1a2230',
  fg2: '#52617a',
  muted: '#8a96a8',
  accent: '#3d8bff',
  accentDim: 'rgba(61,139,255,0.10)',
  up: '#ff4d4f',
  down: '#2ec27e',
  warn: '#f5a623',
  neutral: '#6b7a90',
  radius: 8,
  fontSans:
    '-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
  fontMono:
    '"SF Mono","JetBrains Mono","IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace',
} as const

// dark 段：suying-app.css 的 :root[data-theme="dark"] 只覆盖与浅色不同的项；
// accent / up / down / warn / radius / font* 在深色下继承浅色同值，这里补全为完整对象。
export const darkTokens = {
  bg: '#0b0e14',
  surface: '#11161f',
  surface2: '#161c28',
  elevated: '#1b2330',
  border: '#1f2733',
  border2: '#2a3444',
  fg: '#e8edf4',
  fg2: '#9aa7b8',
  muted: '#5e6a7d',
  accent: '#3d8bff',
  accentDim: 'rgba(61,139,255,0.14)',
  up: '#ff4d4f',
  down: '#2ec27e',
  warn: '#f5a623',
  neutral: '#6b7a90',
  radius: 8,
  fontSans:
    '-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
  fontMono:
    '"SF Mono","JetBrains Mono","IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace',
} as const

// signal 评级语义色（A 股红涨绿跌：强买=红 / 卖出=绿，中间档过渡）。
// page 层禁裸 hex 统一走此组；本处是 token 定义，hex 合规。
export const signalLevelTokens = {
  STRONG_BUY: lightTokens.up, // 红，强正向
  BUY: lightTokens.warn, // 橙，正向
  HOLD: lightTokens.accent, // 蓝，中性
  REDUCE: '#faad14', // 黄，偏负向（介于 warn 与 down）
  SELL: lightTokens.down, // 绿，强负向
  TIMING_ALERT: '#722ed1', // 紫，拐点提示
} as const

// alpha 派生（ECharts 配置色不吃 CSS var，JS 常量桥接；与 lightTokens 对应 token 同源）
export const alpha = {
  accent: (a: number) => `rgba(61,139,255,${a})`,
  up: (a: number) => `rgba(255,77,79,${a})`,
  down: (a: number) => `rgba(46,194,126,${a})`,
  warn: (a: number) => `rgba(245,166,35,${a})`,
} as const

export type DesignTokens = typeof lightTokens

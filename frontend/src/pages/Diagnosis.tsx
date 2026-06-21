import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Card, Input, Button, Tag, Progress, Typography, Row, Col,
  Statistic, message, Spin, Tabs, Table, Collapse, Descriptions,
  Modal, Select, Space, Divider, Empty, Tooltip, Badge,
} from 'antd'
import {
  FundOutlined, SearchOutlined, ExportOutlined, SwapOutlined,
  RiseOutlined, FallOutlined, QuestionCircleOutlined,
  RadarChartOutlined, HistoryOutlined, FireOutlined,
  DollarOutlined, BankOutlined, RobotOutlined, SmileOutlined,
  ThunderboltOutlined, InfoCircleOutlined, DownloadOutlined,
  StockOutlined, TrophyOutlined, AimOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { diagnosisApi } from '../api/client'

const { Title, Text, Paragraph } = Typography
const { Panel } = Collapse
const { Option } = Select

// ── Types ──

interface FactorDetail {
  name: string
  score: number
  weight: number
  direction: 'bullish' | 'bearish' | 'neutral'
  detail?: string
}

interface CapitalFlow {
  north_bound: { net_inflow: number; trend: string }
  margin: { balance: number; ratio: number }
  dragon_tiger: { net_buy: number; institutions: number }
}

interface Fundamentals {
  pe: number
  pb: number
  roe: number
  revenue_growth: number
  profit_growth: number
  debt_ratio: number
  market_cap: number
}

interface SentimentData {
  news_score: number
  news_count: number
  research_rating: string
  research_target: number
  social_sentiment: number
}

interface PredictionPoint {
  date: string
  open: number
  close: number
  high: number
  low: number
}

// ── Backend-aligned interfaces (matching Pydantic DiagnosisReport) ──

interface DiagnosisReport {
  code: string
  overall_score: number
  grade: string
  recommendation: string
  recommendation_reason: string
  dimensions: Record<string, DimensionScore>
  key_levels: Record<string, number>
  risk_warnings: string[]
  kronos_available: boolean
  degraded: boolean
  degraded_dimensions: string[]
  created_at?: string
}

interface DimensionScore {
  name: string
  score: number
  weight: number
  grade: string
  status: string
  details?: Record<string, any>
  signals?: string[]
  // Sub-dimension optional fields
  factor_scores?: Record<string, number>
  trend?: string
  northbound_net?: number
  margin_balance?: number
  leaderboard_net?: number
  main_force_flow?: number
  pe_percentile?: number
  roe?: number
  revenue_growth?: number
  debt_ratio?: number
  pred_return?: number
  pred_30d_close?: number
  confidence?: number
  inflection_days?: number[]
  max_drawdown?: number
  news_sentiment?: number
  research_rating?: string
  analyst_target?: number
}

interface DiagnosisCompareResponse {
  stocks: DiagnosisReport[]
  ranking: Record<string, any>[]
  dimension_comparison: Record<string, Record<string, any>[]>
}

// ── Data transformer: Backend DiagnosisReport → Frontend DiagnosisResult ──

function transformHistoryItem(item: any): HistoryRecord {
  return {
    id: item.id,
    code: item.code,
    name: item.code,
    score: item.overall_score ?? item.score ?? 0,
    grade: item.grade ?? '',
    grade_label: item.recommendation ?? item.grade_label ?? '',
    created_at: item.created_at ?? '',
  }
}

function transformDiagnosisReport(report: DiagnosisReport): DiagnosisResult {
  const dims = report.dimensions
  const tech = dims['technical'] || ({} as DimensionScore)
  const capital = dims['capital_flow'] || ({} as DimensionScore)
  const fund = dims['fundamental'] || ({} as DimensionScore)
  const ai = dims['ai_predict'] || ({} as DimensionScore)
  const sent = dims['sentiment'] || ({} as DimensionScore)

  // Factor details from technical dimension factor_scores
  const factorScores = tech.factor_scores || {}
  const factorCount = Object.keys(factorScores).length || 1
  const factor_details: FactorDetail[] = Object.entries(factorScores).map(([name, score]) => ({
    name,
    score: Math.round(score),
    weight: +(1 / factorCount).toFixed(3),
    direction: (score >= 60 ? 'bullish' : score <= 40 ? 'bearish' : 'neutral') as FactorDetail['direction'],
    detail: tech.signals?.join('; ') || undefined,
  }))

  // Capital flow mapping
  const capital_flow: CapitalFlow = {
    north_bound: {
      net_inflow: capital.northbound_net || 0,
      trend: (capital.northbound_net || 0) >= 0 ? '净流入' : '净流出',
    },
    margin: {
      balance: +((capital.margin_balance || 0) / 10000).toFixed(2),
      ratio: 0,
    },
    dragon_tiger: {
      net_buy: capital.leaderboard_net || 0,
      institutions: 0,
    },
  }

  // Fundamentals mapping
  const fundamentals: Fundamentals = {
    pe: fund.pe_percentile || 0,
    pb: 0,
    roe: fund.roe || 0,
    revenue_growth: fund.revenue_growth || 0,
    profit_growth: 0,
    debt_ratio: fund.debt_ratio || 0,
    market_cap: 0,
  }

  // Sentiment mapping: news_sentiment is -1..1 → scale to 0..10
  const sentiments: SentimentData = {
    news_score: +(((sent.news_sentiment || 0) + 1) * 5).toFixed(1),
    news_count: 0,
    research_rating: sent.research_rating || '无',
    research_target: sent.analyst_target || 0,
    social_sentiment: 0,
  }

  return {
    code: report.code,
    name: report.code,
    market: report.code.startsWith('6') ? '上海'
      : report.code.startsWith('00') || report.code.startsWith('30') ? '深圳'
      : '科创板',
    current_price: 0,
    change_pct: 0,
    overall_score: report.overall_score,
    grade: report.grade,
    grade_label: report.recommendation,
    dimensions: {
      technical: tech.score || 0,
      capital: capital.score || 0,
      fundamental: fund.score || 0,
      ai_prediction: ai.score || 0,
      sentiment: sent.score || 0,
    },
    factor_details,
    capital_flow,
    fundamentals,
    sentiment: sentiments,
    historical_klines: [],
    predictions: [],
    suggestion: {
      action: report.recommendation,
      buy_price: report.key_levels?.['entry'] || 0,
      stop_loss: report.key_levels?.['stop_loss'] || 0,
      take_profit: report.key_levels?.['take_profit'] || report.key_levels?.['resistance'] || 0,
      confidence: +((ai.confidence || 0) * 100).toFixed(0),
      reasoning: report.recommendation_reason,
    },
  }
}

interface DiagnosisResult {
  code: string
  name: string
  market: string
  current_price: number
  change_pct: number
  overall_score: number
  grade: string
  grade_label: string
  dimensions: {
    technical: number
    capital: number
    fundamental: number
    ai_prediction: number
    sentiment: number
  }
  factor_details: FactorDetail[]
  capital_flow: CapitalFlow
  fundamentals: Fundamentals
  sentiment: SentimentData
  historical_klines: PredictionPoint[]
  predictions: PredictionPoint[]
  suggestion: {
    action: string
    buy_price: number
    stop_loss: number
    take_profit: number
    confidence: number
    reasoning: string
  }
}

interface HistoryRecord {
  id: number
  code: string
  name: string
  score: number
  grade: string
  grade_label: string
  created_at: string
}

// ── Constants ──

const GRADE_CONFIG: Record<string, { color: string; label: string; bg: string }> = {
  'A+': { color: '#ff1f1f', label: 'A+', bg: '#fff1f0' },
  'A':  { color: '#ff1f1f', label: 'A',  bg: '#fff1f0' },
  'B+': { color: '#ff7a45', label: 'B+', bg: '#fff7e6' },
  'B':  { color: '#ff7a45', label: 'B',  bg: '#fff7e6' },
  'C+': { color: '#faad14', label: 'C+', bg: '#fffbe6' },
  'C':  { color: '#faad14', label: 'C',  bg: '#fffbe6' },
  'D':  { color: '#1890ff', label: 'D',  bg: '#e6f7ff' },
  'E':  { color: '#52c41a', label: 'E',  bg: '#f6ffed' },
}

const RECOMMENDATION_COLORS: Record<string, string> = {
  '强烈买入': '#ff1f1f',
  '买入':     '#ff7a45',
  '持有':     '#faad14',
  '减仓':     '#1890ff',
  '卖出':     '#52c41a',
}

const DIMENSION_NAMES: Record<string, string> = {
  technical: '技术面', capital: '资金面', fundamental: '基本面',
  ai_prediction: 'AI预测', sentiment: '情绪面',
}

const DIMENSION_ICONS: Record<string, React.ReactNode> = {
  technical: <ThunderboltOutlined />,
  capital: <DollarOutlined />,
  fundamental: <BankOutlined />,
  ai_prediction: <RobotOutlined />,
  sentiment: <SmileOutlined />,
}

// ── Radar Chart Options ──

function buildRadarOption(dimensions: DiagnosisResult['dimensions'], dark = false) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const axisColor = dark ? '#444' : '#e8e8e8'
  const splitColor = dark ? '#333' : '#f0f0f0'
  return {
    tooltip: { trigger: 'item' as const },
    legend: {
      data: ['当前诊断'],
      bottom: 0,
      textStyle: { color: textColor, fontSize: 12 },
    },
    radar: {
      center: ['50%', '48%'],
      radius: '65%',
      indicator: [
        { name: '技术面', max: 100 },
        { name: '资金面', max: 100 },
        { name: '基本面', max: 100 },
        { name: 'AI预测', max: 100 },
        { name: '情绪面', max: 100 },
      ],
      axisName: { color: textColor, fontSize: 11 },
      splitArea: {
        areaStyle: { color: [splitColor, 'transparent'] },
      },
      axisLine: { lineStyle: { color: axisColor } },
      splitLine: { lineStyle: { color: axisColor } },
    },
    series: [{
      type: 'radar',
      name: '诊断',
      data: [{
        value: [
          dimensions.technical,
          dimensions.capital,
          dimensions.fundamental,
          dimensions.ai_prediction,
          dimensions.sentiment,
        ],
        name: '当前诊断',
      }],
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: '#1677ff', width: 2 },
      areaStyle: { color: 'rgba(22,119,255,0.15)' },
      itemStyle: { color: '#1677ff' },
    }],
  }
}

function buildCompareRadarOption(
  stocks: { name: string; dims: DiagnosisResult['dimensions'] }[],
  dark = false,
) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const axisColor = dark ? '#444' : '#e8e8e8'
  const splitColor = dark ? '#333' : '#f0f0f0'
  const colors = ['#1677ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1']
  return {
    tooltip: { trigger: 'item' as const },
    legend: {
      data: stocks.map(s => s.name),
      bottom: 0,
      textStyle: { color: textColor, fontSize: 11 },
    },
    radar: {
      center: ['50%', '45%'],
      radius: '60%',
      indicator: [
        { name: '技术面', max: 100 },
        { name: '资金面', max: 100 },
        { name: '基本面', max: 100 },
        { name: 'AI预测', max: 100 },
        { name: '情绪面', max: 100 },
      ],
      axisName: { color: textColor, fontSize: 11 },
      splitArea: {
        areaStyle: { color: [splitColor, 'transparent'] },
      },
      axisLine: { lineStyle: { color: axisColor } },
      splitLine: { lineStyle: { color: axisColor } },
    },
    series: stocks.map((s, i) => ({
      type: 'radar',
      name: s.name,
      data: [{
        value: [
          s.dims.technical,
          s.dims.capital,
          s.dims.fundamental,
          s.dims.ai_prediction,
          s.dims.sentiment,
        ],
        name: s.name,
      }],
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: colors[i % colors.length], width: 2 },
      areaStyle: { color: 'transparent' },
      itemStyle: { color: colors[i % colors.length] },
    })),
  }
}

// ── K-line + Prediction Chart ──

function buildKlinePredictionOption(
  historical: PredictionPoint[],
  predictions: PredictionPoint[],
  dark = false,
) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const borderColor = dark ? '#333' : '#e5e5e5'

  const allDates = [
    ...historical.map(p => p.date),
    ...predictions.map(p => p.date),
  ]

  const hO = historical.map(p => p.open)
  const hC = historical.map(p => p.close)
  const hL = historical.map(p => p.low)
  const hH = historical.map(p => p.high)

  // Build candlestick data: [open, close, low, high]
  const histCandle = historical.map(p => [p.open, p.close, p.low, p.high])

  // Build prediction line (dashed)
  const predDates = predictions.map(p => p.date)
  const predClose = predictions.map(p => p.close)

  // Separator: last historical close
  const lastHistClose = historical.length > 0 ? historical[historical.length - 1].close : 0

  return {
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const },
    },
    legend: {
      data: ['历史K线', 'AI预测'],
      bottom: 0,
      textStyle: { color: textColor, fontSize: 12 },
    },
    grid: {
      left: '3%', right: '4%', top: '10%', bottom: '14%',
      containLabel: true,
    },
    xAxis: {
      type: 'category' as const,
      data: allDates,
      axisLine: { lineStyle: { color: borderColor } },
      axisLabel: {
        color: textColor,
        fontSize: 10,
        rotate: 30,
        interval: Math.max(Math.floor(allDates.length / 8), 0),
      },
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      axisLine: { lineStyle: { color: borderColor } },
      splitLine: { lineStyle: { color: borderColor, type: 'dashed' as const } },
      axisLabel: { color: textColor, fontSize: 10 },
    },
    series: [
      {
        name: '历史K线',
        type: 'candlestick',
        data: histCandle,
        itemStyle: {
          color: '#ef232a',
          color0: '#14b143',
          borderColor: '#ef232a',
          borderColor0: '#14b143',
        },
      },
      {
        name: 'AI预测',
        type: 'line',
        data: [
          ...historical.map(() => null),
          ...predictions.map(p => [p.open, p.close, p.low, p.high]),
        ],
        // Actually for prediction we want a line, not candlestick
      },
    ],
  }
}

// Build a more practical version: line chart overlay
function buildPredictionOverlayChart(
  historical: PredictionPoint[],
  predictions: PredictionPoint[],
  dark = false,
) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const borderColor = dark ? '#333' : '#e5e5e5'

  const histDates = historical.map(p => p.date)
  const histClose = historical.map(p => p.close)
  const predDates = predictions.map(p => p.date)

  // Combine dates for x-axis
  const allDates = [...histDates, ...predDates]

  // For the line connecting last historical to first prediction
  const lastHistIdx = histDates.length - 1

  const predCloseFull = [
    ...new Array(histDates.length).fill(null),
    ...predictions.map(p => p.close),
  ] as (number | null)[]

  // Fill in the connection point
  if (histClose.length > 0 && predictions.length > 0) {
    predCloseFull[lastHistIdx] = histClose[lastHistIdx]
  }

  // Prediction band (confidence interval - use high/low as bounds)
  const predHighFull = [
    ...new Array(histDates.length).fill(null),
    ...predictions.map(p => p.high),
  ] as (number | null)[]
  const predLowFull = [
    ...new Array(histDates.length).fill(null),
    ...predictions.map(p => p.low),
  ] as (number | null)[]
  if (histClose.length > 0 && predictions.length > 0) {
    predHighFull[lastHistIdx] = histClose[lastHistIdx]
    predLowFull[lastHistIdx] = histClose[lastHistIdx]
  }

  return {
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!params || params.length === 0) return ''
        const date = params[0].axisValue
        let html = `<div style="font-weight:bold;margin-bottom:4px">${date}</div>`
        params.forEach((p: any) => {
          if (p.value != null) {
            html += `<div>${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}</div>`
          }
        })
        return html
      },
    },
    legend: {
      data: ['历史收盘', 'AI预测', '预测上限', '预测下限'],
      bottom: 0,
      textStyle: { color: textColor, fontSize: 11 },
    },
    grid: { left: '3%', right: '4%', top: '10%', bottom: '14%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: allDates,
      axisLine: { lineStyle: { color: borderColor } },
      axisLabel: {
        color: textColor, fontSize: 10,
        interval: Math.max(Math.floor(allDates.length / 10), 0),
      },
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      axisLine: { lineStyle: { color: borderColor } },
      splitLine: { lineStyle: { color: borderColor, type: 'dashed' as const } },
      axisLabel: { color: textColor, fontSize: 10 },
    },
    series: [
      {
        name: '历史收盘',
        type: 'line',
        data: histClose,
        smooth: false,
        lineStyle: { color: '#1677ff', width: 2 },
        itemStyle: { color: '#1677ff' },
        symbol: 'none',
      },
      {
        name: 'AI预测',
        type: 'line',
        data: predCloseFull,
        smooth: true,
        lineStyle: { color: '#fa8c16', width: 2, type: 'dashed' as const },
        itemStyle: { color: '#fa8c16' },
        symbol: 'circle',
        symbolSize: 4,
        connectNulls: true,
      },
      {
        name: '预测上限',
        type: 'line',
        data: predHighFull,
        smooth: true,
        lineStyle: { color: '#ffd591', width: 1, type: 'dotted' as const },
        itemStyle: { color: '#ffd591' },
        symbol: 'none',
        connectNulls: true,
      },
      {
        name: '预测下限',
        type: 'line',
        data: predLowFull,
        smooth: true,
        lineStyle: { color: '#ffd591', width: 1, type: 'dotted' as const },
        itemStyle: { color: '#ffd591' },
        symbol: 'none',
        connectNulls: true,
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(250,140,22,0.08)' },
              { offset: 1, color: 'rgba(250,140,22,0.02)' },
            ],
          },
        },
      },
    ],
  }
}

// ── Component ──

export default function Diagnosis() {
  const [searchParams] = useSearchParams()

  // Search state
  const [code, setCode] = useState(searchParams.get('code') || '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DiagnosisResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // History state
  const [history, setHistory] = useState<HistoryRecord[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [expandedHistoryRow, setExpandedHistoryRow] = useState<number | null>(null)
  const [historyDetail, setHistoryDetail] = useState<DiagnosisResult | null>(null)
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false)

  // Compare modal
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareCodes, setCompareCodes] = useState<string[]>([])
  const [compareResults, setCompareResults] = useState<DiagnosisResult[]>([])
  const [compareLoading, setCompareLoading] = useState(false)

  // Active tab
  const [activeTab, setActiveTab] = useState('diagnosis')

  // ── API calls ──

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const { data } = await diagnosisApi.getHistory()
      const rawItems = data.items || []
      setHistory(rawItems.map(transformHistoryItem))
    } catch {
      message.error('历史记录加载失败，请稍后重试')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const runDiagnosis = useCallback(async (stockCode: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await diagnosisApi.analyze(stockCode)
      const transformed = transformDiagnosisReport(res.data)
      setResult(transformed)
      message.success(`诊断完成: ${transformed.grade_label}`)
      // Refresh history
      loadHistory()
    } catch {
      setError('诊断服务暂不可用，请稍后重试')
      message.error('诊断失败，请检查网络连接后重试')
    } finally {
      setLoading(false)
    }
  }, [loadHistory])

  const loadHistoryDetail = useCallback(async (stockCode: string) => {
    setHistoryDetailLoading(true)
    try {
      const res = await diagnosisApi.analyze(stockCode)
      setHistoryDetail(transformDiagnosisReport(res.data))
    } catch {
      setHistoryDetail(null)
      message.error('加载诊断详情失败')
    } finally {
      setHistoryDetailLoading(false)
    }
  }, [])

  const runCompare = useCallback(async (codes: string[]) => {
    setCompareLoading(true)
    try {
      const res = await diagnosisApi.compare(codes)
      const stocks: DiagnosisReport[] = res.data.stocks || []
      setCompareResults(stocks.map(transformDiagnosisReport))
    } catch {
      setCompareResults([])
      message.error('对比功能暂不可用，请稍后重试')
    } finally {
      setCompareLoading(false)
    }
  }, [])

  // Load history on mount
  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  // Auto-run diagnosis from URL param (?code=000001)
  useEffect(() => {
    const urlCode = searchParams.get('code')
    if (urlCode && urlCode.trim()) {
      setCode(urlCode.trim())
      setActiveTab('diagnosis')
      runDiagnosis(urlCode.trim())
    }
  }, [])  // run once on mount

  // ── Handlers ──

  const handleSearch = () => {
    if (!code.trim()) {
      message.warning('请输入股票代码')
      return
    }
    setActiveTab('diagnosis')
    runDiagnosis(code.trim())
  }

  const handleExportPdf = async () => {
    if (!result) return
    try {
      const res = await diagnosisApi.getReportPdf(result.code)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${result.code}_诊断报告.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success('PDF 报告下载中...')
    } catch {
      message.error('PDF 导出失败，请稍后重试')
    }
  }

  const handleOpenCompare = () => {
    if (!result) {
      message.warning('请先完成诊断')
      return
    }
    setCompareCodes([result.code])
    setCompareResults([])
    setCompareOpen(true)
  }

  const handleAddCompareStock = (stockCode: string) => {
    if (!stockCode.trim()) return
    if (compareCodes.includes(stockCode.trim())) {
      message.warning('该股票已在对比列表中')
      return
    }
    if (compareCodes.length >= 5) {
      message.warning('最多对比5只股票')
      return
    }
    setCompareCodes(prev => [...prev, stockCode.trim()])
  }

  const handleRemoveCompareStock = (stockCode: string) => {
    setCompareCodes(prev => prev.filter(c => c !== stockCode))
  }

  const handleRunCompare = () => {
    if (compareCodes.length < 2) {
      message.warning('至少选择2只股票进行对比')
      return
    }
    runCompare(compareCodes)
  }

  const handleHistoryRowClick = (record: HistoryRecord) => {
    if (expandedHistoryRow === record.id) {
      setExpandedHistoryRow(null)
      setHistoryDetail(null)
    } else {
      setExpandedHistoryRow(record.id)
      loadHistoryDetail(record.code)
    }
  }

  // ── Render helpers ──

  const renderGradeTag = (grade: string, label: string) => {
    const config = GRADE_CONFIG[grade]
    if (!config) return <Tag>{label}</Tag>
    return (
      <Tag style={{
        color: config.color, background: config.bg,
        border: `1px solid ${config.color}33`,
        fontWeight: 700, fontSize: 13, padding: '2px 12px', borderRadius: 4,
      }}>
        {label}
      </Tag>
    )
  }

  const renderScoreCircle = (score: number) => {
    const color = score >= 80 ? '#ff1f1f' : score >= 65 ? '#ff7a45' : score >= 45 ? '#faad14' : score >= 30 ? '#1890ff' : '#52c41a'
    return (
      <div style={{ textAlign: 'center', padding: '8px 0' }}>
        <div style={{
          fontSize: 56, fontWeight: 800, color, lineHeight: 1.1,
          fontFamily: '-apple-system, "PingFang SC", "Helvetica Neue", sans-serif',
        }}>
          {score}
        </div>
        <Text type="secondary" style={{ fontSize: 13 }}>综合评分 / 100</Text>
      </div>
    )
  }

  const renderFactorTable = (factors: FactorDetail[]) => {
    const columns = [
      {
        title: '因子名称', dataIndex: 'name', key: 'name', width: 120,
        render: (v: string) => <Text strong style={{ fontSize: 13 }}>{v}</Text>,
      },
      {
        title: '得分', dataIndex: 'score', key: 'score', width: 80, sorter: (a: FactorDetail, b: FactorDetail) => a.score - b.score,
        render: (v: number) => {
          const color = v >= 70 ? '#52c41a' : v >= 40 ? '#faad14' : '#ff4d4f'
          return <Text strong style={{ color }}>{v}</Text>
        },
      },
      {
        title: '权重', dataIndex: 'weight', key: 'weight', width: 80,
        render: (v: number) => `${(v * 100).toFixed(0)}%`,
      },
      {
        title: '方向', dataIndex: 'direction', key: 'direction', width: 80,
        render: (v: string) => {
          const icon = v === 'bullish' ? <RiseOutlined style={{ color: '#ff4d4f' }} /> :
            v === 'bearish' ? <FallOutlined style={{ color: '#52c41a' }} /> :
            <span style={{ color: '#faad14' }}>—</span>
          const label = v === 'bullish' ? '看多' : v === 'bearish' ? '看空' : '中性'
          return <Space size={4}>{icon}<Text style={{ fontSize: 12 }}>{label}</Text></Space>
        },
      },
      {
        title: '说明', dataIndex: 'detail', key: 'detail',
        render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>,
      },
    ]
    return (
      <Table
        dataSource={factors}
        columns={columns}
        rowKey="name"
        size="small"
        pagination={false}
        scroll={{ x: 500 }}
      />
    )
  }

  // ── History table columns ──

  const historyColumns = [
    {
      title: '股票代码', dataIndex: 'code', key: 'code', width: 100,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '名称', dataIndex: 'name', key: 'name', width: 100,
    },
    {
      title: '综合评分', dataIndex: 'score', key: 'score', width: 90,
      sorter: (a: HistoryRecord, b: HistoryRecord) => a.score - b.score,
      render: (v: number) => {
        const color = v >= 80 ? '#ff1f1f' : v >= 65 ? '#ff7a45' : v >= 45 ? '#faad14' : v >= 30 ? '#1890ff' : '#52c41a'
        return <Text strong style={{ color, fontSize: 15 }}>{v}</Text>
      },
    },
    {
      title: '等级', dataIndex: 'grade', key: 'grade', width: 100,
      render: (_: string, record: HistoryRecord) => renderGradeTag(record.grade, record.grade_label),
    },
    {
      title: '诊断时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      sorter: (a: HistoryRecord, b: HistoryRecord) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{new Date(v).toLocaleString('zh-CN')}</Text>,
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: any, record: HistoryRecord) => (
        <Button
          type="link"
          size="small"
          onClick={(e) => {
            e.stopPropagation()
            setCode(record.code)
            setActiveTab('diagnosis')
            runDiagnosis(record.code)
          }}
        >
          重新诊断
        </Button>
      ),
    },
  ]

  // ── Render ──

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <Title level={4} style={{ margin: 0 }}>
          <FundOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          个股诊断
        </Title>
        <Text type="secondary">五维分析：技术面 · 资金面 · 基本面 · AI预测 · 情绪面</Text>
      </div>

      {/* Tabs */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'diagnosis',
            label: <span><SearchOutlined /> 智能诊断</span>,
            children: (
              <div>
                {/* Search Bar */}
                <Card style={{ borderRadius: 8, marginBottom: 16 }}>
                  <Row gutter={16} align="middle">
                    <Col flex="auto">
                      <Input.Search
                        placeholder="输入股票代码，如 000001、600519、300750"
                        value={code}
                        onChange={e => setCode(e.target.value)}
                        onSearch={handleSearch}
                        enterButton={
                          <Button type="primary" loading={loading} icon={<SearchOutlined />}>
                            开始诊断
                          </Button>
                        }
                        size="large"
                        style={{ maxWidth: 520 }}
                      />
                    </Col>
                    <Col>
                      <Space>
                        <Text type="secondary" style={{ fontSize: 12 }}>快速示例：</Text>
                        {['000001', '600519', '300750'].map(c => (
                          <Tag
                            key={c}
                            style={{ cursor: 'pointer' }}
                            color={code === c ? 'blue' : 'default'}
                            onClick={() => { setCode(c); runDiagnosis(c) }}
                          >
                            {c}
                          </Tag>
                        ))}
                      </Space>
                    </Col>
                  </Row>
                </Card>

                {/* Loading */}
                {loading && (
                  <Card style={{ borderRadius: 8, marginBottom: 16, textAlign: 'center', padding: 40 }}>
                    <Spin size="large" />
                    <div style={{ marginTop: 16 }}>
                      <Text type="secondary">正在进行五维深度诊断，请稍候...</Text>
                    </div>
                  </Card>
                )}

                {/* Error */}
                {error && !loading && (
                  <Card style={{ borderRadius: 8, marginBottom: 16 }}>
                    <Text type="danger">{error}</Text>
                  </Card>
                )}

                {/* Results */}
                {result && !loading && (
                  <>

                    {/* ── Top: Score + Grade + Price ── */}
                    <Card style={{ borderRadius: 8, marginBottom: 16 }}>
                      <Row gutter={[24, 16]} align="middle">
                        <Col span={8} style={{ textAlign: 'center' }}>
                          {renderScoreCircle(result.overall_score)}
                          <div style={{ marginTop: 4 }}>
                            {renderGradeTag(result.grade, result.grade_label)}
                          </div>
                        </Col>
                        <Col span={8} style={{ textAlign: 'center' }}>
                          <div>
                            <Text type="secondary" style={{ fontSize: 12 }}>{result.code}</Text>
                          </div>
                          <div style={{ fontSize: 20, fontWeight: 700, margin: '4px 0' }}>
                            {result.name}
                          </div>
                          <div style={{ fontSize: 24, fontWeight: 700 }}>
                            {result.current_price.toFixed(2)}
                          </div>
                          <div>
                            <Tag color={result.change_pct >= 0 ? 'red' : 'green'} style={{ fontWeight: 600 }}>
                              {result.change_pct >= 0 ? '+' : ''}{result.change_pct}%
                            </Tag>
                          </div>
                          <Text type="secondary" style={{ fontSize: 11 }}>{result.market}</Text>
                        </Col>
                        <Col span={8}>
                          <div style={{ height: 220 }}>
                            <ReactECharts
                              option={buildRadarOption(result.dimensions)}
                              style={{ height: '100%' }}
                              opts={{ renderer: 'svg' }}
                            />
                          </div>
                        </Col>
                      </Row>
                    </Card>

                    {/* ── Action Buttons ── */}
                    <Card style={{ borderRadius: 8, marginBottom: 16 }}>
                      <Row gutter={12}>
                        <Col>
                          <Button
                            icon={<DownloadOutlined />}
                            onClick={handleExportPdf}
                          >
                            导出 PDF 报告
                          </Button>
                        </Col>
                        <Col>
                          <Button
                            icon={<SwapOutlined />}
                            onClick={handleOpenCompare}
                          >
                            多股对比
                          </Button>
                        </Col>
                      </Row>
                    </Card>

                    {/* ── Dimension Details ── */}
                    <Card title="五维详情" style={{ borderRadius: 8, marginBottom: 16 }}>
                      <Collapse
                        size="small"
                        expandIconPosition="end"
                        items={[
                          {
                            key: 'technical',
                            label: (
                              <Space>
                                {DIMENSION_ICONS.technical}
                                <Text strong>技术面</Text>
                                <Progress
                                  percent={result.dimensions.technical}
                                  size="small"
                                  strokeColor="#1677ff"
                                  style={{ width: 120, margin: 0 }}
                                />
                              </Space>
                            ),
                            children: (
                              <div>
                                <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 12 }}>
                                  基于多因子模型的技术面分析，涵盖动量、趋势、波动率、成交量等维度。
                                </Paragraph>
                                {renderFactorTable(result.factor_details)}
                              </div>
                            ),
                          },
                          {
                            key: 'capital',
                            label: (
                              <Space>
                                {DIMENSION_ICONS.capital}
                                <Text strong>资金面</Text>
                                <Progress
                                  percent={result.dimensions.capital}
                                  size="small"
                                  strokeColor="#52c41a"
                                  style={{ width: 120, margin: 0 }}
                                />
                              </Space>
                            ),
                            children: (
                              <div>
                                <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 12 }}>
                                  监测北向资金、融资融券、龙虎榜等主力资金动向。
                                </Paragraph>
                                <Row gutter={[16, 16]}>
                                  <Col span={8}>
                                    <Card size="small" title="北向资金" style={{ borderRadius: 6 }}>
                                      <Statistic
                                        title="净流入(万元)"
                                        value={result.capital_flow.north_bound.net_inflow}
                                        valueStyle={{
                                          color: result.capital_flow.north_bound.net_inflow >= 0 ? '#ff4d4f' : '#52c41a',
                                          fontSize: 20,
                                        }}
                                      />
                                      <Text type="secondary" style={{ fontSize: 12 }}>
                                        趋势：{result.capital_flow.north_bound.trend}
                                      </Text>
                                    </Card>
                                  </Col>
                                  <Col span={8}>
                                    <Card size="small" title="融资融券" style={{ borderRadius: 6 }}>
                                      <Statistic
                                        title="融资余额(亿)"
                                        value={result.capital_flow.margin.balance}
                                        valueStyle={{ fontSize: 20 }}
                                      />
                                      <Text type="secondary" style={{ fontSize: 12 }}>
                                        占比：{result.capital_flow.margin.ratio}%
                                      </Text>
                                    </Card>
                                  </Col>
                                  <Col span={8}>
                                    <Card size="small" title="龙虎榜" style={{ borderRadius: 6 }}>
                                      <Statistic
                                        title="净买入(万元)"
                                        value={result.capital_flow.dragon_tiger.net_buy}
                                        valueStyle={{
                                          color: result.capital_flow.dragon_tiger.net_buy >= 0 ? '#ff4d4f' : '#52c41a',
                                          fontSize: 20,
                                        }}
                                      />
                                      <Text type="secondary" style={{ fontSize: 12 }}>
                                        机构席位：{result.capital_flow.dragon_tiger.institutions}家
                                      </Text>
                                    </Card>
                                  </Col>
                                </Row>
                              </div>
                            ),
                          },
                          {
                            key: 'fundamental',
                            label: (
                              <Space>
                                {DIMENSION_ICONS.fundamental}
                                <Text strong>基本面</Text>
                                <Progress
                                  percent={result.dimensions.fundamental}
                                  size="small"
                                  strokeColor="#faad14"
                                  style={{ width: 120, margin: 0 }}
                                />
                              </Space>
                            ),
                            children: (
                              <div>
                                <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 12 }}>
                                  核心财务指标分析，评估公司盈利能力、成长性和财务健康度。
                                </Paragraph>
                                <Descriptions bordered size="small" column={3}>
                                  <Descriptions.Item label="市盈率(PE)">
                                    <Text strong>{result.fundamentals.pe}</Text>
                                    <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
                                      {result.fundamentals.pe < 15 ? '偏低' : result.fundamentals.pe < 30 ? '合理' : '偏高'}
                                    </Text>
                                  </Descriptions.Item>
                                  <Descriptions.Item label="市净率(PB)">
                                    <Text strong>{result.fundamentals.pb}</Text>
                                  </Descriptions.Item>
                                  <Descriptions.Item label="ROE">
                                    <Text strong style={{ color: result.fundamentals.roe >= 15 ? '#52c41a' : '#faad14' }}>
                                      {result.fundamentals.roe}%
                                    </Text>
                                  </Descriptions.Item>
                                  <Descriptions.Item label="营收增速">
                                    <Text strong style={{ color: result.fundamentals.revenue_growth >= 0 ? '#ff4d4f' : '#52c41a' }}>
                                      {result.fundamentals.revenue_growth}%
                                    </Text>
                                  </Descriptions.Item>
                                  <Descriptions.Item label="利润增速">
                                    <Text strong style={{ color: result.fundamentals.profit_growth >= 0 ? '#ff4d4f' : '#52c41a' }}>
                                      {result.fundamentals.profit_growth}%
                                    </Text>
                                  </Descriptions.Item>
                                  <Descriptions.Item label="资产负债率">
                                    <Text strong>{result.fundamentals.debt_ratio}%</Text>
                                  </Descriptions.Item>
                                  <Descriptions.Item label="总市值(亿)">
                                    <Text strong>{result.fundamentals.market_cap}</Text>
                                  </Descriptions.Item>
                                </Descriptions>
                              </div>
                            ),
                          },
                          {
                            key: 'ai_prediction',
                            label: (
                              <Space>
                                {DIMENSION_ICONS.ai_prediction}
                                <Text strong>AI预测 (Kronos 30日)</Text>
                                <Progress
                                  percent={result.dimensions.ai_prediction}
                                  size="small"
                                  strokeColor="#722ed1"
                                  style={{ width: 120, margin: 0 }}
                                />
                              </Space>
                            ),
                            children: (
                              <div>
                                <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 12 }}>
                                  Kronos 大模型对未来30个交易日的K线预测（实线为历史收盘价，虚线为AI预测区间）。
                                </Paragraph>
                                <div style={{ height: 400 }}>
                                  <ReactECharts
                                    option={buildPredictionOverlayChart(
                                      result.historical_klines,
                                      result.predictions,
                                    )}
                                    style={{ height: '100%' }}
                                    opts={{ renderer: 'svg' }}
                                  />
                                </div>
                                <div style={{ marginTop: 8, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                                  <Tag color="blue">历史收盘</Tag>
                                  <Tag color="orange">AI预测收盘 (虚线)</Tag>
                                  <Tag color="gold">预测置信区间</Tag>
                                </div>
                              </div>
                            ),
                          },
                          {
                            key: 'sentiment',
                            label: (
                              <Space>
                                {DIMENSION_ICONS.sentiment}
                                <Text strong>情绪面</Text>
                                <Progress
                                  percent={result.dimensions.sentiment}
                                  size="small"
                                  strokeColor="#eb2f96"
                                  style={{ width: 120, margin: 0 }}
                                />
                              </Space>
                            ),
                            children: (
                              <div>
                                <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 12 }}>
                                  综合新闻舆情、研报评级和社交媒体情绪分析。
                                </Paragraph>
                                <Row gutter={[16, 16]}>
                                  <Col span={8}>
                                    <Card size="small" style={{ borderRadius: 6, textAlign: 'center' }}>
                                      <Statistic
                                        title="新闻情感分"
                                        value={result.sentiment.news_score}
                                        suffix="/ 10"
                                        valueStyle={{ fontSize: 24 }}
                                      />
                                      <Text type="secondary" style={{ fontSize: 12 }}>
                                        近30日 {result.sentiment.news_count} 篇报道
                                      </Text>
                                    </Card>
                                  </Col>
                                  <Col span={8}>
                                    <Card size="small" style={{ borderRadius: 6, textAlign: 'center' }}>
                                      <Statistic
                                        title="研报评级"
                                        value={result.sentiment.research_rating}
                                        valueStyle={{
                                          fontSize: 24,
                                          color: result.sentiment.research_rating === '买入' ? '#ff4d4f' :
                                            result.sentiment.research_rating === '增持' ? '#fa8c16' : '#1890ff',
                                        }}
                                      />
                                      <Text type="secondary" style={{ fontSize: 12 }}>
                                        目标价：{result.sentiment.research_target}
                                      </Text>
                                    </Card>
                                  </Col>
                                  <Col span={8}>
                                    <Card size="small" style={{ borderRadius: 6, textAlign: 'center' }}>
                                      <Statistic
                                        title="社交情绪"
                                        value={result.sentiment.social_sentiment}
                                        suffix="/ 10"
                                        valueStyle={{ fontSize: 24 }}
                                      />
                                    </Card>
                                  </Col>
                                </Row>
                              </div>
                            ),
                          },
                        ]}
                      />
                    </Card>

                    {/* ── Operation Suggestion ── */}
                    <Card style={{ borderRadius: 8, marginBottom: 16 }}>
                      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
                        <AimOutlined style={{ fontSize: 18, color: '#1677ff', marginRight: 8 }} />
                        <Text strong style={{ fontSize: 15 }}>操作建议</Text>
                      </div>
                      <Row gutter={[16, 16]}>
                        <Col span={6}>
                          <Card size="small" style={{ background: '#f6ffed', borderRadius: 6, border: '1px solid #b7eb8f' }}>
                            <Statistic
                              title="建议买入价"
                              value={result.suggestion.buy_price}
                              precision={2}
                              valueStyle={{ color: '#52c41a', fontSize: 20 }}
                              prefix={<TrophyOutlined />}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small" style={{ background: '#fff7e6', borderRadius: 6, border: '1px solid #ffd591' }}>
                            <Statistic
                              title="止损价"
                              value={result.suggestion.stop_loss}
                              precision={2}
                              valueStyle={{ color: '#fa8c16', fontSize: 20 }}
                              prefix={<FallOutlined />}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small" style={{ background: '#fff1f0', borderRadius: 6, border: '1px solid #ffa39e' }}>
                            <Statistic
                              title="止盈目标"
                              value={result.suggestion.take_profit}
                              precision={2}
                              valueStyle={{ color: '#ff4d4f', fontSize: 20 }}
                              prefix={<RiseOutlined />}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small" style={{ borderRadius: 6 }}>
                            <Statistic
                              title="建议操作"
                              value={result.suggestion.action}
                              valueStyle={{ fontSize: 18, color: '#1677ff' }}
                            />
                            <div style={{ marginTop: 4 }}>
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                置信度：{result.suggestion.confidence}%
                              </Text>
                            </div>
                          </Card>
                        </Col>
                      </Row>
                      <Card size="small" style={{ marginTop: 12, borderRadius: 6, background: '#fafafa' }}>
                        <Space>
                          <InfoCircleOutlined style={{ color: '#1677ff' }} />
                          <Text style={{ fontSize: 13 }}>{result.suggestion.reasoning}</Text>
                        </Space>
                      </Card>
                    </Card>
                  </>
                )}

                {/* Empty state */}
                {!result && !loading && !error && (
                  <Card style={{ borderRadius: 8, textAlign: 'center', padding: '60px 20px' }}>
                    <FundOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />
                    <div style={{ marginTop: 16 }}>
                      <Text type="secondary">
                        输入股票代码，开启 AI 五维深度诊断
                      </Text>
                    </div>
                    <div style={{ marginTop: 12 }}>
                      <Space>
                        <Tag icon={<ThunderboltOutlined />} color="blue">技术面</Tag>
                        <Tag icon={<DollarOutlined />} color="green">资金面</Tag>
                        <Tag icon={<BankOutlined />} color="gold">基本面</Tag>
                        <Tag icon={<RobotOutlined />} color="purple">AI预测</Tag>
                        <Tag icon={<SmileOutlined />} color="magenta">情绪面</Tag>
                      </Space>
                    </div>
                  </Card>
                )}
              </div>
            ),
          },
          {
            key: 'history',
            label: <span><HistoryOutlined /> 历史记录</span>,
            children: (
              <Card style={{ borderRadius: 8 }}>
                <Table
                  dataSource={history}
                  columns={historyColumns}
                  rowKey="id"
                  loading={historyLoading}
                  size="small"
                  pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
                  onRow={(record) => ({
                    onClick: () => handleHistoryRowClick(record),
                    style: { cursor: 'pointer' },
                  })}
                  expandable={{
                    expandedRowRender: (record) => (
                      <div style={{ padding: '12px 24px' }}>
                        {historyDetailLoading && expandedHistoryRow === record.id ? (
                          <Spin />
                        ) : historyDetail && expandedHistoryRow === record.id ? (
                          <Row gutter={[16, 16]}>
                            <Col span={12}>
                              <Card size="small" title="五维得分" style={{ borderRadius: 6 }}>
                                <div style={{ height: 240 }}>
                                  <ReactECharts
                                    option={buildRadarOption(historyDetail.dimensions)}
                                    style={{ height: '100%' }}
                                    opts={{ renderer: 'svg' }}
                                  />
                                </div>
                              </Card>
                            </Col>
                            <Col span={12}>
                              <Card size="small" title="基本面快照" style={{ borderRadius: 6 }}>
                                <Descriptions size="small" column={2}>
                                  <Descriptions.Item label="PE">{historyDetail.fundamentals.pe}</Descriptions.Item>
                                  <Descriptions.Item label="ROE">{historyDetail.fundamentals.roe}%</Descriptions.Item>
                                  <Descriptions.Item label="营收增速">{historyDetail.fundamentals.revenue_growth}%</Descriptions.Item>
                                  <Descriptions.Item label="利润增速">{historyDetail.fundamentals.profit_growth}%</Descriptions.Item>
                                  <Descriptions.Item label="市值(亿)">{historyDetail.fundamentals.market_cap}</Descriptions.Item>
                                  <Descriptions.Item label="新闻情感">{historyDetail.sentiment.news_score}/10</Descriptions.Item>
                                </Descriptions>
                              </Card>
                            </Col>
                          </Row>
                        ) : null}
                      </div>
                    ),
                    expandedRowKeys: expandedHistoryRow ? [expandedHistoryRow] : [],
                    showExpandColumn: false,
                  }}
                  locale={{ emptyText: <Empty description="暂无历史记录" /> }}
                />
              </Card>
            ),
          },
        ]}
      />

      {/* ── Compare Modal ── */}
      <Modal
        title={
          <span><SwapOutlined style={{ marginRight: 8 }} /> 多股对比</span>
        }
        open={compareOpen}
        onCancel={() => setCompareOpen(false)}
        width={900}
        footer={[
          <Button key="cancel" onClick={() => setCompareOpen(false)}>
            关闭
          </Button>,
          <Button key="compare" type="primary" loading={compareLoading} onClick={handleRunCompare}>
            开始对比
          </Button>,
        ]}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 13 }}>
            添加 2-5 只股票代码进行雷达图对比分析
          </Text>
        </div>

        <Space style={{ marginBottom: 16 }} wrap>
          {compareCodes.map(c => (
            <Tag
              key={c}
              closable={compareCodes.length > 1}
              onClose={() => handleRemoveCompareStock(c)}
              color="blue"
              style={{ fontSize: 13, padding: '2px 8px' }}
            >
              {c}
            </Tag>
          ))}
        </Space>

        <Row gutter={12} style={{ marginBottom: 16 }}>
          <Col flex="auto">
            <Input.Search
              placeholder="输入要对比的股票代码"
              enterButton="添加"
              onSearch={handleAddCompareStock}
              size="small"
              style={{ maxWidth: 300 }}
            />
          </Col>
        </Row>

        {compareResults.length > 0 && (
          <div style={{ height: 400 }}>
            <ReactECharts
              option={buildCompareRadarOption(
                compareResults.map(r => ({ name: `${r.code} ${r.name}`, dims: r.dimensions })),
              )}
              style={{ height: '100%' }}
              opts={{ renderer: 'svg' }}
            />
          </div>
        )}

        {compareResults.length > 0 && (
          <Table
            dataSource={compareResults}
            rowKey="code"
            size="small"
            style={{ marginTop: 16 }}
            pagination={false}
            columns={[
              { title: '代码', dataIndex: 'code', width: 90, render: (v: string) => <Text code>{v}</Text> },
              { title: '名称', dataIndex: 'name', width: 90 },
              {
                title: '评分', dataIndex: 'overall_score', width: 70,
                sorter: (a: DiagnosisResult, b: DiagnosisResult) => a.overall_score - b.overall_score,
                render: (v: number) => <Text strong style={{ fontSize: 15 }}>{v}</Text>,
              },
              {
                title: '等级', dataIndex: 'grade', width: 90,
                render: (_: string, r: DiagnosisResult) => renderGradeTag(r.grade, r.grade_label),
              },
              { title: '技术面', dataIndex: ['dimensions', 'technical'], width: 70 },
              { title: '资金面', dataIndex: ['dimensions', 'capital'], width: 70 },
              { title: '基本面', dataIndex: ['dimensions', 'fundamental'], width: 70 },
              { title: 'AI预测', dataIndex: ['dimensions', 'ai_prediction'], width: 70 },
              { title: '情绪面', dataIndex: ['dimensions', 'sentiment'], width: 70 },
              {
                title: '建议', dataIndex: ['suggestion', 'action'], width: 100,
                render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
              },
            ]}
          />
        )}
      </Modal>
    </div>
  )
}

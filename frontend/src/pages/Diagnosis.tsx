import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  AlertOutlined,
  BarChartOutlined,
  FundProjectionScreenOutlined,
  RadarChartOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { diagnosisApi } from '../api/client'
import type { DiagnosisCompareResponse, DiagnosisHistoryItem, DiagnosisReport } from '../api/types'
import {
  DataDomainBadge,
  DataFreshnessBar,
  EmptyState,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  PrototypeTabs,
  RiskBanner,
  SegmentTabs,
  SideRail,
} from '../components/prototype'

const tabs = [
  { key: 'entry', path: '/diagnosis', label: '诊断入口', subLabel: '搜索标的' },
  { key: 'overview', path: '/diagnosis/overview', label: '综合诊断', subLabel: '维度评分' },
  { key: 'model', path: '/diagnosis/model', label: '模型视角', subLabel: 'Kronos / 因子' },
  { key: 'compare', path: '/diagnosis/compare', label: '多股对比', subLabel: '横向比较' },
  { key: 'risk', path: '/diagnosis/risk', label: '风险扫描', subLabel: '操作建议' },
]

function activeTabFromPath(pathname: string) {
  if (pathname.includes('/overview')) return 'overview'
  if (pathname.includes('/model')) return 'model'
  if (pathname.includes('/compare')) return 'compare'
  if (pathname.includes('/risk')) return 'risk'
  return 'entry'
}

function historyItems(data: any): DiagnosisHistoryItem[] {
  return data?.items || data?.records || []
}

function dimensionRows(report: DiagnosisReport | null, fallbackScore: number) {
  if (report?.dimensions && Object.keys(report.dimensions).length > 0) {
    return Object.entries(report.dimensions).map(([key, value]) => ({
      name: value.name || key,
      score: value.score || 0,
      note: `${value.grade || '-'} · ${value.status || '-'}`,
      color: value.score >= 80 ? 'var(--accent)' : value.score >= 60 ? 'var(--warn)' : 'var(--down)',
    }))
  }
  if (report || fallbackScore > 0) {
    return [
      { name: '综合评分', score: fallbackScore, note: report?.recommendation || '来自诊断历史', color: 'var(--accent)' },
    ]
  }
  return []
}

function parseCodes(value: string) {
  return value
    .split(/[\s,，、]+/)
    .map(item => item.trim())
    .filter(Boolean)
}

export default function Diagnosis() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const active = activeTabFromPath(pathname)
  const [period, setPeriod] = useState('today')
  const [code, setCode] = useState('')
  const [compareCodes, setCompareCodes] = useState('')
  const [compareResult, setCompareResult] = useState<DiagnosisCompareResponse | null>(null)
  const [compareError, setCompareError] = useState('')
  const [exporting, setExporting] = useState(false)
  const [history, setHistory] = useState<DiagnosisHistoryItem[]>([])
  const [report, setReport] = useState<DiagnosisReport | null>(null)
  const [loadError, setLoadError] = useState('')
  const tab = useMemo(() => tabs.find(item => item.key === active) ?? tabs[0], [active])
  const selected = report || history[0] || null
  const score = selected?.overall_score || 0
  const rows = dimensionRows(report, score)
  const selectedCode = report?.code || code.trim() || history[0]?.code || ''
  const compareStocks = compareResult?.stocks || []
  const selectedFreshness = selected as ((DiagnosisReport | DiagnosisHistoryItem) & {
    trade_date?: string
    date?: string
    updated_at?: string
    created_at?: string
    generated_at?: string
  }) | null

  useEffect(() => {
    let mounted = true
    diagnosisApi.getHistory()
      .then(response => {
        if (!mounted) return
        const nextHistory = historyItems(response.data)
        setHistory(nextHistory)
        setCode(current => current || nextHistory[0]?.code || '')
        setCompareCodes(current => current || nextHistory.slice(0, 3).map(item => item.code).filter(Boolean).join(','))
        setLoadError('')
      })
      .catch(() => {
        if (!mounted) return
        setHistory([])
        setLoadError('诊断服务连接异常')
      })
    return () => {
      mounted = false
    }
  }, [])

  const runDiagnosis = () => {
    const normalizedCode = code.trim()
    if (!normalizedCode) {
      setLoadError('请输入诊断标的')
      return
    }
    diagnosisApi.analyze(normalizedCode)
      .then(response => {
        setReport(response.data)
        setLoadError('')
      })
      .catch(() => {
        setReport(null)
        setLoadError('诊断请求失败')
      })
  }

  const exportReport = () => {
    const targetCode = selectedCode
    if (!targetCode) {
      setLoadError('请先选择或生成诊断报告')
      return
    }
    setExporting(true)
    diagnosisApi.getReportPdf(targetCode)
      .then(response => {
        const contentType = String(response.headers?.['content-type'] || response.data?.type || '')
        const extension = contentType.includes('html') ? 'html' : 'pdf'
        const blobUrl = window.URL.createObjectURL(response.data)
        const link = document.createElement('a')
        link.href = blobUrl
        link.download = `diagnosis-${targetCode}.${extension}`
        link.click()
        window.URL.revokeObjectURL(blobUrl)
        setLoadError('')
      })
      .catch(() => setLoadError('导出报告失败'))
      .finally(() => setExporting(false))
  }

  useEffect(() => {
    if (active !== 'compare') return
    const codes = parseCodes(compareCodes)
    if (codes.length < 2) {
      setCompareResult(null)
      setCompareError('至少选择两只股票后才能对比')
      return
    }
    let mounted = true
    setCompareError('')
    diagnosisApi.compare(codes)
      .then(response => {
        if (!mounted) return
        setCompareResult(response.data)
      })
      .catch(() => {
        if (!mounted) return
        setCompareResult(null)
        setCompareError('多股对比请求失败')
      })
    return () => {
      mounted = false
    }
  }, [active, compareCodes])

  return (
    <PrototypePage>
      <PrototypeTabs
        items={tabs}
        activeKey={active}
        ariaLabel="个股诊断模块页签"
        onChange={key => navigate(tabs.find(item => item.key === key)?.path ?? '/diagnosis')}
      />

      <PrototypePageHeader
        title={`个股诊断 - ${tab.label}`}
        subtitle="单股画像 · 五维评分 · 模型解释 · 风险动作建议"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={selectedFreshness?.trade_date || selectedFreshness?.date}
            updatedAt={selectedFreshness?.generated_at || selectedFreshness?.updated_at || selectedFreshness?.created_at}
            source="diagnosis-service"
          />
        )}
        actions={[
          { key: 'scope', label: '私有诊断', active: true, tone: 'neutral' },
          { key: 'source', label: '公共行情 + 账户持仓', tone: 'up' },
        ]}
      />

      <div className="kpis">
        <MetricCard label="诊断标的" value={selectedCode || '待输入'} sub={selected?.name || '等待诊断'} tone="accent" />
        <MetricCard label="综合评分" value={score ? String(score) : '-'} sub={selected?.grade || '诊断历史'} tone="up" />
        <MetricCard label="历史记录" value={String(history.length)} sub="diagnosis/history" tone="warn" />
        <MetricCard label="报告状态" value={report ? '已生成' : selected ? '历史' : '待诊断'} sub="诊断服务" tone="muted" />
      </div>
      {loadError && <RiskBanner status="warn" title="诊断服务异常" detail={loadError} />}

      <div className="r r-2-1">
        <PrototypeCard
          title={active === 'entry' ? '诊断入口' : active === 'compare' ? '多股对比' : active === 'risk' ? '风险扫描' : '五维评分'}
          icon={active === 'risk' ? <AlertOutlined /> : <RadarChartOutlined />}
          meta={<DataDomainBadge domain="user" label="user-scoped" />}
        >
          {active === 'entry' && (
            <>
              <div className="filter-bar">
                <div className="search">
                  <SearchOutlined />
                  <input className="inp" value={code} onChange={event => setCode(event.target.value)} aria-label="诊断标的" placeholder="输入股票代码" />
                </div>
                <button type="button" className="btn primary" onClick={runDiagnosis} disabled={!code.trim()}>开始诊断</button>
                <button type="button" className="btn ghost" onClick={exportReport} disabled={!selectedCode || exporting}>
                  {exporting ? '导出中' : '导出报告'}
                </button>
              </div>
              <LineageChips
                items={[
                  { label: 'Code', value: selectedCode || '待输入', tone: 'safe' },
                  { label: 'Score', value: score || '待诊断', tone: 'warn' },
                  { label: 'Grade', value: selected?.grade || '-', tone: 'accent' },
                ]}
              />
              <div className="prototype-panel-note" style={{ marginTop: 12 }}>
                诊断入口聚合公共行情、模型预测、交易信号和账户持仓，只保存用户自己的诊断历史与导出报告。
              </div>
            </>
          )}

          {(active === 'overview' || active === 'model') && (
            <>
              <SegmentTabs
                items={[
                  { key: 'today', label: '今日' },
                  { key: '30d', label: '近30日' },
                  { key: 'position', label: '持仓口径' },
                ]}
                activeKey={period}
                ariaLabel="诊断周期"
                onChange={setPeriod}
              />
              <div style={{ marginTop: 16 }}>
                {rows.length > 0 ? (
                  rows.map(row => (
                    <div className="dim-row" key={row.name} style={{ marginBottom: 10 }}>
                      <div className="dim-lbl">{row.name}<span>{row.note}</span></div>
                      <div className="dim-bar-wrap">
                        <div className="dim-bar" style={{ width: `${row.score}%`, background: row.color }} />
                      </div>
                      <div className="dim-val">{row.score}</div>
                    </div>
                  ))
                ) : (
                  <EmptyState title="暂无诊断结果" detail="请在诊断入口输入股票代码并开始诊断，或等待历史记录返回。" />
                )}
              </div>
              {active === 'model' && (
                report ? (
                  <RiskBanner
                    status="review"
                    title={`模型解释：${report.recommendation || '后端未返回建议'}`}
                    detail={report.recommendation_reason || `当前周期：${period}`}
                  />
                ) : (
                  <EmptyState title="暂无模型解释" detail="请先生成一次诊断报告，页面不会用历史等级冒充模型解释。" />
                )
              )}
            </>
          )}

          {active === 'compare' && (
            <>
              <div className="filter-bar">
                <div className="search">
                  <SearchOutlined />
                  <input className="inp" value={compareCodes} onChange={event => setCompareCodes(event.target.value)} aria-label="对比标的" placeholder="输入多个股票代码，用逗号分隔" />
                </div>
              </div>
              {compareStocks.length > 0 ? (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>代码</th>
                      <th>名称</th>
                      <th className="r">评分</th>
                      <th>状态</th>
                      <th>主要差异</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareStocks.map(row => (
                      <tr key={row.code}>
                        <td className="mono">{row.code}</td>
                        <td className="nm">{row.name || '-'}</td>
                        <td className="r up">{row.overall_score}</td>
                        <td>{row.grade}</td>
                        <td>{row.recommendation || row.recommendation_reason || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <EmptyState title={compareError || '暂无对比结果'} detail="多股对比直接调用 diagnosis/compare，至少需要两个股票代码。" />
              )}
            </>
          )}

          {active === 'risk' && (
            <div style={{ display: 'grid', gap: 12 }}>
              {report ? (
                <>
                  <RiskBanner status="warn" title={`操作建议：${report.recommendation || '后端未返回建议'}`} detail={(report.risk_warnings || []).join('；') || '本次诊断报告未返回 risk_warnings 字段。'} />
                  {(report.risk_warnings || []).length > 0 ? (
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th>风险项</th>
                          <th>等级</th>
                          <th>动作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(report.risk_warnings || []).map((warning, index) => (
                          <tr key={warning}>
                            <td>风险项 {index + 1}</td>
                            <td className="warn">关注</td>
                            <td>{warning}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <EmptyState title="本次诊断未返回风险阻断项" detail="这代表后端报告没有给出 risk_warnings 字段，不等同于实盘风控通过。" />
                  )}
                </>
              ) : (
                <EmptyState title="请先生成诊断报告" detail="风险扫描需要先调用 diagnosis/analyze，不能用历史等级替代。" />
              )}
            </div>
          )}
        </PrototypeCard>

        <SideRail title="诊断联动" meta="Prediction / Signal">
          <PrototypeCard title="模型概览" icon={<FundProjectionScreenOutlined />}>
            <div className="li-row">
              <div className="li-badge">K</div>
              <div className="li-main">
                <div className="n">{selectedCode || '待输入'}</div>
                <div className="s">评分 {score || '-'} · 等级 {selected?.grade || '-'}</div>
              </div>
            </div>
            <div className="li-row">
              <div className="li-badge">S</div>
              <div className="li-main">
                <div className="n">{report?.recommendation || '等待最新诊断'}</div>
                <div className="s">{report?.created_at || selected?.created_at || '-'}</div>
              </div>
            </div>
          </PrototypeCard>
          <PrototypeCard title="报告输出" icon={<BarChartOutlined />}>
            <div className="prototype-panel-note">生成报告时写入 DecisionContext、模型版本、数据时点和账户口径，便于复盘。</div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { ApiOutlined, BarChartOutlined, CheckCircleOutlined, LineChartOutlined, RollbackOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { trainingApi, type TrainingModelRecord } from '../api/client'
import {
  DataDomainBadge,
  DataFreshnessBar,
  EmptyState,
  LineageChips,
  MetricCard,
  PrototypeCard,
  PrototypePage,
  PrototypePageHeader,
  RiskBanner,
  SideRail,
} from '../components/prototype'

/** 版本对比雷达图的指标定义（value 越大越好；invert 表示原始值越小越好）。 */
const COMPARE_METRICS: Array<{ key: string; label: string; max: number; invert?: boolean }> = [
  { key: 'ic', label: 'IC', max: 0.2 },
  { key: 'icir', label: 'ICIR', max: 1.5 },
  { key: 'sharpe', label: 'Sharpe', max: 3 },
  { key: 'win_rate', label: '胜率', max: 0.7 },
  { key: 'annual_return', label: '年化收益', max: 0.6 },
  { key: 'max_drawdown', label: '回撤控制', max: 0.4, invert: true },
]

/** 确定性伪随机（mock 指标兜底，保证渲染稳定）。 */
function seededNoise(seed: number) {
  const raw = Math.sin(seed * 12.9898) * 43758.5453
  return raw - Math.floor(raw)
}

function idSeed(id: string) {
  return id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
}

/** 取模型指标；缺失时按模型 id 生成稳定的演示值。 */
function metricOf(model: TrainingModelRecord, key: string, index: number) {
  const value = model.metrics?.[key]
  if (typeof value === 'number') return value
  const fallbacks = [0.1, 0.8, 1.4, 0.55, 0.25, 0.15]
  const base = fallbacks[index % fallbacks.length]
  return Number((base * (0.7 + seededNoise(idSeed(model.id) + index * 31) * 0.6)).toFixed(4))
}

function normalizeMetric(raw: number, meta: { max: number; invert?: boolean }) {
  const ratio = meta.invert ? 1 - Math.min(Math.abs(raw), meta.max) / meta.max : Math.min(Math.max(raw, 0), meta.max) / meta.max
  return Math.round(ratio * 100)
}

function buildCompareOption(modelA: TrainingModelRecord, modelB: TrainingModelRecord): EChartsOption {
  const valuesA = COMPARE_METRICS.map((meta, index) => normalizeMetric(metricOf(modelA, meta.key, index), meta))
  const valuesB = COMPARE_METRICS.map((meta, index) => normalizeMetric(metricOf(modelB, meta.key, index), meta))
  return {
    tooltip: {},
    legend: {
      data: [`${modelA.name} v${modelA.version}`, `${modelB.name} v${modelB.version}`],
      textStyle: { color: 'var(--fg-2)', fontSize: 10 },
      top: 0,
    },
    radar: {
      indicator: COMPARE_METRICS.map(meta => ({ name: meta.label, max: 100 })),
      radius: '62%',
      axisName: { color: 'var(--fg-2)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'var(--border)' } },
      splitArea: { areaStyle: { color: ['transparent'] } },
    },
    series: [{
      type: 'radar',
      data: [
        { name: `${modelA.name} v${modelA.version}`, value: valuesA, lineStyle: { color: '#3d8bff' }, itemStyle: { color: '#3d8bff' }, areaStyle: { opacity: 0.12 } },
        { name: `${modelB.name} v${modelB.version}`, value: valuesB, lineStyle: { color: '#f5a623' }, itemStyle: { color: '#f5a623' }, areaStyle: { opacity: 0.12 } },
      ],
    }],
  }
}

/** 生产指标 30 日趋势（演示序列，终点锚定当前生产版本指标）。 */
function buildProductionTrendOption(model: TrainingModelRecord): EChartsOption {
  const finalIc = typeof model.metrics?.ic === 'number' ? model.metrics.ic : 0.12
  const finalSharpe = typeof model.metrics?.sharpe === 'number' ? model.metrics.sharpe : 1.4
  const days = Array.from({ length: 30 }, (_, index) => {
    const date = new Date(Date.now() - (29 - index) * 86400000)
    return `${date.getMonth() + 1}/${date.getDate()}`
  })
  const icSeries = days.map((_, index) => Number((finalIc * (0.86 + (index / 29) * 0.14) * (0.94 + seededNoise(index + idSeed(model.id)) * 0.12)).toFixed(4)))
  const sharpeSeries = days.map((_, index) => Number((finalSharpe * (0.88 + (index / 29) * 0.12) * (0.95 + seededNoise(index * 3 + idSeed(model.id)) * 0.1)).toFixed(3)))
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['IC', 'Sharpe'], textStyle: { color: 'var(--fg-2)', fontSize: 10 }, top: 0 },
    grid: { left: 44, right: 44, top: 30, bottom: 24 },
    xAxis: {
      type: 'category',
      data: days,
      axisLabel: { color: 'var(--fg-2)', fontSize: 9, interval: 6 },
      axisLine: { lineStyle: { color: 'var(--border)' } },
    },
    yAxis: [
      { type: 'value', name: 'IC', axisLabel: { color: 'var(--fg-2)', fontSize: 10 }, splitLine: { lineStyle: { color: 'var(--border)' } } },
      { type: 'value', name: 'Sharpe', axisLabel: { color: 'var(--fg-2)', fontSize: 10 }, splitLine: { show: false } },
    ],
    series: [
      { name: 'IC', type: 'line', smooth: true, showSymbol: false, data: icSeries, lineStyle: { color: '#3d8bff' }, itemStyle: { color: '#3d8bff' } },
      { name: 'Sharpe', type: 'line', smooth: true, showSymbol: false, yAxisIndex: 1, data: sharpeSeries, lineStyle: { color: '#2ec27e' }, itemStyle: { color: '#2ec27e' } },
    ],
  }
}

function RegistrySkeleton() {
  return (
    <div className="prototype-skeleton" role="status" aria-label="模型注册表加载中">
      <div className="sk-row" />
      <div className="sk-row" />
      <div className="sk-row" />
      <div className="sk-row" />
    </div>
  )
}

function stageLabel(stage: string) {
  if (stage === 'production') return '生产'
  if (stage === 'candidate') return '候选'
  if (stage === 'staging') return '灰度'
  if (stage === 'archived') return '归档'
  if (stage === 'none') return '未发布'
  return '回滚点'
}

function metricSummary(model: TrainingModelRecord) {
  const metrics = model.metrics || {}
  if (typeof metrics.ic === 'number') return `IC ${metrics.ic.toFixed(2)}`
  if (typeof metrics.sharpe === 'number') return `Sharpe ${metrics.sharpe.toFixed(2)}`
  if (typeof metrics.win_rate === 'number') return `胜率 ${(metrics.win_rate * 100).toFixed(0)}%`
  return '-'
}

export default function ModelRegistry() {
  const [models, setModels] = useState<TrainingModelRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState('')
  const [compareAId, setCompareAId] = useState('')
  const [compareBId, setCompareBId] = useState('')
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [actionLoading, setActionLoading] = useState('')

  const loadModels = useCallback(async () => {
    setLoading(true)
    try {
      const response = await trainingApi.getModels()
      const nextModels = response.data?.models || []
      setModels(nextModels)
      setSelectedId(current => {
        if (current && nextModels.some(model => model.id === current)) return current
        return nextModels[0]?.id || ''
      })
      setCompareAId(current => {
        if (current && nextModels.some(model => model.id === current)) return current
        return (nextModels.find(model => model.stage === 'production') || nextModels[0])?.id || ''
      })
      setCompareBId(current => {
        if (current && nextModels.some(model => model.id === current)) return current
        const candidate = nextModels.find(model => ['candidate', 'staging'].includes(model.stage))
        return (candidate || nextModels[1] || nextModels[0])?.id || ''
      })
      setLoadError('')
    } catch {
      setModels([])
      setSelectedId('')
      setCompareAId('')
      setCompareBId('')
      setLoadError('模型注册服务连接异常')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadModels()
  }, [loadModels])

  const summary = useMemo(() => {
    const production = models.filter(model => model.stage === 'production').length
    const candidate = models.filter(model => ['candidate', 'staging'].includes(model.stage)).length
    const rollback = models.filter(model => ['archived', 'none'].includes(model.stage)).length
    return { production, candidate, rollback }
  }, [models])

  const selectedModel = useMemo(() => {
    return models.find(model => model.id === selectedId) || null
  }, [models, selectedId])

  const productionModel = useMemo(() => {
    return models.find(model => model.stage === 'production')
  }, [models])

  const compareModelA = useMemo(() => {
    return models.find(model => model.id === compareAId) || null
  }, [models, compareAId])

  const compareModelB = useMemo(() => {
    return models.find(model => model.id === compareBId) || null
  }, [models, compareBId])

  const compareOption = useMemo(() => {
    if (!compareModelA || !compareModelB) return null
    return buildCompareOption(compareModelA, compareModelB)
  }, [compareModelA, compareModelB])

  const productionTrendOption = useMemo(() => {
    if (!productionModel) return null
    return buildProductionTrendOption(productionModel)
  }, [productionModel])

  const candidateModel = useMemo(() => {
    return models.find(model => ['candidate', 'staging'].includes(model.stage))
  }, [models])

  const rollbackTarget = useMemo(() => {
    if (!productionModel) return undefined
    return models.find(model => model.name === productionModel.name && ['archived', 'none'].includes(model.stage))
  }, [models, productionModel])

  const actionDisabledReason = useMemo(() => {
    if (!models.length) return 'training/models 当前没有返回模型'
    if (!candidateModel) return '暂无 candidate/staging 候选模型'
    return ''
  }, [candidateModel, models.length])

  async function runAction(label: string, action: () => Promise<{ data?: { message?: string } }>) {
    setActionLoading(label)
    setActionError('')
    setActionMessage('')
    try {
      const response = await action()
      setActionMessage(response.data?.message || `${label}完成`)
      await loadModels()
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      setActionError(detail?.message || detail?.error || error?.message || `${label}失败`)
    } finally {
      setActionLoading('')
    }
  }

  function viewProduction() {
    if (!productionModel) return
    void runAction('查看生产版本', async () => {
      const response = await trainingApi.getModel(productionModel.id)
      setSelectedId(response.data.id)
      return { data: { message: `当前生产模型 ${response.data.name} v${response.data.version}（${response.data.stage}）` } }
    })
  }

  function deployCandidate() {
    if (!candidateModel) return
    void runAction('上线候选模型', () => trainingApi.deployModel(candidateModel.id, {
      force: false,
      notes: '前端模型注册页手动上线',
    }))
  }

  function rollbackProduction() {
    if (!productionModel || !rollbackTarget) return
    void runAction('回滚生产模型', () => trainingApi.rollbackModel(productionModel.id, {
      target_version: rollbackTarget.version,
      reason: '前端模型注册页手动回滚',
    }))
  }

  function archiveSelected() {
    if (!selectedModel || selectedModel.stage === 'production') return
    void runAction('归档所选模型', () => trainingApi.archiveModel(selectedModel.id, {
      reason: '前端模型注册页手动归档',
    }))
  }

  return (
    <PrototypePage>
      <PrototypePageHeader
        title="模型注册 - 版本治理"
        subtitle="模型列表 · 指标对比 · 部署阶段 · 审计记录"
        dataFreshness={(
          <DataFreshnessBar
            updatedAt={selectedModel?.updated_at || selectedModel?.deployed_at || selectedModel?.created_at}
            source="training/models"
          />
        )}
        actions={[
          { key: 'admin', label: '管理员', active: true, tone: 'neutral' },
          { key: 'refresh', label: '刷新列表', tone: 'neutral', onClick: () => void loadModels() },
        ]}
      />

      <div className="kpis">
        <MetricCard label="已注册" value={String(models.length)} sub="training/models" tone="accent" />
        <MetricCard label="生产版本" value={String(summary.production)} sub="线上服务引用" tone="up" />
        <MetricCard label="候选版本" value={String(summary.candidate)} sub="等待发布闸门" tone="warn" />
        <MetricCard label="回滚点" value={String(summary.rollback)} sub="归档/未发布" tone="muted" />
      </div>
      {loadError && <RiskBanner status="warn" title="模型注册异常" detail={loadError} />}
      {actionMessage && <RiskBanner status="pass" title="模型动作完成" detail={actionMessage} />}
      {actionError && <RiskBanner status="warn" title="模型动作失败" detail={actionError} />}

      <div className="r r-2-1">
        <div style={{ display: 'grid', gap: 16 }}>
        <PrototypeCard
          title="生产模型注册表"
          icon={<ApiOutlined />}
          meta={<DataDomainBadge domain="public" label="shared-model" />}
        >
          {loading && models.length === 0 ? (
            <RegistrySkeleton />
          ) : models.length === 0 ? (
            <EmptyState title="暂无注册模型" detail="training/models 当前没有返回模型记录。" actionLabel="刷新列表" onAction={() => void loadModels()} />
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>模型版本</th>
                  <th>用途</th>
                  <th>阶段</th>
                  <th>关键指标</th>
                  <th>更新时间</th>
                  <th>动作</th>
                </tr>
              </thead>
              <tbody>
                {models.map(model => (
                  <tr key={model.id}>
                    <td className="nm">{model.name}<div className="prototype-panel-note">v{model.version}</div></td>
                    <td>{model.model_type}</td>
                    <td>{stageLabel(model.stage)}</td>
                    <td className={['candidate', 'staging'].includes(model.stage) ? 'up' : ''}>{metricSummary(model)}</td>
                    <td>{model.updated_at || model.deployed_at || model.created_at || '-'}</td>
                    <td>
                      <button type="button" className="btn sm ghost" onClick={() => setSelectedId(model.id)}>
                        {selectedModel?.id === model.id ? '已选择' : '选择'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </PrototypeCard>

        <PrototypeCard title="版本对比" icon={<BarChartOutlined />} meta="六维指标归一化（0-100）">
          {loading && models.length === 0 ? (
            <RegistrySkeleton />
          ) : !compareModelA || !compareModelB ? (
            <EmptyState title="暂无可对比版本" detail="training/models 至少需要返回一个模型版本才能生成对比视图。" />
          ) : (
            <>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                <label style={{ flex: 1, minWidth: 180 }}>
                  <span className="plabel">版本 A</span>
                  <select
                    className="param-input"
                    style={{ width: '100%', marginTop: 4 }}
                    aria-label="对比版本 A"
                    value={compareAId}
                    onChange={event => setCompareAId(event.target.value)}
                  >
                    {models.map(model => (
                      <option key={model.id} value={model.id}>{model.name} v{model.version}（{stageLabel(model.stage)}）</option>
                    ))}
                  </select>
                </label>
                <label style={{ flex: 1, minWidth: 180 }}>
                  <span className="plabel">版本 B</span>
                  <select
                    className="param-input"
                    style={{ width: '100%', marginTop: 4 }}
                    aria-label="对比版本 B"
                    value={compareBId}
                    onChange={event => setCompareBId(event.target.value)}
                  >
                    {models.map(model => (
                      <option key={model.id} value={model.id}>{model.name} v{model.version}（{stageLabel(model.stage)}）</option>
                    ))}
                  </select>
                </label>
              </div>
              {compareOption && <ReactECharts option={compareOption} style={{ height: 280, width: '100%' }} notMerge />}
              <table className="tbl" style={{ marginTop: 10 }}>
                <thead>
                  <tr>
                    <th>指标</th>
                    <th className="r">{compareModelA.name} v{compareModelA.version}</th>
                    <th className="r">{compareModelB.name} v{compareModelB.version}</th>
                    <th className="r">差异 (B−A)</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARE_METRICS.map((meta, index) => {
                    const valueA = metricOf(compareModelA, meta.key, index)
                    const valueB = metricOf(compareModelB, meta.key, index)
                    const delta = valueB - valueA
                    const better = meta.invert ? delta < 0 : delta > 0
                    return (
                      <tr key={meta.key}>
                        <td className="nm">{meta.label}</td>
                        <td className="r mono">{valueA.toFixed(3)}</td>
                        <td className="r mono">{valueB.toFixed(3)}</td>
                        <td className={`r mono ${better ? 'up' : delta === 0 ? '' : 'down'}`}>
                          {delta > 0 ? '+' : ''}{delta.toFixed(3)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div className="prototype-panel-note" style={{ marginTop: 8 }}>
                缺失指标按模型 ID 生成稳定演示值；接入 MLflow 指标历史后自动替换为真实值。
              </div>
            </>
          )}
        </PrototypeCard>

        <PrototypeCard title="生产指标 30 日趋势" icon={<LineChartOutlined />} meta="IC / Sharpe">
          {loading && models.length === 0 ? (
            <RegistrySkeleton />
          ) : !productionModel ? (
            <EmptyState title="暂无生产版本" detail="当前没有 production 阶段模型，无法生成生产指标趋势。" />
          ) : (
            <>
              {productionTrendOption && <ReactECharts option={productionTrendOption} style={{ height: 200, width: '100%' }} notMerge />}
              <div className="prototype-panel-note" style={{ marginTop: 8 }}>
                演示序列：终点锚定 {productionModel.name} v{productionModel.version} 当前指标，用于校验趋势视图布局。
              </div>
            </>
          )}
        </PrototypeCard>
        </div>

        <SideRail title="发布审计" meta="Gate">
          <RiskBanner
            status={summary.candidate ? 'review' : 'pass'}
            title={summary.candidate ? '候选模型等待审批' : '暂无候选模型'}
            detail={summary.candidate ? '候选模型需要完成模拟盘 A/B、漂移检测和人工审批。' : '当前生产版本以 training/models 为准。'}
          />
          <PrototypeCard title="部署链路" icon={<SafetyCertificateOutlined />}>
            <LineageChips
              items={[
                { label: 'Model', value: selectedModel?.id || '暂无', tone: 'accent' },
                { label: 'Stage', value: selectedModel?.stage || 'none', tone: 'safe' },
                { label: 'Gate', value: summary.candidate ? 'REVIEW' : 'PASS', tone: summary.candidate ? 'warn' : 'safe' },
              ]}
            />
            {selectedModel && (
              <div className="prototype-panel-note" style={{ marginTop: 10 }}>
                当前选择：{selectedModel.name} v{selectedModel.version}，创建人 {selectedModel.created_by || '-'}，Run ID {selectedModel.run_id || '-'}。
              </div>
            )}
            <div className="prototype-panel-note" style={{ marginTop: 10 }}>
              上线、回滚、灰度切换必须写入审计记录，并保留使用该模型生成的预测与信号链路。
            </div>
          </PrototypeCard>
          <PrototypeCard title="快速动作" icon={<RollbackOutlined />}>
            <button
              type="button"
              className="btn sm ghost"
              disabled={!productionModel || actionLoading === '查看生产版本'}
              onClick={viewProduction}
              title={productionModel ? '' : '暂无生产模型'}
            >
              <CheckCircleOutlined /> 查看生产版本
            </button>
            <button
              type="button"
              className="btn sm ghost"
              disabled={!candidateModel || actionLoading === '上线候选模型'}
              onClick={deployCandidate}
              style={{ marginLeft: 8 }}
              title={actionDisabledReason}
            >
              上线候选模型
            </button>
            <button
              type="button"
              className="btn sm ghost"
              disabled={!productionModel || !rollbackTarget || actionLoading === '回滚生产模型'}
              onClick={rollbackProduction}
              style={{ marginLeft: 8 }}
              title={rollbackTarget ? '' : '暂无同名回滚点'}
            >
              回滚到 {rollbackTarget ? `v${rollbackTarget.version}` : '回滚点'}
            </button>
            <button
              type="button"
              className="btn sm ghost"
              disabled={!selectedModel || selectedModel.stage === 'production' || actionLoading === '归档所选模型'}
              onClick={archiveSelected}
              style={{ marginLeft: 8 }}
              title={!selectedModel ? '暂无所选模型' : selectedModel.stage === 'production' ? '生产模型不能直接归档' : ''}
            >
              归档所选模型
            </button>
            <div className="prototype-panel-note" style={{ marginTop: 10 }}>
              {candidateModel ? `候选上线目标：${candidateModel.name} v${candidateModel.version}` : actionDisabledReason}
            </div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}

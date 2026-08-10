import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Modal } from 'antd'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { CheckCircleOutlined, ClockCircleOutlined, ExperimentOutlined, LineChartOutlined, PlayCircleOutlined } from '@ant-design/icons'
import {
  trainingApi,
  type TrainingHistoryRecord,
  type TrainingModelRecord,
  type TrainingRunParams,
  type TrainingScheduleResponse,
} from '../api/client'
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
  { key: 'overview', path: '/training', label: '训练总览', subLabel: '任务状态' },
  { key: 'tasks', path: '/training/tasks', label: '训练任务', subLabel: '队列 / 参数' },
  { key: 'mlflow', path: '/training/mlflow', label: 'MLflow 实验', subLabel: '指标追踪' },
]

function activeTabFromPath(pathname: string) {
  if (pathname.includes('/tasks')) return 'tasks'
  if (pathname.includes('/mlflow')) return 'mlflow'
  return 'overview'
}

function statusIcon(status: string) {
  if (['completed', 'success', '已完成'].includes(status)) return <CheckCircleOutlined className="down" />
  return <ClockCircleOutlined style={{ color: ['failed', 'cancelled'].includes(status) ? 'var(--warn)' : 'var(--accent)' }} />
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '排队中',
    preparing: '准备中',
    running: '运行中',
    evaluating: '评估中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return labels[status] || status
}

function datasetLabel(params?: Record<string, unknown> | null) {
  if (!params) return '-'
  const dataset = params.dataset || params.data_source || params.train_table || params.mode
  return dataset ? String(dataset) : Object.keys(params).slice(0, 2).join(' / ') || '-'
}

function metricValue(models: TrainingModelRecord[], jobs: TrainingHistoryRecord[], key: string) {
  const values = [
    ...models.map(model => model.metrics?.[key]),
    ...jobs.map(job => job.final_metrics?.[key]),
  ].filter((value): value is number => typeof value === 'number')
  if (!values.length) return 0
  return Math.max(...values)
}

const MODEL_TYPE_OPTIONS = [
  { value: 'lightgbm', label: 'LightGBM 排序' },
  { value: 'catboost', label: 'CatBoost 排序' },
  { value: 'kronos_finetune', label: 'Kronos 微调' },
  { value: 'screener', label: '选股因子' },
]

const MLFLOW_TRIALS = 40

/** 确定性伪随机（保证测试与渲染稳定）。 */
function seededNoise(index: number, salt: number) {
  const raw = Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453
  return raw - Math.floor(raw)
}

/** 演示用 MLflow 训练曲线：收敛形态 + 以真实最优指标锚定终点。 */
function buildMlflowOptions(models: TrainingModelRecord[]): { lossOption: EChartsOption; icOption: EChartsOption } {
  const bestIc = metricValue(models, [], 'ic') || 0.11
  const trials = Array.from({ length: MLFLOW_TRIALS }, (_, index) => index + 1)
  const trainLoss = trials.map(trial => Number((0.92 * Math.exp(-trial / 14) + 0.06 + seededNoise(trial, 1) * 0.03).toFixed(4)))
  const validLoss = trials.map(trial => Number((0.98 * Math.exp(-trial / 12) + 0.09 + seededNoise(trial, 2) * 0.04).toFixed(4)))
  const trainIc = trials.map(trial => Number((bestIc * (1 - Math.exp(-trial / 10)) * (0.94 + seededNoise(trial, 3) * 0.06)).toFixed(4)))
  const validIc = trials.map((trial, index) => Number((bestIc * (1 - Math.exp(-trial / 12)) * (0.9 + seededNoise(trial, 4) * 0.08) + (index === MLFLOW_TRIALS - 1 ? bestIc * 0.02 : 0)).toFixed(4)))

  const baseGrid = { left: 48, right: 16, top: 32, bottom: 28 }
  const baseTooltip = { trigger: 'axis' as const }
  const axisStyle = {
    axisLabel: { color: 'var(--fg-2)', fontSize: 10 },
    axisLine: { lineStyle: { color: 'var(--border)' } },
    splitLine: { lineStyle: { color: 'var(--border)' } },
  }

  const lossOption: EChartsOption = {
    tooltip: baseTooltip,
    legend: { data: ['train_loss', 'valid_loss'], textStyle: { color: 'var(--fg-2)', fontSize: 10 }, top: 0 },
    grid: baseGrid,
    xAxis: { type: 'category', name: 'trial', data: trials.map(String), ...axisStyle },
    yAxis: { type: 'value', name: 'loss', ...axisStyle },
    series: [
      { name: 'train_loss', type: 'line', smooth: true, showSymbol: false, data: trainLoss, lineStyle: { color: '#3d8bff' }, itemStyle: { color: '#3d8bff' } },
      { name: 'valid_loss', type: 'line', smooth: true, showSymbol: false, data: validLoss, lineStyle: { color: '#f5a623' }, itemStyle: { color: '#f5a623' } },
    ],
  }

  const icOption: EChartsOption = {
    tooltip: baseTooltip,
    legend: { data: ['train_ic', 'valid_ic'], textStyle: { color: 'var(--fg-2)', fontSize: 10 }, top: 0 },
    grid: baseGrid,
    xAxis: { type: 'category', name: 'trial', data: trials.map(String), ...axisStyle },
    yAxis: { type: 'value', name: 'IC', ...axisStyle },
    series: [
      { name: 'train_ic', type: 'line', smooth: true, showSymbol: false, data: trainIc, lineStyle: { color: '#2ec27e' }, itemStyle: { color: '#2ec27e' } },
      { name: 'valid_ic', type: 'line', smooth: true, showSymbol: false, data: validIc, lineStyle: { color: '#3d8bff' }, itemStyle: { color: '#3d8bff' } },
    ],
  }

  return { lossOption, icOption }
}

function formatDuration(seconds?: number | null) {
  if (typeof seconds !== 'number' || seconds <= 0) return ''
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes <= 0) return `${rest}s`
  return `${minutes}m ${rest}s`
}

export default function Training() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const active = activeTabFromPath(pathname)
  const tab = useMemo(() => tabs.find(item => item.key === active) ?? tabs[0], [active])
  const [queue, setQueue] = useState('running')
  const [jobs, setJobs] = useState<TrainingHistoryRecord[]>([])
  const [models, setModels] = useState<TrainingModelRecord[]>([])
  const [schedule, setSchedule] = useState<TrainingScheduleResponse | null>(null)
  const [loadError, setLoadError] = useState('')
  const [runModalOpen, setRunModalOpen] = useState(false)
  const [runSubmitting, setRunSubmitting] = useState(false)
  const [runMessage, setRunMessage] = useState('')
  const [runError, setRunError] = useState('')
  const [runForm, setRunForm] = useState<TrainingRunParams>({
    model_type: 'lightgbm',
    horizon: 15,
    lookback: 180,
    n_trials: 50,
    cv_folds: 5,
    learning_rate: null,
    max_depth: null,
    num_leaves: null,
    data_start_date: null,
    data_end_date: null,
  })
  const [autoDeploy, setAutoDeploy] = useState(false)

  const loadData = useCallback(() => {
    Promise.allSettled([
      trainingApi.getHistory(),
      trainingApi.getModels(),
      trainingApi.getSchedule(),
    ]).then(([historyResponse, modelsResponse, scheduleResponse]) => {
        if (historyResponse.status === 'fulfilled') setJobs(historyResponse.value.data?.jobs || [])
        if (modelsResponse.status === 'fulfilled') setModels(modelsResponse.value.data?.models || [])
        if (scheduleResponse.status === 'fulfilled') setSchedule(scheduleResponse.value.data || null)
        const failed = [historyResponse, modelsResponse, scheduleResponse].filter(result => result.status === 'rejected').length
        setLoadError(failed > 0 ? `${failed} 个训练数据接口连接异常` : '')
      })
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  function updateRunForm(patch: Partial<TrainingRunParams>) {
    setRunForm(current => ({ ...current, ...patch }))
  }

  async function submitTraining() {
    setRunSubmitting(true)
    setRunError('')
    setRunMessage('')
    try {
      const response = await trainingApi.runTraining({
        params: {
          ...runForm,
          data_start_date: runForm.data_start_date || null,
          data_end_date: runForm.data_end_date || null,
        },
        auto_deploy: autoDeploy,
      })
      setRunMessage(`训练任务已发起：${response.data?.job_id || '已入队'}（${response.data?.status || 'pending'}）`)
      setRunModalOpen(false)
      loadData()
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      setRunError(detail?.message || detail?.error || error?.message || '发起训练失败')
    } finally {
      setRunSubmitting(false)
    }
  }

  const runningJobs = jobs.filter(job => ['pending', 'preparing', 'running', 'evaluating'].includes(job.status))
  const releaseModels = models.filter(model => ['candidate', 'staging'].includes(model.stage))
  const failedJobs = jobs.filter(job => ['failed', 'cancelled'].includes(job.status))
  const historyJobs = jobs.filter(job => ['completed', 'failed', 'cancelled'].includes(job.status))
  const visibleJobs = queue === 'running' ? runningJobs : queue === 'release' ? historyJobs : jobs
  const bestIc = metricValue(models, jobs, 'ic')
  const { lossOption, icOption } = useMemo(() => buildMlflowOptions(models), [models])
  const latestJob = jobs[0] as (TrainingHistoryRecord & { updated_at?: string; created_at?: string; started_at?: string; finished_at?: string; trade_date?: string }) | undefined
  const latestModel = models[0] as (TrainingModelRecord & { updated_at?: string; created_at?: string; trade_date?: string }) | undefined

  return (
    <PrototypePage>
      <PrototypeTabs
        items={tabs}
        activeKey={active}
        ariaLabel="模型训练模块页签"
        onChange={key => navigate(tabs.find(item => item.key === key)?.path ?? '/training')}
      />

      <PrototypePageHeader
        title={`模型训练 - ${tab.label}`}
        subtitle="任务队列 · 数据校验 · 实验追踪 · 发布闸门"
        dataFreshness={(
          <DataFreshnessBar
            tradeDate={latestJob?.trade_date || latestModel?.trade_date}
            updatedAt={latestJob?.updated_at || latestJob?.finished_at || latestJob?.started_at || latestJob?.created_at || latestModel?.updated_at || latestModel?.created_at || schedule?.next_run}
            source="training-service"
          />
        )}
        actions={[
          { key: 'run', label: (<><PlayCircleOutlined /> 发起训练</>), tone: 'up', onClick: () => setRunModalOpen(true) },
          { key: 'admin', label: '管理员', active: true, tone: 'neutral' },
          { key: 'gate', label: '上线需复核', tone: 'warn' },
        ]}
      />

      <div className="kpis">
        <MetricCard label="运行任务" value={String(runningJobs.length)} sub="training/history" tone="accent" />
        <MetricCard label="待发布" value={String(releaseModels.length)} sub="模型闸门复核" tone="warn" />
        <MetricCard label="最佳 IC" value={bestIc ? bestIc.toFixed(2) : '-'} sub="模型注册指标" tone="up" />
        <MetricCard label="失败任务" value={String(failedJobs.length)} sub="历史任务" tone="muted" />
      </div>
      {loadError && <RiskBanner status="warn" title="训练服务异常" detail={loadError} />}
      {runMessage && <RiskBanner status="pass" title="训练已入队" detail={runMessage} />}
      {runError && <RiskBanner status="warn" title="发起训练失败" detail={runError} />}

      <div className="r r-2-1">
        <PrototypeCard
          title={active === 'mlflow' ? 'MLflow 实验追踪' : '训练任务队列'}
          icon={<ExperimentOutlined />}
          meta={<DataDomainBadge domain="public" label="model-admin" />}
        >
          {active !== 'mlflow' && (
            <>
              <SegmentTabs
                items={[
                  { key: 'running', label: '运行中', count: runningJobs.length },
                  { key: 'release', label: '历史', count: historyJobs.length },
                  { key: 'history', label: '全部', count: jobs.length },
                ]}
                activeKey={queue}
                ariaLabel="训练任务队列筛选"
                onChange={setQueue}
              />
              <table className="tbl" style={{ marginTop: 14 }}>
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>模型</th>
                    <th>状态</th>
                    <th>数据集</th>
                    <th className="r">时长</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleJobs.map(job => (
                    <tr key={job.job_id}>
                      <td className="mono">{job.job_id}</td>
                      <td className="nm">{job.model_type}</td>
                      <td>{statusIcon(job.status)} {statusLabel(job.status)}</td>
                      <td>{datasetLabel(job.params)}</td>
                      <td className="r">{formatDuration(job.duration_seconds) || statusLabel(job.status)}</td>
                    </tr>
                  ))}
                  {visibleJobs.length === 0 && (
                    <tr>
                      <td colSpan={5} className="prototype-panel-note">暂无训练服务返回的任务。</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </>
          )}

          {active === 'mlflow' && (
            <div style={{ display: 'grid', gap: 12 }}>
              <div>
                <div className="prototype-panel-note" style={{ marginBottom: 6 }}>
                  Loss 曲线（演示序列，终点锚定当前最优模型指标）
                </div>
                <ReactECharts option={lossOption} style={{ height: 220, width: '100%' }} notMerge />
              </div>
              <div>
                <div className="prototype-panel-note" style={{ marginBottom: 6 }}>
                  IC 曲线（演示序列，valid_ic 终点对齐最佳 IC {bestIc ? bestIc.toFixed(2) : '-'}）
                </div>
                <ReactECharts option={icOption} style={{ height: 220, width: '100%' }} notMerge />
              </div>
              {models.length > 0 ? models.slice(0, 3).map(model => {
                const ic = model.metrics?.ic ?? 0
                const sharpe = model.metrics?.sharpe ?? 0
                const width = Math.min(100, Math.max(8, Math.round(Math.abs(ic || sharpe) * 100)))
                return (
                <div className="dim-row" key={model.id}>
                  <div className="dim-lbl">{model.name}<span>{model.stage || 'none'}</span></div>
                  <div className="dim-bar-wrap">
                    <div className="dim-bar" style={{ width: `${width}%`, background: 'var(--accent)' }} />
                  </div>
                  <div className="dim-val">{ic ? ic.toFixed(2) : '-'}</div>
                </div>
              )}) : (
                <EmptyState title="暂无模型实验" detail="training/models 当前没有返回模型指标。" />
              )}
              <LineageChips
                items={[
                  { label: 'Job', value: schedule?.last_job_id || '暂无', tone: 'accent' },
                  { label: 'Next', value: schedule?.next_run || '未配置', tone: 'safe' },
                  { label: 'Gate', value: schedule?.auto_deploy ? 'AUTO' : 'REVIEW', tone: 'warn' },
                ]}
              />
            </div>
          )}
        </PrototypeCard>

        <SideRail title="发布闸门" meta="Model Registry">
          <RiskBanner
            status={releaseModels.length ? 'warn' : 'pass'}
            title={releaseModels.length ? `待复核：${releaseModels[0].name}` : '暂无待发布模型'}
            detail={schedule?.enabled ? `自动训练已启用，下一次：${schedule.next_run || '等待调度'}` : '上线前必须通过回测样本、漂移检测和人工审批。'}
          />
          <PrototypeCard title="资源状态" icon={<LineChartOutlined />}>
            <div className="li-row">
              <div className="li-badge">JOB</div>
              <div className="li-main">
                <div className="n">{schedule?.last_job_status || 'unknown'}</div>
                <div className="s">{schedule?.last_job_id || '暂无最近任务'}</div>
              </div>
            </div>
            <div className="li-row">
              <div className="li-badge">CRON</div>
              <div className="li-main">
                <div className="n">{schedule?.enabled ? '已启用' : '未启用'}</div>
                <div className="s">{schedule?.cron || '-'}</div>
              </div>
            </div>
          </PrototypeCard>
        </SideRail>
      </div>

      <Modal
        title="发起训练"
        open={runModalOpen}
        onOk={() => void submitTraining()}
        onCancel={() => setRunModalOpen(false)}
        okText="开始训练"
        cancelText="取消"
        confirmLoading={runSubmitting}
      >
        <div style={{ display: 'grid', gap: 12 }}>
          <label>
            <span className="plabel">模型类型</span>
            <select
              className="param-input"
              style={{ width: '100%', marginTop: 4 }}
              aria-label="模型类型"
              value={runForm.model_type}
              onChange={event => updateRunForm({ model_type: event.target.value })}
            >
              {MODEL_TYPE_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label>
              <span className="plabel">数据起始日</span>
              <input
                type="date"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="数据起始日"
                value={runForm.data_start_date || ''}
                onChange={event => updateRunForm({ data_start_date: event.target.value || null })}
              />
            </label>
            <label>
              <span className="plabel">数据截止日</span>
              <input
                type="date"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="数据截止日"
                value={runForm.data_end_date || ''}
                onChange={event => updateRunForm({ data_end_date: event.target.value || null })}
              />
            </label>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label>
              <span className="plabel">持有周期 horizon（天）</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="持有周期"
                min={1}
                max={60}
                value={runForm.horizon ?? 15}
                onChange={event => updateRunForm({ horizon: Number(event.target.value) })}
              />
            </label>
            <label>
              <span className="plabel">回看窗口 lookback（天）</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="回看窗口"
                min={30}
                max={500}
                value={runForm.lookback ?? 180}
                onChange={event => updateRunForm({ lookback: Number(event.target.value) })}
              />
            </label>
            <label>
              <span className="plabel">Optuna 试验数</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="Optuna 试验数"
                min={1}
                max={500}
                value={runForm.n_trials ?? 50}
                onChange={event => updateRunForm({ n_trials: Number(event.target.value) })}
              />
            </label>
            <label>
              <span className="plabel">交叉验证折数</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="交叉验证折数"
                min={2}
                max={10}
                value={runForm.cv_folds ?? 5}
                onChange={event => updateRunForm({ cv_folds: Number(event.target.value) })}
              />
            </label>
            <label>
              <span className="plabel">学习率（留空由 Optuna 搜索）</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="学习率"
                min={0.001}
                max={1}
                step={0.001}
                value={runForm.learning_rate ?? ''}
                onChange={event => updateRunForm({ learning_rate: event.target.value === '' ? null : Number(event.target.value) })}
              />
            </label>
            <label>
              <span className="plabel">最大深度（留空自动搜索）</span>
              <input
                type="number"
                className="param-input"
                style={{ width: '100%', marginTop: 4 }}
                aria-label="最大深度"
                min={2}
                max={16}
                value={runForm.max_depth ?? ''}
                onChange={event => updateRunForm({ max_depth: event.target.value === '' ? null : Number(event.target.value) })}
              />
            </label>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              aria-label="优于线上则自动上线"
              checked={autoDeploy}
              onChange={event => setAutoDeploy(event.target.checked)}
            />
            <span className="plabel" style={{ margin: 0 }}>优于线上则自动上线（仍需通过发布闸门）</span>
          </label>
        </div>
      </Modal>
    </PrototypePage>
  )
}

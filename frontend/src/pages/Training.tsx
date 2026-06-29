import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CheckCircleOutlined, ClockCircleOutlined, ExperimentOutlined, LineChartOutlined } from '@ant-design/icons'
import {
  trainingApi,
  type TrainingHistoryRecord,
  type TrainingModelRecord,
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

  useEffect(() => {
    let mounted = true
    Promise.allSettled([
      trainingApi.getHistory(),
      trainingApi.getModels(),
      trainingApi.getSchedule(),
    ]).then(([historyResponse, modelsResponse, scheduleResponse]) => {
        if (!mounted) return
        if (historyResponse.status === 'fulfilled') setJobs(historyResponse.value.data?.jobs || [])
        if (modelsResponse.status === 'fulfilled') setModels(modelsResponse.value.data?.models || [])
        if (scheduleResponse.status === 'fulfilled') setSchedule(scheduleResponse.value.data || null)
        const failed = [historyResponse, modelsResponse, scheduleResponse].filter(result => result.status === 'rejected').length
        setLoadError(failed > 0 ? `${failed} 个训练数据接口暂不可用` : '')
      })
    return () => {
      mounted = false
    }
  }, [])

  const runningJobs = jobs.filter(job => ['pending', 'preparing', 'running', 'evaluating'].includes(job.status))
  const releaseModels = models.filter(model => ['candidate', 'staging'].includes(model.stage))
  const failedJobs = jobs.filter(job => ['failed', 'cancelled'].includes(job.status))
  const historyJobs = jobs.filter(job => ['completed', 'failed', 'cancelled'].includes(job.status))
  const visibleJobs = queue === 'running' ? runningJobs : queue === 'release' ? historyJobs : jobs
  const bestIc = metricValue(models, jobs, 'ic')
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
                  { key: 'release', label: '已完成', count: historyJobs.length },
                  { key: 'history', label: '历史', count: jobs.length },
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
                    <th className="r">进度</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleJobs.map(job => (
                    <tr key={job.job_id}>
                      <td className="mono">{job.job_id}</td>
                      <td className="nm">{job.model_type}</td>
                      <td>{statusIcon(job.status)} {statusLabel(job.status)}</td>
                      <td>{datasetLabel(job.params)}</td>
                      <td className="r">{job.duration_seconds ? `${job.duration_seconds}s` : statusLabel(job.status)}</td>
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
    </PrototypePage>
  )
}

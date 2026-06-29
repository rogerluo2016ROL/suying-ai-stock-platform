import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CheckCircleOutlined, ClockCircleOutlined, ExperimentOutlined, LineChartOutlined } from '@ant-design/icons'
import {
  DataDomainBadge,
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

const tasks = [
  ['TRN-20260628-01', 'Kronos 30D path', '运行中', 'A股日线 + 因子宽表', '42%'],
  ['TRN-20260627-03', 'LightGBM signal rank', '待发布', '候选池样本', '100%'],
  ['TRN-20260627-02', 'Diagnosis risk head', '已完成', '诊断标签集', '100%'],
]

function activeTabFromPath(pathname: string) {
  if (pathname.includes('/tasks')) return 'tasks'
  if (pathname.includes('/mlflow')) return 'mlflow'
  return 'overview'
}

function statusIcon(status: string) {
  if (status === '已完成') return <CheckCircleOutlined className="down" />
  return <ClockCircleOutlined style={{ color: status === '待发布' ? 'var(--warn)' : 'var(--accent)' }} />
}

export default function Training() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const active = activeTabFromPath(pathname)
  const tab = useMemo(() => tabs.find(item => item.key === active) ?? tabs[0], [active])
  const [queue, setQueue] = useState('running')

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
        actions={[
          { key: 'admin', label: '管理员', active: true, tone: 'neutral' },
          { key: 'gate', label: '上线需复核', tone: 'warn' },
        ]}
      />

      <div className="kpis">
        <MetricCard label="运行任务" value="2" sub="GPU / CPU 混合队列" tone="accent" />
        <MetricCard label="待发布" value="1" sub="需模型闸门复核" tone="warn" />
        <MetricCard label="最佳 IC" value="0.12" sub="近30日 out-of-sample" tone="up" />
        <MetricCard label="失败任务" value="0" sub="今日无失败" tone="muted" />
      </div>

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
                  { key: 'running', label: '运行中', count: 2 },
                  { key: 'release', label: '待发布', count: 1 },
                  { key: 'history', label: '历史', count: 18 },
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
                  {tasks.map(row => (
                    <tr key={row[0]}>
                      <td className="mono">{row[0]}</td>
                      <td className="nm">{row[1]}</td>
                      <td>{statusIcon(row[2])} {row[2]}</td>
                      <td>{row[3]}</td>
                      <td className="r">{row[4]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {active === 'mlflow' && (
            <div style={{ display: 'grid', gap: 12 }}>
              {[
                ['IC', 72, 'var(--accent)', '+0.03 vs baseline'],
                ['命中率', 68, 'var(--down)', '+4.2pp'],
                ['回撤约束', 81, 'var(--warn)', '风险样本稳定'],
              ].map(row => (
                <div className="dim-row" key={row[0]}>
                  <div className="dim-lbl">{row[0]}<span>{row[3]}</span></div>
                  <div className="dim-bar-wrap">
                    <div className="dim-bar" style={{ width: `${row[1]}%`, background: row[2] }} />
                  </div>
                  <div className="dim-val">{row[1]}</div>
                </div>
              ))}
              <LineageChips
                items={[
                  { label: 'Experiment', value: 'MLF-8842', tone: 'accent' },
                  { label: 'Dataset', value: 'daily-v20260627', tone: 'safe' },
                  { label: 'Gate', value: 'REVIEW', tone: 'warn' },
                ]}
              />
            </div>
          )}
        </PrototypeCard>

        <SideRail title="发布闸门" meta="Model Registry">
          <RiskBanner
            status="warn"
            title="待复核：LightGBM signal rank"
            detail="上线前必须通过回测样本、漂移检测和人工审批。"
          />
          <PrototypeCard title="资源状态" icon={<LineChartOutlined />}>
            <div className="li-row">
              <div className="li-badge">GPU</div>
              <div className="li-main">
                <div className="n">1/2 使用中</div>
                <div className="s">Kronos 训练预计 36 分钟完成</div>
              </div>
            </div>
            <div className="li-row">
              <div className="li-badge">CPU</div>
              <div className="li-main">
                <div className="n">4 worker 空闲</div>
                <div className="s">因子模型可立即排队</div>
              </div>
            </div>
          </PrototypeCard>
        </SideRail>
      </div>
    </PrototypePage>
  )
}

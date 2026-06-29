import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiOutlined, CheckCircleOutlined, RollbackOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
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
  PrototypeTabs,
  RiskBanner,
  SideRail,
} from '../components/prototype'

const tabs = [
  { key: 'registry', label: '版本治理', subLabel: '生产 / 候选 / 回滚' },
]

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
  const [selectedId, setSelectedId] = useState('')
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [actionLoading, setActionLoading] = useState('')

  const loadModels = useCallback(async () => {
    try {
      const response = await trainingApi.getModels()
      const nextModels = response.data?.models || []
      setModels(nextModels)
      setSelectedId(current => {
        if (current && nextModels.some(model => model.id === current)) return current
        return nextModels[0]?.id || ''
      })
      setLoadError('')
    } catch {
      setModels([])
      setSelectedId('')
      setLoadError('模型注册服务暂不可用')
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
    return models.find(model => model.id === selectedId) || models[0]
  }, [models, selectedId])

  const productionModel = useMemo(() => {
    return models.find(model => model.stage === 'production')
  }, [models])

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

  function reviewProduction() {
    if (!productionModel) return
    void runAction('复核生产版本', async () => {
      const response = await trainingApi.getModel(productionModel.id)
      setSelectedId(response.data.id)
      return { data: { message: `已读取生产模型 ${response.data.name} v${response.data.version}` } }
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
      <PrototypeTabs
        items={tabs}
        activeKey="registry"
        ariaLabel="模型注册模块页签"
        onChange={() => undefined}
      />

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
        <PrototypeCard
          title="生产模型注册表"
          icon={<ApiOutlined />}
          meta={<DataDomainBadge domain="public" label="shared-model" />}
        >
          {models.length === 0 ? (
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
              disabled={!productionModel || actionLoading === '复核生产版本'}
              onClick={reviewProduction}
              title={productionModel ? '' : '暂无生产模型'}
            >
              <CheckCircleOutlined /> 复核生产版本
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

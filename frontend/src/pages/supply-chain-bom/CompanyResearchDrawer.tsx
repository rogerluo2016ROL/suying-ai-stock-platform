import { Alert, Descriptions, Drawer, Empty, Progress, Space, Spin, Tabs, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { screenerApi, type EvidenceChainResponse } from '../../api/client'
import EvidenceChainPanel from './EvidenceChainPanel'
import StageTimelinePanel from './StageTimelinePanel'
import type { CandidateCompany } from './types'
import { dimensionLabel, formatNumber } from './formatters'

const { Text } = Typography

interface CompanyResearchDrawerProps {
  open: boolean
  company: CandidateCompany | null
  onClose: () => void
}

export default function CompanyResearchDrawer({ open, company, onClose }: CompanyResearchDrawerProps) {
  const [evidenceChain, setEvidenceChain] = useState<EvidenceChainResponse | null>(null)
  const [loadingEvidence, setLoadingEvidence] = useState(false)
  const [evidenceError, setEvidenceError] = useState<string | null>(null)
  const dimensionEntries = Object.entries(company?.dimension_scores || {})
  const financial = company?.financial_indicators || {}

  useEffect(() => {
    if (!open || !company?.mapping_id) {
      setEvidenceChain(null)
      setEvidenceError(null)
      setLoadingEvidence(false)
      return
    }

    let active = true
    setLoadingEvidence(true)
    setEvidenceError(null)
    screenerApi.getSupplyChainEvidenceChain(company.mapping_id)
      .then((response) => {
        if (active) setEvidenceChain(response.data)
      })
      .catch((error: unknown) => {
        if (!active) return
        const message = error instanceof Error ? error.message : '证据链接口请求失败'
        setEvidenceError(message)
        setEvidenceChain(null)
      })
      .finally(() => {
        if (active) setLoadingEvidence(false)
      })

    return () => {
      active = false
    }
  }, [open, company?.mapping_id])

  const baseProfile = (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="业务映射 ID">{company?.mapping_id || '--'}</Descriptions.Item>
        <Descriptions.Item label="评级">{company?.rating || '--'}</Descriptions.Item>
        <Descriptions.Item label="排名">{company?.rank || '--'}</Descriptions.Item>
        <Descriptions.Item label="交易信号">{company?.trade_signal || '观察'}</Descriptions.Item>
        <Descriptions.Item label="BOM路径">{company?.bom_path?.join(' / ') || '--'}</Descriptions.Item>
        <Descriptions.Item label="产品">{company?.products?.join('、') || '--'}</Descriptions.Item>
        <Descriptions.Item label="材料">{company?.materials?.join('、') || '--'}</Descriptions.Item>
        <Descriptions.Item label="商业阶段">{company?.commercialization_stage || '--'}</Descriptions.Item>
        <Descriptions.Item label="周期位置">{company?.commercialization_cycle || '--'}</Descriptions.Item>
        <Descriptions.Item label="共振判断">{company?.resonance?.summary || '--'}</Descriptions.Item>
        <Descriptions.Item label="入选理由">{company?.selection_reason || '--'}</Descriptions.Item>
      </Descriptions>

      <div>
        <Text strong>评分拆解</Text>
        <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 8 }}>
          {dimensionEntries.length ? dimensionEntries.map(([key, value]) => (
            <div key={key}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text>{dimensionLabel[key] || key}</Text>
                <Text>{formatNumber(value, 1)}</Text>
              </Space>
              <Progress percent={Math.min(100, Number(value) * 5)} showInfo={false} size="small" />
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评分拆解" />}
        </Space>
      </div>

      <Descriptions title="财务指标" column={2} size="small" bordered>
        <Descriptions.Item label="收入增速">{formatNumber(financial.revenue_growth)}%</Descriptions.Item>
        <Descriptions.Item label="利润增速">{formatNumber(financial.profit_growth)}%</Descriptions.Item>
        <Descriptions.Item label="ROE">{formatNumber(financial.roe)}%</Descriptions.Item>
        <Descriptions.Item label="毛利率">{formatNumber(financial.gross_margin)}%</Descriptions.Item>
      </Descriptions>

      <div>
        <Text strong>护城河证据</Text>
        <Space wrap style={{ marginTop: 8 }}>
          {(company?.moat_evidence || []).length ? company?.moat_evidence?.map((item, index) => (
            <Tag key={`${item.summary}-${index}`} color="purple">{item.summary || item.evidence_type}</Tag>
          )) : <Tag>等待专利、招投标、产能、客户证据</Tag>}
        </Space>
      </div>
    </Space>
  )

  const evidenceContent = !company?.mapping_id ? (
    <Alert type="warning" showIcon message="缺少业务标签映射 ID，暂不能拉取证据链" />
  ) : (
    <Spin spinning={loadingEvidence}>
      {evidenceError ? <Alert type="error" showIcon message="证据链加载失败" description={evidenceError} /> : null}
      {!evidenceError ? <EvidenceChainPanel evidenceChain={evidenceChain} /> : null}
    </Spin>
  )

  const stageContent = !company?.mapping_id ? (
    <Alert type="warning" showIcon message="缺少业务标签映射 ID，暂不能拉取阶段跟踪" />
  ) : (
    <Spin spinning={loadingEvidence}>
      {evidenceError ? <Alert type="error" showIcon message="阶段跟踪加载失败" description={evidenceError} /> : null}
      {!evidenceError ? <StageTimelinePanel evidenceChain={evidenceChain} /> : null}
    </Spin>
  )

  return (
    <Drawer
      title={`${company?.name || company?.code || '上市公司'} ${company?.code || ''}`}
      open={open}
      onClose={onClose}
      width={680}
    >
      <Tabs
        items={[
          { key: 'profile', label: '基础画像', children: baseProfile },
          { key: 'evidence', label: '证据链', children: evidenceContent },
          { key: 'stage', label: '阶段跟踪', children: stageContent },
        ]}
      />
    </Drawer>
  )
}

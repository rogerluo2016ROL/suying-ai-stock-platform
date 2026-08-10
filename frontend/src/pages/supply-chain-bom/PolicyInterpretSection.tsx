// P2-08: 政策解读区块（替代旧 LLM 抽取）：粘贴文本 → chain/interpret → 主题提取
// 从 SupplyChainBom.tsx 拆出，policyText/policyResult 等 UI 状态下沉；
// 解读出的新主题通过 onAddThemes 回调上抛给页面

import { useState } from 'react'
import { Button, Checkbox, Input, message, Space, Tag, Typography } from 'antd'
import { FileTextOutlined, ScanOutlined } from '@ant-design/icons'
import { chainApi, type PolicyInterpretResponse } from '../../api/client'
import type { ResearchIngestionStatus, ThemeRow } from './types'
import { researchCollectionColor, researchCollectionLabel } from './helpers'
import { lightTokens } from '../../styles/tokens'

const { Text, Paragraph } = Typography
const { TextArea } = Input

interface PolicyInterpretSectionProps {
  researchIngestion: ResearchIngestionStatus
  onAddThemes: (themes: ThemeRow[]) => void
}

export default function PolicyInterpretSection({ researchIngestion, onAddThemes }: PolicyInterpretSectionProps) {
  const [policyText, setPolicyText] = useState('')
  const [policyResult, setPolicyResult] = useState<PolicyInterpretResponse | null>(null)
  const [policyLoading, setPolicyLoading] = useState(false)
  const [persistPolicy, setPersistPolicy] = useState(false)

  const runPolicyInterpret = async () => {
    const text = policyText.trim()
    if (!text) {
      message.warning('请输入政策解读文本')
      return
    }
    setPolicyLoading(true)
    try {
      const resp = await chainApi.interpretPolicy(text, { source_type: 'manual_paste' }, persistPolicy)
      const data = resp.data as PolicyInterpretResponse
      setPolicyResult(data)
      if (data.status === 'ok') {
        message.success('政策解读完成')
        // If interpretation extracted themes, add them to the list
        if (data.interpretation_result?.industry_themes?.length) {
          const newThemes = data.interpretation_result.industry_themes.map((t: any, idx: number) => ({
            theme_id: t.id || `policy-${Date.now()}-${idx}`,
            name: t.name || '新政策主题',
            policy_weight: t.weight || 1,
            keywords: t.keywords || [],
            node_count: 0,
          }))
          onAddThemes(newThemes)
        }
      } else if (data.status === 'disabled') {
        message.info(data.reason || '政策解读功能未启用')
      } else {
        message.error(data.reason || '政策解读失败')
      }
    } catch (err) {
      console.error('Policy interpret failed:', err)
      message.error('政策解读请求失败')
    } finally {
      setPolicyLoading(false)
    }
  }

  return (
    <div style={{ marginTop: 16, border: `1px solid ${lightTokens.border}`, borderRadius: lightTokens.radius, background: lightTokens.surface, padding: 16 }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap>
          <Text strong><FileTextOutlined style={{ marginRight: 6 }} />政策解读</Text>
          <Tag color={researchCollectionColor(researchIngestion.auto_collection_status)}>
            {researchCollectionLabel(researchIngestion.auto_collection_status)}
          </Tag>
          {policyResult?.status && (
            <Tag color={policyResult.status === 'ok' ? 'green' : policyResult.status === 'disabled' ? 'gold' : 'red'}>
              {policyResult.status === 'ok' ? '解读成功' : policyResult.status === 'disabled' ? '功能未启用' : '解读失败'}
            </Tag>
          )}
          {policyResult?.usage && (
            <Tag color="purple">
              tokens: {policyResult.usage.total_tokens}
            </Tag>
          )}
        </Space>
        {researchIngestion.message && (
          <Text type="secondary">{researchIngestion.message}</Text>
        )}
        <TextArea
          value={policyText}
          onChange={e => setPolicyText(e.target.value)}
          placeholder="粘贴政策文件、公告、新闻稿文本，LLM将自动解读并提取产业主题与投资逻辑..."
          autoSize={{ minRows: 4, maxRows: 8 }}
        />
        <Space wrap>
          <Button
            type="primary"
            icon={<ScanOutlined />}
            loading={policyLoading}
            disabled={!policyText.trim()}
            onClick={runPolicyInterpret}
          >
            解读政策
          </Button>
          <Checkbox checked={persistPolicy} onChange={e => setPersistPolicy(e.target.checked)}>
            写入待审核图谱
          </Checkbox>
          {policyResult?.persisted && <Tag color="green">已写入</Tag>}
        </Space>
        {policyResult?.interpretation_result && (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            {policyResult.interpretation_result.summary && (
              <Paragraph style={{ marginBottom: 0, background: lightTokens.surface2, padding: 8, borderRadius: 4 }}>
                {policyResult.interpretation_result.summary}
              </Paragraph>
            )}
            {policyResult.interpretation_result.investment_logic && (
              <Text type="secondary">投资逻辑: {policyResult.interpretation_result.investment_logic}</Text>
            )}
            {!!policyResult.interpretation_result.industry_themes?.length && (
              <Space wrap>
                <Text>产业主题:</Text>
                {policyResult.interpretation_result.industry_themes.map((t: any, idx: number) => (
                  <Tag key={idx} color="blue">{t.name || t}</Tag>
                ))}
              </Space>
            )}
            {!!policyResult.interpretation_result.bom_nodes?.length && (
              <Space wrap>
                <Text>BOM节点:</Text>
                {policyResult.interpretation_result.bom_nodes.map((node: string, idx: number) => (
                  <Tag key={idx}>{node}</Tag>
                ))}
              </Space>
            )}
            {!!policyResult.interpretation_result.risk_factors?.length && (
              <Space wrap>
                <Text>风险因素:</Text>
                {policyResult.interpretation_result.risk_factors.map((r: any, idx: number) => (
                  <Tag key={idx} color="orange">{r.name || r}</Tag>
                ))}
              </Space>
            )}
          </Space>
        )}
      </Space>
    </div>
  )
}

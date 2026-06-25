import { Button, Empty, Space, Table, Tag, Typography } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, ProfileOutlined, SignalFilled } from '@ant-design/icons'
import type { CandidateCompany } from './types'
import { formatNumber, scoreColor } from './formatters'

const { Text } = Typography

function formatChangePct(value?: number) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

function changeColor(value?: number) {
  const n = Number(value)
  if (!Number.isFinite(n) || n === 0) return 'default'
  return n > 0 ? 'red' : 'green'
}

/**
 * Determine resonance level color for V6 scoring
 */
function resonanceLevelColor(level: string): string {
  if (level === '强启动') return 'red'
  if (level === '启动') return 'orange'
  if (level === '关注') return 'blue'
  return 'default'
}

/**
 * Parse resonance info from dimension_scores or resonance field
 */
function parseResonanceInfo(row: CandidateCompany): {
  policyIntensity: number
  performanceProof: number
  chokepoint: number
} {
  const dimScores = row.dimension_scores || {}
  return {
    policyIntensity: dimScores.policy_intensity || 0,
    performanceProof: dimScores.performance_proof || 0,
    chokepoint: row.chokepoint_score || dimScores.chokepoint || 0,
  }
}

interface CandidateCompanyTableProps {
  candidates: CandidateCompany[]
  loading?: boolean
  selectedNodeName?: string
  mappingMessage?: string
  onOpenCompany: (company: CandidateCompany) => void
}

export default function CandidateCompanyTable({
  candidates,
  loading = false,
  selectedNodeName,
  mappingMessage,
  onOpenCompany,
}: CandidateCompanyTableProps) {
  const columns: any[] = [
    {
      title: '上市公司',
      dataIndex: 'name',
      width: 170,
      render: (_: string, row: CandidateCompany) => (
        <Button type="link" icon={<ProfileOutlined />} onClick={() => onOpenCompany(row)}>
          {row.name || row.code}
          <Text type="secondary" style={{ marginLeft: 6 }}>{row.code}</Text>
        </Button>
      ),
    },
    {
      title: '最新行情',
      width: 150,
      render: (_: unknown, row: CandidateCompany) => (
        <Space direction="vertical" size={4}>
          <Space size={6}>
            <Text strong>{formatNumber(row.last_price, 2)}</Text>
            <Tag color={changeColor(row.last_change_pct)} style={{ marginInlineEnd: 0 }}>
              {Number(row.last_change_pct) > 0 && <ArrowUpOutlined />}
              {Number(row.last_change_pct) < 0 && <ArrowDownOutlined />}
              <span style={{ marginLeft: Number.isFinite(Number(row.last_change_pct)) && Number(row.last_change_pct) !== 0 ? 4 : 0 }}>
                {formatChangePct(row.last_change_pct)}
              </span>
            </Tag>
          </Space>
          <Text type="secondary">{row.last_trade_date || '最近交易日待同步'}</Text>
        </Space>
      ),
    },
    {
      title: '产业链拆解',
      width: 250,
      render: (_: unknown, row: CandidateCompany) => (
        <Space direction="vertical" size={4}>
          <Space wrap>
            <Tag color="blue">{row.chain || row.bom_path?.[0] || '产业链'}</Tag>
            <Tag>{row.layer || row.bom_path?.slice(-1)[0] || '关键环节'}</Tag>
          </Space>
          <Space wrap>
            {(row.products || []).slice(0, 3).map(product => <Tag key={product} color="processing">{product}</Tag>)}
            {(row.materials || []).slice(0, 2).map(material => <Tag key={material}>{material}</Tag>)}
          </Space>
        </Space>
      ),
    },
    {
      title: '评分/信号',
      width: 160,
      render: (_: unknown, row: CandidateCompany) => (
        <Space direction="vertical" size={4}>
          <Space>
            <Tag color={scoreColor(row.score)}>#{row.rank || '--'} {formatNumber(row.score, 1)}</Tag>
            <Tag>{row.rating || row.chokepoint_score?.toString() || '待评级'}</Tag>
          </Space>
          <Tag color={resonanceLevelColor(row.trade_signal || '观察')}>
            <SignalFilled style={{ marginRight: 4 }} />
            {row.trade_signal || '观察'}
          </Tag>
        </Space>
      ),
    },
    {
      title: '三因子共振',
      width: 200,
      render: (_: unknown, row: CandidateCompany) => {
        const { policyIntensity, performanceProof, chokepoint } = parseResonanceInfo(row)
        return (
          <Space direction="vertical" size={4}>
            <Space size={4}>
              <Tag color={policyIntensity >= 3 ? 'red' : policyIntensity >= 1 ? 'gold' : 'default'}>
                政策: {policyIntensity.toFixed(0)}
              </Tag>
              <Tag color={performanceProof >= 10 ? 'green' : performanceProof >= 5 ? 'blue' : 'default'}>
                业绩: {performanceProof.toFixed(0)}
              </Tag>
              <Tag color={chokepoint >= 6 ? 'purple' : chokepoint >= 3 ? 'cyan' : 'default'}>
                卡脖: {chokepoint.toFixed(0)}
              </Tag>
            </Space>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {row.resonance?.summary || `${row.commercialization_stage || '待确认'} | ${row.commercialization_cycle || '产业验证'}`}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '入选理由',
      dataIndex: 'selection_reason',
      render: (reason: string) => <Text>{reason || '等待公告、专利、产能与财务证据补强'}</Text>,
    },
  ]

  return (
    <Table
      rowKey="code"
      size="small"
      loading={loading}
      columns={columns}
      dataSource={candidates}
      pagination={{ pageSize: 8, showSizeChanger: false }}
      scroll={{ x: 1270 }}
      locale={{
        emptyText: (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={selectedNodeName ? mappingMessage || '该节点缺少公司映射证据' : '暂无候选公司'}
          />
        ),
      }}
    />
  )
}

import { Button, Checkbox, Empty, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { DownloadOutlined, EyeOutlined } from '@ant-design/icons'
import { useMemo, useState } from 'react'
import type { CandidateCompany } from './types'
import { formatNumber, scoreColor } from './formatters'
import CandidateCompareBar from './CandidateCompareBar'
import { downloadResearchExport, evidenceQuality } from './researchWorkbenchUtils'

const { Text } = Typography

function statusText(status?: string) {
  if (status === 'verified') return '已确认'
  if (status === 'pending_review') return '待复核'
  if (status === 'weak_evidence') return '弱证据'
  if (status === 'rejected') return '已驳回'
  return status || '待复核'
}

function statusColor(status?: string) {
  if (status === 'verified') return 'green'
  if (status === 'pending_review') return 'gold'
  if (status === 'weak_evidence') return 'orange'
  if (status === 'rejected') return 'red'
  return 'default'
}

interface SupplyChainCandidateGridProps {
  candidates: CandidateCompany[]
  loading?: boolean
  selectedCodes: string[]
  selectedNodeName?: string
  mappingMessage?: string
  onToggleCompare: (company: CandidateCompany) => void
  onOpenCompany: (company: CandidateCompany) => void
}

export default function SupplyChainCandidateGrid({
  candidates,
  loading = false,
  selectedCodes,
  selectedNodeName,
  mappingMessage,
  onToggleCompare,
  onOpenCompany,
}: SupplyChainCandidateGridProps) {
  const [statusFilter, setStatusFilter] = useState('all')
  const filtered = useMemo(
    () => statusFilter === 'all' ? candidates : candidates.filter(item => item.mapping_status === statusFilter),
    [candidates, statusFilter],
  )
  const selectedCandidates = candidates.filter(item => selectedCodes.includes(item.code))

  const columns: TableColumnsType<CandidateCompany> = [
    {
      title: '',
      width: 54,
      fixed: 'left',
      render: (_: unknown, row: CandidateCompany) => (
        <Checkbox
          aria-label={`对比 ${row.name || row.code}`}
          checked={selectedCodes.includes(row.code)}
          onChange={() => onToggleCompare(row)}
        />
      ),
    },
    {
      title: '公司',
      width: 150,
      fixed: 'left',
      render: (_: unknown, row: CandidateCompany) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => onOpenCompany(row)}>
          {row.name || row.code}
        </Button>
      ),
    },
    { title: '行业', dataIndex: 'industry', width: 120 },
    {
      title: '链路节点',
      width: 180,
      render: (_: unknown, row: CandidateCompany) => `${row.chain || row.bom_path?.[0] || '--'} / ${row.node_name || row.layer || '--'}`,
    },
    {
      title: '原始分',
      width: 90,
      render: (_: unknown, row: CandidateCompany) => <Tag color={scoreColor(row.score)}>{formatNumber(row.score, 1)}</Tag>,
    },
    {
      title: '调整分',
      width: 90,
      render: (_: unknown, row: CandidateCompany) => <Tag color="blue">{formatNumber(row.mapping_adjusted_score ?? row.score, 1)}</Tag>,
    },
    {
      title: '映射',
      dataIndex: 'mapping_status',
      width: 100,
      render: (value: string) => <Tag color={statusColor(value)}>{statusText(value)}</Tag>,
    },
    {
      title: '证据评分',
      width: 100,
      render: (_: unknown, row: CandidateCompany) => {
        const quality = evidenceQuality(row)
        return <Tag color={quality.color}>{quality.score}</Tag>
      },
    },
    { title: '证据来源', dataIndex: 'mapping_source', width: 120 },
    { title: '信号', dataIndex: 'trade_signal', width: 100 },
    {
      title: '证据缺口',
      width: 220,
      render: (_: unknown, row: CandidateCompany) => (
        <Space wrap={false}>
          {(row.evidence_gaps || []).slice(0, 2).map(gap => <Tag key={gap}>{gap}</Tag>)}
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space>
          <Text strong>候选对比</Text>
          <Tag color="blue">{filtered.length}</Tag>
        </Space>
        <Select
          value={statusFilter}
          style={{ width: 140 }}
          onChange={setStatusFilter}
          options={[
            { value: 'all', label: '全部' },
            { value: 'verified', label: '已确认' },
            { value: 'pending_review', label: '待复核' },
            { value: 'weak_evidence', label: '弱证据' },
          ]}
        />
        <Button icon={<DownloadOutlined />} onClick={() => downloadResearchExport(filtered, selectedNodeName)}>
          导出清单
        </Button>
      </Space>
      <div data-testid="candidate-grid-wrap" style={{ whiteSpace: 'nowrap' }}>
        <Table
          rowKey="code"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          scroll={{ x: 1334 }}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={selectedNodeName ? mappingMessage || '该节点缺少公司映射证据' : '暂无候选公司'} />,
          }}
        />
      </div>
      <CandidateCompareBar candidates={selectedCandidates} />
    </Space>
  )
}

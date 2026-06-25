import { Empty, Space, Table, Tag, Typography } from 'antd'
import type { CandidateCompany } from './types'
import { formatNumber } from './formatters'

const { Text } = Typography

interface CandidateCompareBarProps {
  candidates: CandidateCompany[]
}

export default function CandidateCompareBar({ candidates }: CandidateCompareBarProps) {
  if (!candidates.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="勾选候选公司后进行横向对比" />
  }

  const columns: any[] = [
    {
      title: '公司',
      dataIndex: 'name',
      width: 140,
      render: (_: string, row: CandidateCompany) => <Text strong>{row.name || row.code}</Text>,
    },
    {
      title: '收入增速',
      dataIndex: ['financial_indicators', 'revenue_growth'],
      width: 110,
      render: (value: number) => `${formatNumber(value, 1)}%`,
    },
    {
      title: '利润增速',
      dataIndex: ['financial_indicators', 'profit_growth'],
      width: 110,
      render: (value: number) => `${formatNumber(value, 1)}%`,
    },
    {
      title: 'ROE',
      dataIndex: ['financial_indicators', 'roe'],
      width: 90,
      render: (value: number) => `${formatNumber(value, 1)}%`,
    },
    {
      title: '映射可信',
      dataIndex: 'mapping_confidence',
      width: 100,
      render: (value: number) => formatNumber(value, 2),
    },
    { title: '证据来源', dataIndex: 'mapping_source', width: 120 },
    {
      title: '缺口',
      dataIndex: 'evidence_gaps',
      width: 100,
      render: (gaps: string[] = []) => <Tag color={gaps.length ? 'orange' : 'green'}>{gaps.length}</Tag>,
    },
  ]

  return (
    <div aria-label="候选对比栏">
      <Table
        rowKey="code"
        size="small"
        columns={columns}
        dataSource={candidates}
        pagination={false}
        scroll={{ x: 770 }}
      />
    </div>
  )
}

import { Button, Descriptions, Drawer, Empty, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { BarChartOutlined } from '@ant-design/icons'
import { useState } from 'react'
import type { CandidateCompany } from './types'
import { formatNumber } from './formatters'
import { evidenceQuality } from './researchWorkbenchUtils'

const { Text } = Typography

interface CandidateCompareBarProps {
  candidates: CandidateCompany[]
}

export default function CandidateCompareBar({ candidates }: CandidateCompareBarProps) {
  const [open, setOpen] = useState(false)

  if (!candidates.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="勾选候选公司后进行横向对比" />
  }

  const columns: TableColumnsType<CandidateCompany> = [
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
    {
      title: '证据评分',
      width: 100,
      render: (_: unknown, row: CandidateCompany) => {
        const quality = evidenceQuality(row)
        return <Tag color={quality.color}>{quality.score}</Tag>
      },
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
      <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }}>
        <Text strong>已选 {candidates.length} 只</Text>
        <Button icon={<BarChartOutlined />} onClick={() => setOpen(true)}>
          对比详情
        </Button>
      </Space>
      <Table
        rowKey="code"
        size="small"
        columns={columns}
        dataSource={candidates}
        pagination={false}
        scroll={{ x: 870 }}
      />
      <Drawer
        title="候选对比详情"
        width={680}
        open={open}
        onClose={() => setOpen(false)}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {candidates.map((company) => {
            const quality = evidenceQuality(company)
            return (
              <Descriptions key={company.code} title={company.name || company.code} column={1} size="small" bordered>
                <Descriptions.Item label="代码">{company.code}</Descriptions.Item>
                <Descriptions.Item label="节点">{company.node_name || company.layer || '--'}</Descriptions.Item>
                <Descriptions.Item label="调整分">{formatNumber(company.mapping_adjusted_score ?? company.score, 1)}</Descriptions.Item>
                <Descriptions.Item label="映射可信">{formatNumber(company.mapping_confidence, 2)}</Descriptions.Item>
                <Descriptions.Item label="证据评分">
                  <Tag color={quality.color}>{quality.score}</Tag>
                  <Text type="secondary">{quality.label}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="产品">{company.products?.join('、') || '--'}</Descriptions.Item>
                <Descriptions.Item label="证据缺口">{company.evidence_gaps?.join('、') || '无'}</Descriptions.Item>
                <Descriptions.Item label="研报">{company.report_titles?.join('、') || '--'}</Descriptions.Item>
              </Descriptions>
            )
          })}
        </Space>
      </Drawer>
    </div>
  )
}

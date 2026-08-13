// 上游影响观察池：从下游战略产业反向拆解上游材料/设备/工艺/软件/零部件
// 从 SupplyChainBom.tsx 拆出，upstreamColumns 列定义随 UI 下沉

import { Button, Empty, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { EyeOutlined } from '@ant-design/icons'
import type { CandidateCompany } from './types'
import { formatNumber } from './formatters'
import { formatChangePct } from './helpers'

const { Text } = Typography

interface UpstreamPoolSectionProps {
  candidates: CandidateCompany[]
  onOpenCompany: (company: CandidateCompany) => void
}

export default function UpstreamPoolSection({ candidates, onOpenCompany }: UpstreamPoolSectionProps) {
  const upstreamColumns: TableColumnsType<CandidateCompany> = [
    {
      title: '上游公司',
      width: 180,
      render: (_: unknown, row: CandidateCompany) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => onOpenCompany(row)}>
          {row.name || row.code}
          <Text type="secondary" style={{ marginLeft: 6 }}>{row.code}</Text>
        </Button>
      ),
    },
    {
      title: '所属行业/行情',
      width: 190,
      render: (_: unknown, row: CandidateCompany) => (
        <Space direction="vertical" size={4}>
          <Space wrap>
            <Tag>{row.industry || '行业待确认'}</Tag>
            <Tag color="gold">{row.pool_status || '观察池'}</Tag>
          </Space>
          <Space size={6}>
            <Text strong>{formatNumber(row.last_price, 2)}</Text>
            <Tag color={Number(row.last_change_pct) >= 0 ? 'red' : 'green'}>{formatChangePct(row.last_change_pct)}</Tag>
            <Text type="secondary">{row.last_trade_date || '--'}</Text>
          </Space>
        </Space>
      ),
    },
    {
      title: '上游影响路径',
      width: 320,
      render: (_: unknown, row: CandidateCompany) => (
        <Space direction="vertical" size={4}>
          <Space wrap>
            <Tag color="cyan">{row.upstream_node || row.layer || '上游节点'}</Tag>
            <Tag color="blue">{row.impact_role || '上游使能环节'}</Tag>
          </Space>
          {(row.influence_paths || []).slice(0, 2).map(path => <Text key={path}>{path}</Text>)}
        </Space>
      ),
    },
    {
      title: '影响的下游产业',
      width: 240,
      render: (_: unknown, row: CandidateCompany) => (
        <Space wrap>
          {(row.downstream_chains || []).map(chain => <Tag key={chain} color="processing">{chain}</Tag>)}
        </Space>
      ),
    },
    {
      title: '待验证证据',
      width: 280,
      render: (_: unknown, row: CandidateCompany) => (
        <Space wrap>
          {(row.evidence_gaps || []).slice(0, 3).map(gap => <Tag key={gap}>{gap}</Tag>)}
        </Space>
      ),
    },
    {
      title: '入池理由',
      dataIndex: 'selection_reason',
      render: (reason: string) => <Text>{reason || '等待产品、客户、量产与财务证据补强'}</Text>,
    },
  ]

  return (
    <div style={{ marginTop: 16 }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
          <Space wrap>
            <Typography.Title level={5} style={{ margin: 0 }}>上游影响观察池</Typography.Title>
            <Tag color="cyan">{candidates.length}</Tag>
          </Space>
          <Text type="secondary">从下游战略产业反向拆解上游材料、设备、工艺、软件与零部件，不再用公司所属行业做硬边界</Text>
        </Space>
        <Table
          rowKey="code"
          size="small"
          columns={upstreamColumns}
          dataSource={candidates}
          pagination={{ pageSize: 6, showSizeChanger: false }}
          scroll={{ x: 1320 }}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无上游影响观察候选" />,
          }}
        />
      </Space>
    </div>
  )
}

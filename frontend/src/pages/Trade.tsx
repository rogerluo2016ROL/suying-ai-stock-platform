import { useState } from 'react'
import { Card, Form, Input, InputNumber, Button, Select, Table, Descriptions, Space, Typography, Tabs, Statistic, Row, Col, Tag } from 'antd'
import { DollarOutlined, SendOutlined } from '@ant-design/icons'

const { Title } = Typography

export default function Trade() {
  const [mode, setMode] = useState('paper')
  const [orders, setOrders] = useState<any[]>([])

  const placeOrder = (values: any) => {
    const { code, direction, price, volume } = values
    setOrders(prev => [{
      id: Date.now(), code, direction, price: price || '市价', volume,
      status: 'pending', time: new Date().toLocaleTimeString(),
    }, ...prev])
  }

  const orderColumns = [
    { title: '时间', dataIndex: 'time', width: 80 },
    { title: '代码', dataIndex: 'code', width: 100 },
    { title: '方向', dataIndex: 'direction', width: 60,
      render: (v: string) => <Tag color={v === 'BUY' ? 'red' : 'green'}>{v}</Tag> },
    { title: '价格', dataIndex: 'price', width: 80 },
    { title: '数量', dataIndex: 'volume', width: 80 },
    { title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => <Tag>{v}</Tag> },
  ]

  return (
    <div>
      <Title level={2}><DollarOutlined /> 交易</Title>
      <Tag color={mode === 'paper' ? 'blue' : 'red'} style={{ marginBottom: 16 }}>
        {mode === 'paper' ? '📝 模拟交易' : '🔴 实盘交易'}
      </Tag>

      <Row gutter={16}>
        <Col span={6}>
          <Card size="small"><Statistic title="总资产" value="1,000,000" prefix="¥" /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="可用资金" value="1,000,000" prefix="¥" /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="持仓市值" value="--" prefix="¥" /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="今日盈亏" value="--" prefix="¥" /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={8}>
          <Card title="下单">
            <Form layout="vertical" onFinish={placeOrder}>
              <Form.Item label="股票代码" name="code" rules={[{ required: true }]}>
                <Input placeholder="000001.XSHE" />
              </Form.Item>
              <Form.Item label="买卖方向" name="direction" initialValue="BUY">
                <Select options={[{ label: '🟢 买入', value: 'BUY' }, { label: '🔴 卖出', value: 'SELL' }]} />
              </Form.Item>
              <Form.Item label="价格 (0=市价)" name="price" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} precision={2} />
              </Form.Item>
              <Form.Item label="数量 (股)" name="volume" rules={[{ required: true }]}>
                <InputNumber style={{ width: '100%' }} min={100} step={100} />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<SendOutlined />} block>下单</Button>
            </Form>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="委托记录">
            <Table columns={orderColumns} dataSource={orders} rowKey="id" size="small"
                   pagination={{ pageSize: 10 }} />
          </Card>
        </Col>
      </Row>
    </div>
  )
}

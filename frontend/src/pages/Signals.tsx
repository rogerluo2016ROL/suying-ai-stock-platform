import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Table, Tag, Select, Space, Typography, Input, Button, Row, Col, message, Descriptions } from 'antd'
import { ThunderboltOutlined, SearchOutlined } from '@ant-design/icons'
import { signalApi } from '../api/client'

const { Title, Text } = Typography

const signalColors: Record<string, string> = {
  'STRONG_BUY': '#ff4d4f', 'BUY': '#fa8c16', 'HOLD': '#1677ff',
  'REDUCE': '#faad14', 'SELL': '#8c8c8c',
}

export default function Signals() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [result, setResult] = useState<any>(null)
  const [levels, setLevels] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    signalApi.getLevels().then(r => setLevels(r.data as unknown as string[])).catch(() => {})
  }, [])

  const analyzeSignal = async () => {
    if (!code) { message.warning('请输入股票代码'); return }
    setLoading(true)
    try {
      const { data } = await signalApi.analyzeCode(code)
      setResult(data)
    } catch (e: any) { message.error(e.response?.data?.detail || '分析失败') }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <ThunderboltOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          交易信号
        </Title>
        <Text type="secondary">信号强度 = Kronos×0.3 + 因子共振×0.3 + 规则匹配×0.2 + 市场适应×0.2</Text>
      </div>

      <Row gutter={16}>
        <Col span={16}>
          <Card title="实时信号分析" style={{ borderRadius: 8, marginBottom: 16 }}>
            <Space>
              <Input.Search placeholder="输入股票代码 (如 000001)" value={code}
                            onChange={e => setCode(e.target.value)} onSearch={analyzeSignal}
                            enterButton={<><SearchOutlined /> 分析</>} loading={loading}
                            style={{ width: 320 }} />
            </Space>

            {result && !result.error && (
              <div style={{ marginTop: 16 }}>
                <Descriptions column={2} size="small" bordered>
                  <Descriptions.Item label="股票代码">{result.code}</Descriptions.Item>
                  <Descriptions.Item label="信号">
                    <Tag color={signalColors[result.signal?.level]} style={{ fontWeight: 600 }}>
                      {result.signal?.icon} {result.signal?.level}
                    </Tag>
                    <Text style={{ marginLeft: 8 }}>({result.signal?.score}分)</Text>
                  </Descriptions.Item>
                  {result.factors?.five_factor && (
                    <>
                      <Descriptions.Item label="五因子评分">
                        {result.factors.five_factor.score}分 ({result.factors.five_factor.grade}级)
                      </Descriptions.Item>
                      <Descriptions.Item label="动量/量能/技术/质量/风险">
                        {result.factors.five_factor.momentum}/{result.factors.five_factor.volume}/
                        {result.factors.five_factor.technical}/{result.factors.five_factor.quality}/
                        {result.factors.five_factor.risk}
                      </Descriptions.Item>
                    </>
                  )}
                  <Descriptions.Item label="资金流向">{result.factors?.money_flow?.signal || '--'}</Descriptions.Item>
                  <Descriptions.Item label="趋势强度">{result.factors?.trend_strength?.score || '--'}分</Descriptions.Item>
                </Descriptions>
                <Descriptions column={1} size="small" bordered style={{ marginTop: 8 }}>
                  <Descriptions.Item label="信号分解">
                    Kronos: {result.components?.kronos_confidence?.score}分 |
                    因子: {result.components?.factor_resonance?.score}分 |
                    规则: {result.components?.rule_match?.score}分 |
                    市场: {result.components?.market_adapt?.score}分
                  </Descriptions.Item>
                </Descriptions>
              </div>
            )}
          </Card>

          <Card title="信号级别定义" style={{ borderRadius: 8 }}>
            <Table dataSource={levels} rowKey="level" size="small" pagination={false} columns={[
              { title: '信号', dataIndex: 'icon', width: 40 },
              { title: '级别', dataIndex: 'level', width: 120,
                render: (v: string) => <Tag color={signalColors.ALL}>{v}</Tag> },
              { title: '最低分', dataIndex: 'min_score', width: 80 },
              { title: '操作建议', dataIndex: 'action' },
            ]} />
          </Card>
        </Col>

        <Col span={8}>
          <Card title="信号模型" size="small" style={{ borderRadius: 8, marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              信号覆盖：<br />
              • 正式方案标的<br />
              • 模拟盘持仓<br />
              • 实盘持仓<br />
              • 用户自选股
            </Text>
          </Card>
          <Card title="K线亮化" size="small" style={{ borderRadius: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              🟢 绿色箭头 = 买入信号<br />
              🔴 红色箭头 = 卖出信号<br />
              ⚡ 黄色标记 = Kronos拐点
            </Text>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

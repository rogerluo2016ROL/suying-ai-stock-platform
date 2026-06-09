import { useState } from 'react'
import { Card, Input, Button, Descriptions, Tag, Space, Typography, Row, Col, Statistic, message, Spin, Progress } from 'antd'
import { LineChartOutlined, ThunderboltOutlined, RiseOutlined, FallOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export default function Predictions() {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)

  const runPredict = async () => {
    if (!code) { message.warning('请输入股票代码'); return }
    setLoading(true)
    try {
      // Use signal/analyze as fallback (returns factor scores when Kronos is offline)
      const r = await fetch(`/api/v1/signal/analyze/${code}`)
      const data = await r.json()
      setResult(data)
      message.success('分析完成')
    } catch {
      message.error('分析失败')
    } finally { setLoading(false) }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <LineChartOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          Kronos AI 预测
        </Title>
        <Text type="secondary" style={{ fontSize: 13 }}>30日价格轨迹预测 · 拐点识别 · 风险量化</Text>
      </div>

      <Row gutter={16}>
        <Col span={16}>
          <Card style={{ borderRadius: 8, marginBottom: 16 }}>
            <Space>
              <Input.Search placeholder="输入股票代码 (如 000001)" value={code}
                            onChange={e => setCode(e.target.value)} onSearch={runPredict}
                            enterButton="开始预测" loading={loading} style={{ width: 300 }} />
            </Space>
          </Card>

          <Spin spinning={loading}>
            {result && !result.error && (
              <>
                <Row gutter={12} style={{ marginBottom: 16 }}>
                  <Col span={6}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="信号级别" value={result.signal?.level || '--'}
                                valueStyle={{ color: result.signal?.score >= 60 ? '#52c41a' : '#faad14' }} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="综合评分" value={result.signal?.score} suffix="分" />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="技术面" value={result.components?.factor_resonance?.detail?.technical}
                                suffix="分" valueStyle={{ color: '#1677ff' }} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="资金面" value={result.components?.factor_resonance?.detail?.money_flow}
                                suffix="分" valueStyle={{ color: '#52c41a' }} />
                    </Card>
                  </Col>
                </Row>

                <Card title={<Space><LineChartOutlined style={{ color: '#1677ff' }} />预测因子详情</Space>}
                      style={{ borderRadius: 8 }}>
                  {result.factors?.five_factor && (
                    <Descriptions column={2} size="small" bordered>
                      <Descriptions.Item label="五因子评分">
                        {result.factors.five_factor.score}分 ({result.factors.five_factor.grade}级)
                      </Descriptions.Item>
                      <Descriptions.Item label="动量/量能/技术/质量/风险">
                        {result.factors.five_factor.momentum}/{result.factors.five_factor.volume}/
                        {result.factors.five_factor.technical}/{result.factors.five_factor.quality}/
                        {result.factors.five_factor.risk}
                      </Descriptions.Item>
                      <Descriptions.Item label="资金流向">
                        <Tag color={result.factors.money_flow?.signal === 'inflow' ? 'green' : 'orange'}>
                          {result.factors.money_flow?.signal}
                        </Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="趋势强度">
                        {result.factors.trend_strength?.score}分 ({result.factors.trend_strength?.adx} ADX)
                      </Descriptions.Item>
                    </Descriptions>
                  )}
                </Card>

                <Card style={{ borderRadius: 8, marginTop: 16 }}>
                  <div style={{ height: 280, background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                    borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#fff', flexDirection: 'column', gap: 8 }}>
                    <LineChartOutlined style={{ fontSize: 48, opacity: 0.6 }} />
                    <Text style={{ color: 'rgba(255,255,255,0.6)' }}>📈 Kronos 30日预测K线图</Text>
                    <Text style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>
                      启动 prediction-service 后渲染真实预测K线
                    </Text>
                  </div>
                </Card>
              </>
            )}
          </Spin>
        </Col>

        <Col span={8}>
          <Card title="预测引擎" size="small" style={{ borderRadius: 8, marginBottom: 16 }}>
            <Tag color="blue" style={{ marginBottom: 8 }}>AI-POWERED</Tag>
            <div style={{ fontSize: 13 }}>
              <p>• <b>Kronos-base</b> (102M参数)</p>
              <p>• 30日 OHLCV 预测</p>
              <p>• 趋势拐点识别</p>
              <p>• 最大回调风险量化</p>
              <p>• 5条采样路径融合</p>
            </div>
          </Card>
          <Card title="批量预测" size="small" style={{ borderRadius: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              对接 POST /api/v1/prediction/predict-batch<br />
              最多30只 · 每只可选5条采样路径
            </Text>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

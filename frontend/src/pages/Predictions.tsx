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
      const r = await fetch(`/api/v1/prediction/predict/${code}?pred_days=10`, { method: 'POST' })
      const data = await r.json()
      setResult(data)
      message.success(`Kronos预测: ${data.pred_return_pct > 0 ? '📈' : '📉'} ${data.pred_return_pct > 0 ? '+' : ''}${data.pred_return_pct}%`)
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
                      <Statistic title="当前价" value={result.current_price} prefix="¥" />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="预测收盘" value={result.pred_last_close} prefix="¥"
                                valueStyle={{ color: result.pred_return_pct >= 0 ? '#52c41a' : '#ff4d4f' }} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="预期收益" value={`${result.pred_return_pct > 0 ? '+' : ''}${result.pred_return_pct}%`}
                                valueStyle={{ color: result.pred_return_pct >= 0 ? '#52c41a' : '#ff4d4f' }} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="趋势" value={result.trend} />
                    </Card>
                  </Col>
                </Row>

                <Card title={<Space><LineChartOutlined style={{ color: '#1677ff' }} />Kronos 预测详情</Space>}
                      style={{ borderRadius: 8 }}>
                  <Descriptions column={2} size="small" bordered>
                    <Descriptions.Item label="预测区间">{result.pred_low} ~ {result.pred_high}</Descriptions.Item>
                    <Descriptions.Item label="最大回调">
                      <Tag color={result.max_drawdown_pct < -5 ? 'red' : 'orange'}>{result.max_drawdown_pct}%</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="预测天数">{result.pred_days} 天</Descriptions.Item>
                    <Descriptions.Item label="轨迹点数">{result.pred_trajectory?.length || 0}</Descriptions.Item>
                  </Descriptions>
                </Card>

                {result.pred_trajectory && (
                  <Card title="预测轨迹" style={{ borderRadius: 8, marginTop: 16 }}>
                    <div style={{ display: 'flex', gap: 4, overflowX: 'auto', paddingBottom: 8 }}>
                      {result.pred_trajectory.map((p: any) => (
                        <div key={p.day} style={{
                          minWidth: 50, textAlign: 'center', padding: 8,
                          background: p.close >= result.current_price ? '#f6ffed' : '#fff2f0',
                          borderRadius: 4, border: '1px solid ' + (p.close >= result.current_price ? '#b7eb8f' : '#ffa39e'),
                        }}>
                          <div style={{ fontSize: 10, color: '#8c8c8c' }}>D{p.day}</div>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{p.close}</div>
                          <div style={{ fontSize: 10, color: p.close >= result.current_price ? '#52c41a' : '#ff4d4f' }}>
                            {p.close >= result.current_price ? '↑' : '↓'}
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
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

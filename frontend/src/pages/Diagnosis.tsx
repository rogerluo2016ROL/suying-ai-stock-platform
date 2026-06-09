import { useState } from 'react'
import { Card, Input, Button, Descriptions, Tag, Progress, Space, Typography, Row, Col, Statistic, message, Spin } from 'antd'
import { FundOutlined, LineChartOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export default function Diagnosis() {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)

  const analyze = async () => {
    if (!code) { message.warning('请输入股票代码'); return }
    setLoading(true)
    try {
      const [sigRes, predRes] = await Promise.all([
        fetch(`/api/v1/signal/analyze/${code}`),
        fetch(`/api/v1/prediction/predict/${code}?pred_days=10`, { method: 'POST' }).catch(() => null),
      ])
      const signal = await sigRes.json()
      const prediction = predRes ? await predRes.json() : null
      setResult({ signal, prediction })
      message.success(`诊断完成: ${signal.signal?.level}`)
    } catch { message.error('诊断失败') }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <FundOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          个股诊断
        </Title>
        <Text type="secondary">五维分析：技术面 · 资金面 · 基本面 · AI预测 · 情绪面</Text>
      </div>

      <Row gutter={16}>
        <Col span={16}>
          <Card style={{ borderRadius: 8, marginBottom: 16 }}>
            <Space>
              <Input.Search placeholder="输入股票代码" value={code} onChange={e => setCode(e.target.value)}
                            onSearch={analyze} enterButton="开始诊断" loading={loading} style={{ width: 280 }} />
            </Space>
          </Card>

          <Spin spinning={loading}>
            {result?.signal && (
              <>
                <Card style={{ borderRadius: 8, marginBottom: 16 }}>
                  <Row gutter={12}>
                    <Col span={6}><Statistic title="综合评分" value={result.signal?.signal?.score || '--'} suffix="分" /></Col>
                    <Col span={6}><Statistic title="信号" value={result.signal?.level} valueStyle={{ color: '#1677ff' }} /></Col>
                    <Col span={6}><Statistic title="技术面" value={result.components?.factor_resonance?.detail?.technical} suffix="分" /></Col>
                    <Col span={6}><Statistic title="资金面" value={result.components?.factor_resonance?.detail?.money_flow} suffix="分" /></Col>
                  </Row>
                </Card>

                <Card title="五维诊断" style={{ borderRadius: 8, marginBottom: 16 }}>
                  {[
                    { key: '技术面', score: Number(result.components?.factor_resonance?.detail?.technical) || 50, weight: 40, color: '#1677ff' },
                    { key: '资金面', score: Number(result.components?.factor_resonance?.detail?.money_flow) || 50, weight: 25, color: '#52c41a' },
                    { key: '趋势面', score: Number(result.components?.factor_resonance?.detail?.trend) || 50, weight: 15, color: '#faad14' },
                    { key: 'AI预测', score: 50, weight: 10, color: '#722ed1' },
                    { key: '情绪面', score: 50, weight: 10, color: '#fa8c16' },
                  ].map(d => (
                    <div key={d.key} style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
                      <Tag style={{ width: 60, textAlign: 'center' }}>{d.key}</Tag>
                      <Progress percent={d.score} size="small" strokeColor={d.color} style={{ flex: 1 }} />
                      <Text type="secondary" style={{ width: 60 }}>权重 {d.weight}%</Text>
                    </div>
                  ))}
                </Card>

                {result.factors?.five_factor && (
                  <Card title="五因子细节" style={{ borderRadius: 8 }}>
                    <Descriptions column={2} size="small" bordered>
                      <Descriptions.Item label="评分">{result.factors.five_factor.score}分 ({result.factors.five_factor.grade}级)</Descriptions.Item>
                      <Descriptions.Item label="动量">{result.factors.five_factor.momentum}</Descriptions.Item>
                      <Descriptions.Item label="量能">{result.factors.five_factor.volume}</Descriptions.Item>
                      <Descriptions.Item label="技术">{result.factors.five_factor.technical}</Descriptions.Item>
                      <Descriptions.Item label="质量">{result.factors.five_factor.quality}</Descriptions.Item>
                      <Descriptions.Item label="风险">{result.factors.five_factor.risk}</Descriptions.Item>
                      <Descriptions.Item label="资金流">{result.factors.money_flow?.signal}</Descriptions.Item>
                      <Descriptions.Item label="趋势(ADX)">{result.factors.trend_strength?.adx}</Descriptions.Item>
                    </Descriptions>
                  </Card>
                )}
              </>
            )}
          </Spin>
        </Col>

        <Col span={8}>
          <Card title="诊断维度" size="small" style={{ borderRadius: 8, marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              📊 <b>技术面</b> — 均线/形态/指标<br />
              💰 <b>资金面</b> — 主力/北向/龙虎榜<br />
              📈 <b>基本面</b> — PE/ROE/成长<br />
              🤖 <b>AI预测</b> — Kronos K线预测<br />
              🎯 <b>情绪面</b> — 新闻/研报/舆情
            </Text>
          </Card>
          <Card title="关键价位" size="small" style={{ borderRadius: 8 }}>
            <div style={{ fontSize: 12 }}>
              <Tag color="green">支撑</Tag> --<br />
              <Tag color="red">压力</Tag> --<br />
              <Tag color="orange">止损</Tag> --
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

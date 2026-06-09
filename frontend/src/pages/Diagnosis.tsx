import { useState } from 'react'
import { Card, Input, Button, Descriptions, Tag, Progress, Space, Typography, Row, Col, Statistic, message } from 'antd'
import { FundOutlined } from '@ant-design/icons'
import { diagnosisApi } from '../api/client'

const { Title } = Typography

export default function Diagnosis() {
  const [code, setCode] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const analyze = async () => {
    if (!code) { message.warning('请输入股票代码'); return }
    setLoading(true)
    try {
      const r = await diagnosisApi.analyze(code.toUpperCase())
      setResult(r.data)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '诊断失败')
    } finally { setLoading(false) }
  }

  return (
    <div>
      <Title level={2}><FundOutlined /> 个股诊断</Title>

      <Card>
        <Space>
          <Input placeholder="输入股票代码" value={code} onChange={e => setCode(e.target.value)}
                 style={{ width: 200 }} onPressEnter={analyze} />
          <Button type="primary" loading={loading} onClick={analyze}>开始诊断</Button>
        </Space>
      </Card>

      {result && (
        <>
          <Card style={{ marginTop: 16 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title="综合评分" value={result.overall_score} suffix="/100" />
              </Col>
              <Col span={6}>
                <Statistic title="评级" value={result.grade} />
              </Col>
              <Col span={6}>
                <Statistic title="建议" value={result.recommendation} />
              </Col>
              <Col span={6}>
                <Statistic title="Kronos预测收益" value={`${result.kronos_prediction?.pred_return_pct || '--'}%`} />
              </Col>
            </Row>
          </Card>

          <Card title="五维诊断" style={{ marginTop: 16 }}>
            {Object.entries(result.dimensions || {}).map(([key, dim]: [string, any]) => (
              <div key={key} style={{ marginBottom: 12 }}>
                <Space>
                  <Tag color={dim.grade === 'A' ? 'green' : dim.grade === 'B' ? 'blue' : 'orange'}>{dim.grade}</Tag>
                  <span>{key}</span>
                  <Progress percent={dim.score * 10} size="small" style={{ width: 200 }} />
                  <Typography.Text type="secondary">权重 {dim.weight * 100}%</Typography.Text>
                </Space>
              </div>
            ))}
          </Card>

          {result.kronos_prediction && (
            <Card title="Kronos AI 预测" style={{ marginTop: 16 }}>
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="30日预测收盘">{result.kronos_prediction.pred_30d_close}</Descriptions.Item>
                <Descriptions.Item label="趋势">{result.kronos_prediction.trend}</Descriptions.Item>
                <Descriptions.Item label="最大回调"><Tag color="red">{result.kronos_prediction.max_drawdown_pct}%</Tag></Descriptions.Item>
                <Descriptions.Item label="拐点天数">{result.kronos_prediction.inflection_days?.join(', ')}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          <Card title="关键价位" style={{ marginTop: 16 }}>
            <Descriptions column={3} size="small">
              <Descriptions.Item label="支撑位">{result.key_levels?.support}</Descriptions.Item>
              <Descriptions.Item label="压力位">{result.key_levels?.resistance}</Descriptions.Item>
              <Descriptions.Item label="止损位"><Tag color="red">{result.key_levels?.stop_loss}</Tag></Descriptions.Item>
            </Descriptions>
          </Card>
        </>
      )}
    </div>
  )
}

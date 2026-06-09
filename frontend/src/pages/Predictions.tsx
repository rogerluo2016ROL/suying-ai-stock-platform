import { useState } from 'react'
import { Card, Input, Button, Descriptions, Tag, Space, Typography, message, Row, Col, Statistic } from 'antd'
import { LineChartOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { predictionApi } from '../api/client'

const { Title } = Typography

export default function Predictions() {
  const [code, setCode] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const runPredict = async () => {
    if (!code) { message.warning('请输入股票代码'); return }
    setLoading(true)
    try {
      const r = await predictionApi.predict(code.toUpperCase())
      setResult(r.data)
      message.success('预测完成')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '预测失败')
    } finally { setLoading(false) }
  }

  return (
    <div>
      <Title level={2}><LineChartOutlined /> Kronos AI 预测</Title>

      <Card>
        <Space>
          <Input placeholder="输入股票代码 (如 000001.XSHE)" value={code}
                 onChange={e => setCode(e.target.value)} style={{ width: 240 }}
                 onPressEnter={runPredict} />
          <Button type="primary" loading={loading} onClick={runPredict}>开始预测</Button>
        </Space>
      </Card>

      {result && (
        <Card title={`${code} — Kronos 预测结果`} style={{ marginTop: 16 }}>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="状态">{result.status}</Descriptions.Item>
            <Descriptions.Item label="预测天数">{result.pred_days} 天</Descriptions.Item>
            <Descriptions.Item label="预期收益">
              <Tag color="green">{result.pred_return_pct || '--'}%</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="最大回调">
              <Tag color="red">{result.max_drawdown_pct || '--'}%</Tag>
            </Descriptions.Item>
          </Descriptions>

          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={8}>
              <Card size="small"><Statistic title="预测收盘价" value={result.pred_last_close || '--'} suffix="元" /></Card>
            </Col>
            <Col span={8}>
              <Card size="small"><Statistic title="预测最高价" value={result.pred_high || '--'} suffix="元" /></Card>
            </Col>
            <Col span={8}>
              <Card size="small"><Statistic title="预测最低价" value={result.pred_low || '--'} suffix="元" /></Card>
            </Col>
          </Row>

          <div style={{ marginTop: 16, height: 300, background: '#1a1a2e', borderRadius: 8,
                        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Typography.Text type="secondary">
              📈 Kronos 30日预测K线图 — 对接数据管道后渲染
            </Typography.Text>
          </div>
        </Card>
      )}

      <Card title="批量预测" style={{ marginTop: 16 }}>
        <Typography.Text type="secondary">
          批量预测对接 POST /api/v1/prediction/predict-batch (最多30只)
        </Typography.Text>
      </Card>
    </div>
  )
}

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Input, Button, Descriptions, Tag, Space, Typography, Row, Col, Statistic, message, Spin } from 'antd'
import { LineChartOutlined, ThunderboltOutlined, RiseOutlined, FallOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { predictionApi } from '../api/client'

const { Title, Text } = Typography

// P1-09: trajectory candle shape returned by the prediction API
interface TrajectoryPoint {
  day: number
  open: number
  high: number
  low: number
  close: number
}

// Build an ECharts candlestick option from the prediction trajectory.
// Replaces the previous 200-line hand-rolled div candlestick (no axis/tooltip/zoom).
function buildTrajectoryOption(traj: TrajectoryPoint[]): EChartsOption {
  const upColor = '#26a69a'
  const downColor = '#ef5350'
  return {
    backgroundColor: '#1a1a2e',
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    xAxis: {
      type: 'category',
      data: traj.map(p => `D${p.day}`),
      axisLine: { lineStyle: { color: '#888' } },
      axisLabel: { color: '#aaa', fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: '#aaa', fontSize: 10 },
      splitLine: { lineStyle: { color: '#333' } },
    },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 4 }],
    grid: { left: 48, right: 16, top: 16, bottom: 40 },
    series: [{
      type: 'candlestick',
      data: traj.map(p => [p.open, p.close, p.low, p.high]),
      itemStyle: {
        color: upColor,
        color0: downColor,
        borderColor: upColor,
        borderColor0: downColor,
      },
    }],
  }
}

export default function Predictions() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)

  // P1-09: memoize the ECharts option so it isn't rebuilt on every render.
  const trajectoryOption = useMemo<EChartsOption | null>(() => {
    const traj: TrajectoryPoint[] | undefined = result?.pred_trajectory
    if (!traj || !traj.length) return null
    return buildTrajectoryOption(traj)
  }, [result?.pred_trajectory])

  const runPredict = async () => {
    if (!code) { message.warning('请输入股票代码'); return }
    setLoading(true)
    try {
      const { data } = await predictionApi.predict(code, 10)
      setResult(data)
      message.success(`Kronos预测: ${data.pred_return_pct > 0 ? '📈' : '📉'} ${data.pred_return_pct > 0 ? '+' : ''}${data.pred_return_pct}%`)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '分析失败')
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
                <div style={{ marginBottom: 12 }}>
                  <a onClick={() => navigate(`/diagnosis?code=${code}`)} style={{ fontSize: 13 }}>
                    🔍 查看 {code} 完整诊断 →
                  </a>
                </div>
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

                {trajectoryOption && (
                  <Card title="Kronos 预测K线图" style={{ borderRadius: 8, marginTop: 16 }}>
                    <div style={{ background: '#1a1a2e', borderRadius: 8, padding: 16 }}>
                      <ReactECharts option={trajectoryOption} style={{ height: 280, width: '100%' }} notMerge />
                      <div style={{ display: 'flex', gap: 16, marginTop: 4, justifyContent: 'center' }}>
                        <Space><span style={{ width: 10, height: 10, background: '#26a69a', borderRadius: 1, display: 'inline-block' }} /><Text style={{ color: '#aaa', fontSize: 10 }}>阳线</Text></Space>
                        <Space><span style={{ width: 10, height: 10, background: '#ef5350', borderRadius: 1, display: 'inline-block' }} /><Text style={{ color: '#aaa', fontSize: 10 }}>阴线</Text></Space>
                      </div>
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
              对接 POST /api/v1/prediction/{'{'}code{'}'}<br />
              最多30只 · 每只可选5条采样路径
            </Text>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

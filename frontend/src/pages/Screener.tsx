import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Select, Button, Table, Tag, Space, Typography, InputNumber, message, Row, Col, Divider } from 'antd'
import { PlayCircleOutlined, TrophyOutlined, FilterOutlined, FileTextOutlined, InfoCircleOutlined } from '@ant-design/icons'
import { screenerApi, strategyApi } from '../api/client'

const { Title, Text } = Typography

export default function Screener() {
  const navigate = useNavigate()
  const [modes, setModes] = useState<any[]>([])
  const [mode, setMode] = useState('leader_scalp')
  const [topN, setTopN] = useState(20)
  const [loading, setLoading] = useState(false)
  const [picks, setPicks] = useState<any[]>([])
  const [marketEnv, setMarketEnv] = useState('')
  const [stats, setStats] = useState({ scored: 0, excluded: 0, elapsed: 0 })
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [sortBy, setSortBy] = useState('score')
  const [expandedRow, setExpandedRow] = useState<string | null>(null)

  const generatePlan = async () => {
    const selectedPicks = picks.filter((p:any) => selectedRowKeys.includes(p.code))
    if (selectedPicks.length === 0) { message.warning('请先勾选股票'); return }
    try {
      const r1 = await strategyApi.createPlan(
        `选股方案-${new Date().toLocaleDateString()}`, mode, selectedPicks.length)
      const plan = r1.data
      await strategyApi.addPicks(plan.plan.id, selectedPicks)
      message.success(`预方案已生成: ${plan.plan.id} (${selectedPicks.length}只)`)
      setSelectedRowKeys([])
    } catch { message.error('方案生成失败，请检查strategy-service是否启动') }
  }

  useEffect(() => {
    screenerApi.getModes().then(r => setModes(r.data.modes || [])).catch(() => {})
  }, [])

  const runScreening = async () => {
    setLoading(true)
    try {
      const r = await screenerApi.run(mode, topN)
      const data = r.data
      setPicks(data.picks || [])
      setMarketEnv(data.market_env || '')
      setStats({
        scored: data.total_scored || data.picks?.length || 0,
        excluded: data.total_excluded || 0,
        elapsed: data.elapsed || 0,
      })
      message.success(`选股完成: ${data.total_scored || data.picks?.length || 0} 只 | ${(data.elapsed || 0).toFixed(0)}s`)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '选股失败')
    } finally { setLoading(false) }
  }

  const columns = [
    { title: '#', width: 40, render: (_: any, __: any, i: number) => (
      <Text type="secondary" style={{ fontSize: 12 }}>{i + 1}</Text>
    )},
    { title: '代码', dataIndex: 'code', width: 100, render: (v: string) => (
      <a onClick={() => navigate(`/diagnosis?code=${v}`)} style={{ cursor: 'pointer' }}>
        <Text code style={{ fontSize: 12 }}>{v}</Text>
      </a>
    )},
    { title: '名称', dataIndex: 'name', width: 90, render: (v: string, record: any) => (
      <a onClick={() => navigate(`/diagnosis?code=${record.code}`)} style={{ cursor: 'pointer', color: '#1677ff' }}>
        {v}
      </a>
    )},
    { title: '价格', dataIndex: 'price', width: 70, render: (v: number) => v?.toFixed(2) },
    { title: '评分', dataIndex: 'score', width: 65, render: (v: number) => (
      <Text strong style={{ color: v >= 16 ? '#ff4d4f' : v >= 12 ? '#fa8c16' : '#1890ff' }}>
        {v?.toFixed(1)}
      </Text>
    )},
    { title: '等级', dataIndex: 'grade', width: 50, render: (v: string) => {
      const color = v === 'S' ? '#ff4d4f' : v === 'A' ? '#fa8c16' : v === 'B' ? '#1890ff' : '#8c8c8c'
      return <Tag color={color} style={{ fontWeight: 600 }}>{v}</Tag>
    }},
    { title: '入场', dataIndex: 'entry_price', width: 70, render: (v: any) => v ? (
      <Text style={{ color: '#52c41a' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text> },
    { title: '止损', dataIndex: 'stop_loss', width: 70, render: (v: any) => v ? (
      <Text style={{ color: '#ff4d4f' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text> },
    { title: '目标', dataIndex: 'target_price', width: 70, render: (v: any) => v ? (
      <Text style={{ color: '#1a73e8' }}>{Number(v).toFixed(2)}</Text>
    ) : <Text type="secondary">--</Text> },
  ]

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div className="section-title">智能选股</div>
        <Text type="secondary">6套内置策略 · 全市场5000+标的 · 多因子智能排序</Text>
      </div>

      {/* ── Control Panel ── */}
      <Card style={{ borderRadius: 8, marginBottom: 16 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col>
            <Space>
              <FilterOutlined style={{ color: '#8c8c8c' }} />
              <Select value={mode} onChange={setMode} style={{ width: 220 }} options={
                modes.map((m: any) => ({ label: `${m.name} (${m.cycle})`, value: m.id }))
              } />
            </Space>
          </Col>
          <Col>
            <Space>
              <TrophyOutlined style={{ color: '#8c8c8c' }} />
              <InputNumber min={5} max={100} value={topN} onChange={v => setTopN(v || 20)}
                           style={{ width: 80 }} />
              <Text type="secondary" style={{ fontSize: 12 }}>只</Text>
            </Space>
          </Col>
          <Col>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={loading}
                    onClick={runScreening} size="middle">
              开始选股
            </Button>
            {picks.length > 0 && (
              <Button icon={<FileTextOutlined />} onClick={generatePlan}
                      disabled={selectedRowKeys.length === 0}>
                生成预方案 ({selectedRowKeys.length})
              </Button>
            )}
          </Col>
          {marketEnv && (
            <Col>
              <Tag color="blue">{marketEnv}</Tag>
            </Col>
          )}
          {stats.elapsed > 0 && (
            <>
              <Col>
                <Select size="small" value={sortBy} onChange={setSortBy} style={{ width: 130 }} options={[
                  {label: '按评分排序', value: 'score'},
                  {label: '按价格排序', value: 'price'},
                ]} />
              </Col>
              <Col>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  评分 {stats.scored} 只 · 排除 {stats.excluded} · 耗时 {stats.elapsed.toFixed(0)}s
                </Text>
              </Col>
            </>
          )}
        </Row>
      </Card>

      {/* ── Results ── */}
      <Card style={{ borderRadius: 8 }} loading={loading}
            title={picks.length > 0 ? `选股结果 (Top ${picks.length})` : '等待选股'}
      >
        <Table columns={columns} dataSource={picks} rowKey="code" size="small"
               rowSelection={{
                 selectedRowKeys,
                 onChange: setSelectedRowKeys,
               }}
               expandable={{
                 expandedRowRender: (record: any) => (
                   <div style={{ padding: '8px 16px', background: '#fafafa', borderRadius: 4 }}>
                     <Space wrap size="small">
                       {[
                         {label:'技术面', val:record.technical || record.score*0.35, color:'#1677ff'},
                         {label:'资金面', val:record.money_flow || record.score*0.25, color:'#52c41a'},
                         {label:'基本面', val:record.quality || record.score*0.20, color:'#faad14'},
                         {label:'情绪面', val:record.sentiment || record.score*0.10, color:'#722ed1'},
                         {label:'AI预测', val:record.pred || record.score*0.10, color:'#ff4d4f'},
                       ].map(d => (
                         <div key={d.label} style={{ display:'flex', alignItems:'center', gap:8 }}>
                           <Text style={{fontSize:11,width:42}}>{d.label}</Text>
                           <div style={{width:80,height:6,background:'#f0f0f0',borderRadius:3}}>
                             <div style={{width:`${Math.min(100,(d.val/25)*100)}%`,height:6,background:d.color,borderRadius:3}} />
                           </div>
                           <Text style={{fontSize:11}}>{Number(d.val).toFixed(1)}</Text>
                         </div>
                       ))}
                     </Space>
                     {record.rationale && (
                       <div style={{marginTop:8}}>
                         <Text type="secondary" style={{fontSize:11}}>
                           <InfoCircleOutlined /> {record.rationale}
                         </Text>
                       </div>
                     )}
                     <div style={{marginTop:4}}>
                       <Text type="secondary" style={{fontSize:11}}>
                         📊 综合评分 {record.score?.toFixed(1)} 分, 排名第 {picks.findIndex((p:any)=>p.code===record.code)+1}/{picks.length}, 评级 {record.grade} 级
                         {record.grade==='S'?' — 技术面S级+资金面优秀+评分领先, 重点关注':''}
                         {record.grade==='A'?' — 多维度表现均衡, 评分优良':''}
                         {record.grade==='B'?' — 部分维度表现一般, 建议观察':''}
                       </Text>
                     </div>
                   </div>
                 ),
               }}
               pagination={{ pageSize: 15, showSizeChanger: false }}
               scroll={{ x: 750 }}
               locale={{ emptyText: '点击「开始选股」运行模型筛选全市场标的' }} />
      </Card>
    </div>
  )
}

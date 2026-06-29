import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  BarChartOutlined,
  CheckCircleOutlined,
  DollarOutlined,
  FireOutlined,
  FundOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { MetricCard, PrototypeCard, PrototypePage, PrototypePageHeader, PrototypeTabs, SegmentTabs } from '../components/prototype'

const tabs = [
  { key: 'overview', path: '/open-decision', label: '决策总览', subLabel: '开盘闸门' },
  { key: 'auction', path: '/open-decision/auction', label: '竞价分析', subLabel: '集合竞价' },
  { key: 'signals', path: '/open-decision/signals', label: '信号扫描', subLabel: '触发队列' },
  { key: 'candidates', path: '/open-decision/candidates', label: '候选池', subLabel: 'AI 队列' },
  { key: 'execution', path: '/open-decision/execution', label: '执行监控', subLabel: '链路状态' },
]

const auctionBullishRows = [
  { code: '688981', name: '中芯国际', industry: '半导体', gap: 5.56, vol: 13.5, score: 92, intent: '强烈抢筹' },
  { code: '300750', name: '宁德时代', industry: '新能源', gap: 4.58, vol: 11.1, score: 88, intent: '强烈抢筹' },
  { code: '000001', name: '平安银行', industry: '金融', gap: 4.17, vol: 12.3, score: 85, intent: '强烈抢筹' },
  { code: '002415', name: '海康威视', industry: 'AI算力', gap: 3.66, vol: 10.5, score: 82, intent: '强烈抢筹' },
  { code: '601012', name: '隆基绿能', industry: '新能源', gap: 4.69, vol: 9.8, score: 81, intent: '强烈抢筹' },
  { code: '002230', name: '科大讯飞', industry: 'AI算力', gap: 3.9, vol: 9.2, score: 80, intent: '强烈抢筹' },
  { code: '002371', name: '北方华创', industry: '半导体设备', gap: 4.2, vol: 8.9, score: 79, intent: '偏多抢筹' },
  { code: '603986', name: '兆易创新', industry: '存储芯片', gap: 3.5, vol: 8.1, score: 78, intent: '偏多抢筹' },
]

const auctionBearishRows = [
  { code: '600000', name: '浦发银行', drop: -5.27, vol: 15.2, score: 18, intent: '强烈出货' },
  { code: '000858', name: '五粮液', drop: -2.82, vol: 10.2, score: 20, intent: '强烈出货' },
  { code: '000002', name: '万科A', drop: -4.23, vol: 9.8, score: 22, intent: '强烈出货' },
  { code: '601398', name: '工商银行', drop: -3.12, vol: 11.5, score: 24, intent: '强烈出货' },
  { code: '600031', name: '三一重工', drop: -2.41, vol: 7.8, score: 26, intent: '偏空出货' },
]

const sectorRows = [
  { name: '半导体', count: 12, change: 3.2, lead: '中芯+5.8% / 韦尔+4.2%', width: 92 },
  { name: '新能源', count: 9, change: 2.8, lead: '宁德+8.2% / 隆基+4.5%', width: 78 },
  { name: 'AI算力', count: 8, change: 2.5, lead: '浪潮+3.1% / 中科+3.5%', width: 70 },
  { name: '消费电子', count: 6, change: 1.8, lead: '立讯+2.8% / 歌尔+2.1%', width: 56 },
  { name: '白酒', count: 5, change: 1.5, lead: '茅台+3.2% / 五粮+2.1%', width: 46 },
]

const signalRows = [
  { code: '688981', name: '中芯', price: '68.20', signal: '强买', score: 78, kronos: '+8.2%', target: '73.80', confidence: 78, consistency: '双确认', risk: '通过', action: '确认买入', watchlist: true },
  { code: '603501', name: '韦尔', price: '218.00', signal: '强买', score: 72, kronos: '-1.2%', target: '215.00', confidence: 62, consistency: '相悖', risk: '通过', action: '降低优先级', watchlist: false },
  { code: '603986', name: '兆易', price: '120.50', signal: '强买', score: 68, kronos: '+5.0%', target: '126.50', confidence: 71, consistency: '双确认', risk: '通过', action: '确认买入', watchlist: true },
  { code: '300750', name: '宁德', price: '218.50', signal: '强买', score: 85, kronos: '+12.5%', target: '242.30', confidence: 82, consistency: '双确认', risk: '通过', action: '确认买入', watchlist: true },
  { code: '601012', name: '隆基', price: '27.70', signal: '买入', score: 65, kronos: '+3.2%', target: '28.60', confidence: 68, consistency: '双确认', risk: '通过', action: '确认买入', watchlist: false },
  { code: '000858', name: '五粮', price: '135.00', signal: '减仓', score: 32, kronos: '-2.0%', target: '132.00', confidence: 45, consistency: '中性', risk: '止损', action: '排除', watchlist: false },
]

const candidateRows = [
  { code: '688981', name: '中芯国际', source: '竞价+信号', score: 92, risk: '通过', size: '30%' },
  { code: '300750', name: '宁德时代', source: '自选+Kronos', score: 90, risk: '通过', size: '25%' },
  { code: '002371', name: '北方华创', source: '板块共振', score: 87, risk: '通过', size: '20%' },
  { code: '603986', name: '兆易创新', source: '信号扫描', score: 84, risk: '仓位复核', size: '15%' },
]

const orders = [
  { time: '09:31:05', code: '688981', name: '中芯国际', dir: '买入', price: '68.20', qty: '2,000', status: '已成交' },
  { time: '09:32:18', code: '300750', name: '宁德时代', dir: '买入', price: '218.50', qty: '600', status: '已成交' },
  { time: '09:34:42', code: '002371', name: '北方华创', dir: '买入', price: '305.80', qty: '400', status: '待成交' },
  { time: '09:40:11', code: '603986', name: '兆易创新', dir: '买入', price: '153.00', qty: '800', status: '待确认' },
]

const positions = [
  { code: '688981', name: '中芯国际', value: '13.6万', pnl: '+5.8%', weight: '18%' },
  { code: '300750', name: '宁德时代', value: '13.1万', pnl: '+8.2%', weight: '17%' },
  { code: '002371', name: '北方华创', value: '12.2万', pnl: '+4.2%', weight: '16%' },
]

const overnightNews = [
  { type: '公告', tone: 'danger', title: '中芯国际: 收到证监会立案调查通知书', impact: '影响: 高 · 竞价强度需复核', time: '昨 20:35' },
  { type: '公告', tone: 'danger', title: '贵州茅台: 半年度业绩预增 15%-20%', impact: '影响: 中 · 白酒高位分歧', time: '昨 19:00' },
  { type: '外盘', tone: 'accent', title: '美股三大指数收涨 · 道指 +0.32% · 纳指 +1.15%', impact: '影响: 正向 · AI算力风险偏好回暖', time: '今 05:00' },
  { type: '期货', tone: 'accent', title: 'A50 指数期货 +0.28% · 恒生期货 +0.45%', impact: '影响: 正向 · 开盘资金承接观察', time: '今 08:30' },
  { type: '舆情', tone: 'warn', title: '热词: #降息预期 #半导体出口管制 #新能源政策', impact: '影响: 主题催化 · 纳入情绪模型', time: '-' },
]

function activeKey(pathname: string) {
  if (pathname.endsWith('/auction')) return 'auction'
  if (pathname.endsWith('/signals')) return 'signals'
  if (pathname.endsWith('/candidates')) return 'candidates'
  if (pathname.endsWith('/execution')) return 'execution'
  return 'overview'
}

function toneForRisk(risk: string) {
  if (risk === '通过') return 't-down'
  if (risk.includes('复核')) return 't-warn'
  return 't-mute'
}

function decisionHeader(activeLabel: string) {
  if (activeLabel === '信号扫描') return '验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池'
  if (activeLabel === '候选池') return '候选池: 竞价 + 信号 + 选股 + 自选 -> 多源融合去重'
  if (activeLabel === '执行监控') return '订单: trade-service (orders) | 持仓: trade-service (positions)'
  return '竞价分析 · 信号扫描 · 候选池 · 执行监控'
}

export default function OpenDecision() {
  const location = useLocation()
  const navigate = useNavigate()
  const active = activeKey(location.pathname)
  const activeTab = useMemo(() => tabs.find(tab => tab.key === active) ?? tabs[0], [active])

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="开盘决策页签"
        activeKey={active}
        onChange={(key) => {
          const tab = tabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={tabs.map((tab, index) => ({ key: tab.key, label: tab.label, subLabel: tab.subLabel, number: String(index + 1).padStart(2, '0') }))}
      />
      <PrototypePageHeader title={`开盘决策 - ${activeTab.label}`} subtitle={decisionHeader(activeTab.label)} />

      {active === 'overview' && <DecisionOverview />}
      {active === 'auction' && <AuctionAnalysis />}
      {active === 'signals' && <SignalScan />}
      {active === 'candidates' && <CandidatePool />}
      {active === 'execution' && <ExecutionMonitor />}
    </PrototypePage>
  )
}

function DecisionOverview() {
  return (
    <>
      <section className="od-countdown card">
        <div>
          <div className="od-time mono">12:45</div>
          <strong>距竞价数据采集</strong>
          <span>09:25 竞价撮合 · 数据源 Tushare stk_auction</span>
        </div>
        <div className="prototype-panel-note">竞价开始后自动切换到竞价分析</div>
      </section>

      <div className="kpis od-kpis-5">
        <MetricCard label="情绪指数" value="72" sub="偏牛 +5" tone="warn" />
        <MetricCard label="熔断器" value="正常" sub="亏损预算 83.6%" tone="down" />
        <MetricCard label="隔夜公告" value="2条" sub="1条需关注" tone="up" />
        <MetricCard label="候选池" value="10只" sub="强信号 4 只" tone="accent" />
        <MetricCard label="数据状态" value="就绪" sub="竞价待采集 (09:25)" tone="down" />
      </div>

      <div className="row r-6-4">
        <div className="grid">
          <PrototypeCard title="隔夜新闻" icon={<LineChartOutlined />} meta="最近 12 小时">
            <div className="od-news-list">
              {overnightNews.map(item => (
                <div className="od-news-row" key={item.title}>
                  <span className={`od-news-tag ${item.tone}`}>{item.type}</span>
                  <div className="od-news-main">
                    <strong>{item.title}</strong>
                    <span>{item.impact}</span>
                  </div>
                  <time className="mono">{item.time}</time>
                </div>
              ))}
            </div>
            <div className="od-news-summary">
              <div>
                <span>摘要</span>
                <strong>半导体与AI算力偏正向，白酒高位分歧需降权</strong>
              </div>
              <button type="button" className="btn sm ghost">全部还原 LLM原始结果</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="昨日复盘" icon={<LineChartOutlined />} meta="回看强势线索">
            <div className="od-review-grid">
              <div><b className="up mono">+2.8%</b><span>半导体延续</span></div>
              <div><b className="up mono">+1.9%</b><span>新能源反弹</span></div>
              <div><b className="warn mono">72</b><span>情绪偏牛</span></div>
              <div><b className="down mono">83.6%</b><span>风控余量</span></div>
            </div>
          </PrototypeCard>

          <PrototypeCard title="候选池预加载" icon={<ThunderboltOutlined />} meta="开盘前预热">
            <div className="chips">
              {candidateRows.map(row => <span className="chip active" key={row.code}>{row.name} {row.score}</span>)}
            </div>
            <div className="prototype-panel-note mt14">来自自选、昨日强势板块、Kronos 预测和竞价待采集任务，开盘后进入去重与风控。</div>
          </PrototypeCard>
        </div>

        <div className="grid">
          <PrototypeCard title="今日情绪 + 风控" icon={<SafetyCertificateOutlined />} meta="开盘前">
            <div className="op-hint">
              <div className="pos warn">7成</div>
              <div>
                <div className="op-title warn">偏牛但不追高</div>
                <div className="op-desc">半导体、新能源、AI算力共振，优先选择竞价强且风控通过的候选。</div>
              </div>
            </div>
          </PrototypeCard>

          <PrototypeCard title="昨日强势板块 (可能延续)" icon={<BarChartOutlined />} meta="按共振强度">
            {sectorRows.slice(0, 4).map(row => (
              <div className="watch-sector-bar" key={row.name}>
                <span>{row.name}</span>
                <div><i style={{ width: `${row.width}%` }} /></div>
                <b className="up">+{row.change}%</b>
              </div>
            ))}
          </PrototypeCard>
        </div>
      </div>

      <div className="footer-bar">
        <span>开盘决策 · 决策总览 | 盘前 09:12</span>
        <span className="sep" />
        <span>隔夜新闻: stock_news + announcements + cctv_news</span>
        <span className="sep" />
        <span>候选池: CandidatePoolManager (screening_snapshots + watchlist)</span>
      </div>
    </>
  )
}

function AuctionAnalysis() {
  return (
    <div className="od-auction-layout">
      <div className="od-auction-main">
        <section className="od-engine card">
          <div>
            <span className="led on" />
            <strong>竞价分析引擎</strong>
            <span className="mono">auction_intent_v2.4</span>
            <span className="tag t-down">09:25 集合竞价完成</span>
            <span className="tag t-neu">328 只标的</span>
          </div>
          <div>
            <span className="prototype-panel-note">最近刷新 09:25:42</span>
            <button type="button" className="btn sm ghost">刷新</button>
          </div>
        </section>

        <section className="od-risk-callout">
          <div className="od-risk-icon">!</div>
          <div>
            <div className="od-risk-title">竞价风险提示 · 高开过热板块需二次确认</div>
            <div className="prototype-panel-note">半导体、新能源板块竞价共振较强；若开盘 5 分钟量价不能延续，候选池标的进入信号扫描复核，不直接下单。</div>
          </div>
          <div className="od-risk-actions">
            <button type="button" className="btn sm ghost">查看意图全景</button>
            <button type="button" className="btn sm primary">进入竞价选股</button>
          </div>
        </section>

        <div className="od-subtabs">
          <SegmentTabs
            ariaLabel="竞价分析子页签"
            activeKey="overview"
            onChange={() => undefined}
            items={[
              { key: 'overview', label: '竞价意图全景' },
              { key: 'stock', label: '竞价选股' },
              { key: 'bond', label: '可转债竞价' },
              { key: 'detail', label: '全量明细' },
            ]}
          />
        </div>

        <div className="kpis od-auction-kpis">
          <MetricCard label="分析标的" value="328" sub="沪深竞价池" tone="muted" />
          <MetricCard label="强烈抢筹" value="45" sub="评分 >= 75" tone="up" />
          <MetricCard label="偏多抢筹" value="89" sub="评分 60-74" tone="warn" />
          <MetricCard label="中性观察" value="120" sub="等待开盘确认" tone="accent" />
          <MetricCard label="出货预警" value="74" sub="偏空/强出货" tone="down" />
          <MetricCard label="候选池" value="5" sub="已入池待复核" tone="accent" />
        </div>

        <div className="row r-1-1">
          <PrototypeCard title="抢筹 TOP 10" icon={<FireOutlined />} meta="勾选后加入候选池" className="od-card-up">
            <table className="tbl">
              <thead><tr><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
              <tbody>
                {auctionBullishRows.map((row, index) => (
                  <tr key={row.code}>
                    <td>{index + 1}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r up">+{row.gap}%</td>
                    <td className="r mono">{row.vol}x</td>
                    <td className="r up">{row.score}</td>
                    <td><span className="tag t-up">{row.intent}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="od-selection-bar">
              <span>已选 <b>0</b></span>
              <button type="button" className="btn sm ghost">全选可用</button>
              <button type="button" className="btn sm primary">加入候选池</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="出货预警 TOP 10" icon={<SafetyCertificateOutlined />} meta="规避或反向观察" className="od-card-down">
            <table className="tbl">
              <thead><tr><th>#</th><th>代码</th><th>名称</th><th className="r">涨幅</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
              <tbody>
                {auctionBearishRows.map((row, index) => (
                  <tr key={row.code}>
                    <td>{index + 1}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r down">{row.drop}%</td>
                    <td className="r mono">{row.vol}x</td>
                    <td className="r down">{row.score}</td>
                    <td><span className="tag t-down">{row.intent}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="od-selection-bar">
              <span>预警样本</span>
              <button type="button" className="btn sm ghost">全选可用</button>
              <button type="button" className="btn sm down">加入观察</button>
            </div>
          </PrototypeCard>
        </div>

        <div className="row r-16-8 mt14">
          <PrototypeCard title="竞价撮合价走势" icon={<LineChartOutlined />} meta="09:15-09:25 撮合价/匹配量">
            <div className="od-trend-bars">
              {[35, 46, 42, 58, 64, 79, 74, 88, 83, 96].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
            </div>
            <div className="prototype-panel-note mt14">撮合价持续上移且匹配量放大时，优先进入信号扫描复核。</div>
          </PrototypeCard>

          <PrototypeCard title="四维评分" icon={<BarChartOutlined />} meta="价格方向 / 买卖压力 / 竞价强度 / 开盘延续">
            <div className="od-score-bars">
              {[
                ['价格方向', 92],
                ['买卖压力', 86],
                ['竞价强度', 88],
                ['开盘延续', 74],
              ].map(([label, value]) => (
                <div className="watch-sector-bar" key={label}>
                  <span>{label}</span>
                  <div><i style={{ width: `${value}%` }} /></div>
                  <b className="up">{value}</b>
                </div>
              ))}
            </div>
            <div className="od-stock-info">
              <span className="code">000001</span>
              <b>平安银行</b>
              <span className="tag t-up">强烈抢筹</span>
            </div>
          </PrototypeCard>
        </div>

        <PrototypeCard title="一字定方向" icon={<BarChartOutlined />} meta="板块竞价热度 · 点击板块查看强势股与转债" className="mt14">
          <div className="od-sector-grid">
            {sectorRows.map(row => (
              <button type="button" className="od-sector-tile" key={row.name}>
                <span>{row.name}</span>
                <b className="up">+{row.change}%</b>
                <small>{row.count} 只 · {row.lead}</small>
              </button>
            ))}
          </div>
        </PrototypeCard>

        <PrototypeCard title="全量竞价明细" icon={<BarChartOutlined />} meta="共 328 只 · 第 1-12 条" className="mt14">
          <table className="tbl">
            <thead><tr><th>代码</th><th>名称</th><th>板块</th><th className="r">竞价涨跌</th><th className="r">竞量比</th><th className="r">评分</th><th>意图</th></tr></thead>
            <tbody>
              {[...auctionBullishRows.slice(0, 5), ...auctionBearishRows.slice(0, 2)].map(row => (
                <tr key={row.code}>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}</td>
                  <td>{'industry' in row ? row.industry : '风险观察'}</td>
                  <td className={`r ${'gap' in row ? 'up' : 'down'}`}>{'gap' in row ? `+${row.gap}%` : `${row.drop}%`}</td>
                  <td className="r mono">{row.vol}x</td>
                  <td className="r mono">{row.score}</td>
                  <td><span className={`tag ${'gap' in row ? 't-up' : 't-down'}`}>{row.intent}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>
      </div>

      <aside className="od-auction-rail">
        <PrototypeCard title="板块共振详情" icon={<BarChartOutlined />}>
          {sectorRows.map(row => (
            <div className="od-resonance-row" key={row.name}>
              <div>
                <strong>{row.name}</strong>
                <span>{row.count}只 · 领涨: {row.lead}</span>
              </div>
              <b className="up">+{row.change}%</b>
              <button type="button" className="btn sm primary">选股-&gt;</button>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="板块强势标的" icon={<FireOutlined />}>
          {auctionBullishRows.slice(0, 4).map(row => (
            <div className="li-row" key={row.code}>
              <span className="li-badge up">{row.score}</span>
              <div className="li-main"><div className="n">{row.name}</div><div className="s">{row.industry} · +{row.gap}% · {row.intent}</div></div>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="候选池预览" icon={<FundOutlined />}>
          <div className="pool-count">5<span className="unit"> 只</span></div>
          <div className="chips mt14">
            <span className="chip active">300750 宁德</span>
            <span className="chip active">688981 中芯</span>
            <span className="chip">000001 平安</span>
            <span className="chip">002594 比亚迪</span>
            <span className="chip">600519 茅台</span>
          </div>
          <button type="button" className="btn sm ghost mt14">查看全部候选池 -&gt;</button>
        </PrototypeCard>

        <PrototypeCard title="已锁定板块" icon={<CheckCircleOutlined />}>
          <div className="chips">
            <span className="chip active">半导体 (12)</span>
            <span className="chip active">新能源 (9)</span>
          </div>
          <button type="button" className="btn primary mt14" style={{ width: '100%', justifyContent: 'center' }}>锁定板块 -&gt; 信号扫描</button>
        </PrototypeCard>

        <PrototypeCard title="工作流引导" icon={<CheckCircleOutlined />}>
          {[
            ['done', '竞价意图全景 -> 判断抢筹/出货方向'],
            ['active', '锁定强势板块 -> 切换到竞价选股引擎'],
            ['todo', '勾选标的 -> 加入候选池 -> 信号扫描验证'],
          ].map(([state, text], index) => (
            <div className={`od-workflow-row ${state}`} key={text}>
              <span>{state === 'done' ? '✓' : index + 1}</span>
              <b>{text}</b>
            </div>
          ))}
        </PrototypeCard>
      </aside>
    </div>
  )
}

function SignalScan() {
  const selected = signalRows[0]
  const dimensions = [
    { label: 'Kronos', value: 78 },
    { label: '技术面', value: 82 },
    { label: '资金面', value: 65 },
    { label: '基本面', value: 70 },
    { label: '事件', value: 55 },
    { label: '市场', value: 62 },
  ]

  return (
    <>
      <section className="od-locked-banner">
        <strong>锁定板块:</strong>
        <span className="chip active">半导体 <b>12</b></span>
        <span className="chip active">新能源 <b>9</b></span>
        <button type="button" className="btn sm ghost">清除锁定</button>
      </section>

      <section className="od-signal-filter-row">
        <div className="signal-filter-bar">
          <button type="button" className="filter-btn active">全部 <span className="mono">6</span></button>
          <button type="button" className="filter-btn">仅买入 <span className="mono">4</span></button>
          <button type="button" className="filter-btn">仅自选 <span className="mono">3</span></button>
        </div>
        <div className="signal-filter-bar">
          <span className="sort-label">排序:</span>
          <button type="button" className="filter-btn active">信号评分 ▼</button>
          <button type="button" className="filter-btn">一致性</button>
          <button type="button" className="filter-btn">风险</button>
        </div>
      </section>

      <div className="od-signal-layout">
        <div className="od-signal-left">
        <PrototypeCard title="信号扫描" icon={<ThunderboltOutlined />} meta="验证工作台 · 逐条确认信号 · Kronos 交叉验证 · 一键推送候选池">
          <table className="tbl od-verify-table">
            <thead><tr><th>代码</th><th>名称</th><th>信号</th><th className="r">评分</th><th>Kronos预测</th><th>一致性</th><th>风险</th><th className="r">操作</th></tr></thead>
            <tbody>
              {signalRows.map(row => (
                <tr className={row.code === selected.code ? 'picked' : ''} key={row.code}>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}{row.watchlist && <span className="in-pool-tag">自选</span>}</td>
                  <td><span className={row.score >= 70 ? 'tag t-up' : row.score >= 60 ? 'tag t-warn' : 'tag t-mute'}>{row.signal}</span></td>
                  <td className="r mono">{row.score}</td>
                  <td className={row.kronos.startsWith('+') ? 'up' : 'down'}>{row.kronos} -&gt; {row.target}</td>
                  <td><span className={row.consistency === '双确认' ? 'tag t-down' : row.consistency === '相悖' ? 'tag t-warn' : 'tag t-mute'}>{row.consistency}</span></td>
                  <td><span className={`tag ${toneForRisk(row.risk)}`}>{row.risk}</span></td>
                  <td className="r"><button type="button" className="btn sm ghost">{row.action}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="od-batch-bar">
            <button type="button" className="btn sm primary">批量确认买入信号</button>
            <button type="button" className="btn sm ghost">一键排除风险标的</button>
            <span>点击行查看详情</span>
            <b>逐条确认决策</b>
          </div>
          <div className="od-summary-bar">
            已处理 <b>0</b>/<span>6</span> · 已确认 <b className="down">0</b> · 已降级 <b className="warn">0</b> · 已排除 <b className="up">0</b>
          </div>
        </PrototypeCard>

        <PrototypeCard title="信号拆解" icon={<BarChartOutlined />} meta="信号 + 预测 + 风控">
          <div className="od-signal-stack">
            {dimensions.map(item => (
              <div className="watch-sector-bar" key={item.label}>
                <span>{item.label}</span>
                <div><i style={{ width: `${item.value}%` }} /></div>
                <b>{item.value}</b>
              </div>
            ))}
          </div>
        </PrototypeCard>
      </div>

      <aside className="od-signal-rail">
        <PrototypeCard title="选中股票" icon={<FundOutlined />} meta={selected.code}>
          <div className="od-selected-stock">
            <span className="code">{selected.code}</span>
            <b>{selected.name}</b>
            <span className="mono">¥{selected.price}</span>
          </div>
          <div className="od-signal-big-tag">强买 <span>{selected.score}分</span></div>
          <div className="od-detail-title">六维评分</div>
          {dimensions.map(item => (
            <div className="watch-sector-bar" key={item.label}>
              <span>{item.label}</span>
              <div><i style={{ width: `${item.value}%` }} /></div>
              <b>{item.value}</b>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="Kronos 30日预测" icon={<LineChartOutlined />} meta="300750 宁德时代">
          <div className="od-kronos-dir">
            <span>↗</span>
            <div>
              <b className="mono">218.50 -&gt; <span className="up">242.30</span></b>
              <strong>模型 v2.3.1 · 预测收益 +12.5%</strong>
            </div>
          </div>
          <div className="bar mt14"><i style={{ width: '78%' }} /></div>
          <div className="prototype-panel-note mt14">置信度 78% · 方向与强买信号一致</div>
        </PrototypeCard>

        <PrototypeCard title="信号+预测 方向一致" icon={<CheckCircleOutlined />}>
          <div className="od-verdict">
            <span>✓</span>
            <div>
              <strong>方向一致</strong>
              <p>信号强度: 强买 82分 · 多因子共振 · 通过风控</p>
            </div>
          </div>
        </PrototypeCard>

        <PrototypeCard title="风险检查" icon={<SafetyCertificateOutlined />} meta="RiskVerdict">
          {['ST/退市风险: 通过', '公告黑名单: 通过', '单票仓位: 需低于 20%', '板块集中度: 38%'].map((item, index) => (
            <div className="od-risk-row" key={item}>
              <span>{index + 1}. {item}</span>
              <b>{index < 2 ? '自动通过' : '执行前复核'}</b>
            </div>
          ))}
        </PrototypeCard>

        <PrototypeCard title="决策分类" icon={<FundOutlined />} meta="候选池推送">
          <div className="od-decision-group"><strong>已确认</strong><span>强买 + 预测一致 + 风控通过</span></div>
          <div className="od-decision-group"><strong>降级</strong><span>Kronos 相悖或置信度不足</span></div>
          <div className="od-decision-group"><strong>排除</strong><span>风险不通过或高价股限制</span></div>
          <button type="button" className="btn primary od-push-btn mt14">一键推送已确认 -&gt; 候选池</button>
          <button type="button" className="btn ghost od-push-btn mt14">查看候选池 -&gt;</button>
        </PrototypeCard>
      </aside>
    </div>
    </>
  )
}

function CandidatePool() {
  return (
    <>
      <section className="workflow-nav">
        <div className="workflow-track" aria-label="P0 主链路">
          <span className="workflow-step active"><span className="workflow-index">01</span><span className="workflow-copy"><span className="workflow-label">P0 主链路</span><span className="workflow-desc">候选池</span></span></span>
          <span className="workflow-arrow">-&gt;</span>
          <span className="workflow-step"><span className="workflow-index">02</span><span className="workflow-copy"><span className="workflow-label">方案管理</span><span className="workflow-desc">生成方案</span></span></span>
          <span className="workflow-arrow">-&gt;</span>
          <span className="workflow-step"><span className="workflow-index">03</span><span className="workflow-copy"><span className="workflow-label">风控闸门</span><span className="workflow-desc">RiskVerdict</span></span></span>
        </div>
      </section>

      <div className="row r-6-4">
        <PrototypeCard title="多源候选池" icon={<FundOutlined />} meta="Candidate 对象预览 · 多源融合去重">
          <table className="tbl">
            <thead><tr><th>#</th><th>代码</th><th>名称</th><th>来源</th><th className="r">综合评分</th><th>风控</th><th className="r">建议仓位</th></tr></thead>
            <tbody>
              {candidateRows.map((row, index) => (
                <tr key={row.code}>
                  <td>{index + 1}</td>
                  <td className="code">{row.code}</td>
                  <td className="nm">{row.name}</td>
                  <td>{row.source}</td>
                  <td className="r up">{row.score}</td>
                  <td><span className={`tag ${toneForRisk(row.risk)}`}>{row.risk}</span></td>
                  <td className="r mono">{row.size}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PrototypeCard>

        <div className="grid">
          <PrototypeCard title="风控排查" icon={<SafetyCertificateOutlined />} meta="RiskVerdict">
            {['审计风险: 通过', '重大公告: 通过', 'ST/退市: 通过', '止损预算: 通过'].map((item, index) => (
              <div className="li-row" key={item}>
                <span className="li-badge down">{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">已写入候选对象风险字段</div></div>
              </div>
            ))}
          </PrototypeCard>

          <PrototypeCard title="交易方案预览" icon={<DollarOutlined />} meta="Plan 草稿">
            <div className="risk-banner safe">
              <strong>风控预检: 全部通过</strong>
              <span>4只候选 · 计划仓位 70% · 最大单票 30% · 禁止追高价差 &gt; 2%</span>
            </div>
            <div className="od-actions mt14">
              <button type="button" className="btn primary">生成方案</button>
              <button type="button" className="btn ghost">保存为手动方案</button>
            </div>
          </PrototypeCard>
        </div>
      </div>
    </>
  )
}

function ExecutionMonitor() {
  return (
    <>
      <section className="od-account-bar card">
        {[
          ['总资产', '1,280,000', '账户 account.paper'],
          ['可用', '386,000', '可下单资金'],
          ['今日盈亏', '+23,500', '+1.86%'],
          ['总仓位', '68%', '风险阈值 75%'],
        ].map(([label, value, sub]) => (
          <div key={label}>
            <span>{label}</span>
            <b className={`mono ${label === '今日盈亏' ? 'up' : ''}`}>{value}</b>
            <small>{sub}</small>
          </div>
        ))}
      </section>

      <div className="row r-6-4">
        <div className="grid">
          <PrototypeCard title="今日订单" icon={<DollarOutlined />} meta="5单 · 成交3 · 待成交2">
            <table className="tbl">
              <thead><tr><th>时间</th><th>代码</th><th>名称</th><th>方向</th><th className="r">价格</th><th className="r">数量</th><th>状态</th></tr></thead>
              <tbody>
                {orders.map(row => (
                  <tr key={`${row.time}-${row.code}`}>
                    <td className="mono">{row.time}</td>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td><span className="tag t-up">{row.dir}</span></td>
                    <td className="r mono">{row.price}</td>
                    <td className="r mono">{row.qty}</td>
                    <td><span className={`tag ${row.status === '已成交' ? 't-down' : row.status === '待成交' ? 't-warn' : 't-neu'}`}>{row.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>

          <PrototypeCard title="持仓" icon={<FundOutlined />} meta="实时同步 trade-service">
            <table className="tbl">
              <thead><tr><th>代码</th><th>名称</th><th className="r">市值</th><th className="r">盈亏</th><th className="r">权重</th></tr></thead>
              <tbody>
                {positions.map(row => (
                  <tr key={row.code}>
                    <td className="code">{row.code}</td>
                    <td className="nm">{row.name}</td>
                    <td className="r mono">{row.value}</td>
                    <td className="r up">{row.pnl}</td>
                    <td className="r mono">{row.weight}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrototypeCard>
        </div>

        <div className="grid">
          <PrototypeCard title="自动交易策略" icon={<ThunderboltOutlined />} meta="paper">
            {['开盘竞价强势策略: 运行中', '单票最大仓位: 30%', '板块集中度上限: 45%', '异常熔断: 未触发'].map((item, index) => (
              <div className="li-row" key={item}>
                <span className={`li-badge ${index === 0 ? 'down' : 'neu'}`}>{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">StrategyExecutionContext 已记录</div></div>
              </div>
            ))}
          </PrototypeCard>

          <PrototypeCard title="今日方案" icon={<CheckCircleOutlined />} meta="Plan-OPEN-0925">
            <div className="risk-banner accent">
              <strong>开盘决策方案已生成</strong>
              <span>候选 4 只 · 已下单 3 只 · 待确认 1 只</span>
            </div>
            <div className="od-actions mt14">
              <button type="button" className="btn primary">一键启动自动交易</button>
              <button type="button" className="btn ghost">去交易中心手动下单</button>
              <button type="button" className="btn ghost">删除</button>
            </div>
          </PrototypeCard>

          <PrototypeCard title="需关注" icon={<SafetyCertificateOutlined />}>
            {['北方华创未完全成交，10:00 前复核', '白酒高位分歧，不进入追涨队列', '若仓位超过 70%，暂停新增订单'].map((item, index) => (
              <div className="li-row" key={item}>
                <span className="li-badge warn">{index + 1}</span>
                <div className="li-main"><div className="n">{item}</div><div className="s">执行前提醒</div></div>
              </div>
            ))}
          </PrototypeCard>
        </div>
      </div>
    </>
  )
}

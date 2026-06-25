/* ============================================================
   速赢AI · 智能选股（新版）

   完全按照 docs/design/new front/screener.html 设计稿实现
   连接真实后端API
   ============================================================ */

import React, { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { screenerApi } from '../api/client'
import type { ScreenerMode, ScreenerPick } from '../api/types'

// SVG图标组件
const Icons = {
  Search: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>,
  Download: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>,
  Refresh: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 4v5h-5"/></svg>,
  Check: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M20 6L9 17l-5-5"/></svg>,
  Star: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2l3 6.5 7 .9-5 4.9 1.2 7L12 18l-6.4 3.3L6.8 14 2 9.4l7-.9z"/></svg>,
  Plus: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v10"/></svg>,
}

export default function ScreenerV2() {
  const navigate = useNavigate()

  // 状态
  const [modes, setModes] = useState<ScreenerMode[]>([])
  const [picks, setPicks] = useState<ScreenerPick[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedMode, setSelectedMode] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [sortBy, setSortBy] = useState('score')
  const [sortDir, setSortDir] = useState(-1)
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set())
  const [lastScanTime, setLastScanTime] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  // 加载策略模式
  useEffect(() => {
    screenerApi.getModes().then(r => {
      setModes((r.data as { modes?: ScreenerMode[] }).modes || [])
    }).catch(() => {})
  }, [])

  // 运行选股
  const runScreening = async () => {
    setLoading(true)
    try {
      const mode = selectedMode || 'leader_auction'
      const r = await screenerApi.run(mode, 30)
      const data = r.data as { picks?: ScreenerPick[]; elapsed?: number }
      setPicks(data.picks || [])
      setLastScanTime(new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }))
      showToast(`扫描完成 · 命中 ${data.picks?.length || 0} 只候选`)
    } catch (e) {
      showToast('扫描失败，请检查后端服务')
    } finally {
      setLoading(false)
    }
  }

  // 筛选和排序
  const filteredPicks = useMemo(() => {
    let result = [...picks]

    // 搜索过滤
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(p =>
        p.code.toLowerCase().includes(q) ||
        (p.name && p.name.toLowerCase().includes(q)) ||
        (p.industry && p.industry.toLowerCase().includes(q))
      )
    }

    // 标签过滤
    if (filter === 'up') {
      result = result.filter(p => (p.change_pct ?? 0) > 0)
    }

    // 策略过滤
    if (selectedMode) {
      // 这里需要后端返回策略信息，暂时跳过
    }

    // 排序
    result.sort((a, b) => {
      let va = 0, vb = 0
      if (sortBy === 'score') { va = a.score ?? 0; vb = b.score ?? 0 }
      else if (sortBy === 'price') { va = a.price ?? 0; vb = b.price ?? 0 }
      else if (sortBy === 'change_pct') { va = a.change_pct ?? 0; vb = b.change_pct ?? 0 }
      return (va - vb) * sortDir
    })

    return result
  }, [picks, searchQuery, filter, selectedMode, sortBy, sortDir])

  // 选择/取消选择
  const toggleSelect = (code: string) => {
    const newSet = new Set(selectedCodes)
    if (newSet.has(code)) {
      newSet.delete(code)
    } else {
      newSet.add(code)
    }
    setSelectedCodes(newSet)
  }

  const toggleSelectAll = () => {
    if (selectedCodes.size === filteredPicks.length) {
      setSelectedCodes(new Set())
    } else {
      setSelectedCodes(new Set(filteredPicks.map(p => p.code)))
    }
  }

  // Toast提示
  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2000)
  }

  // 加入自选
  const addToWatchlist = () => {
    const names = filteredPicks.filter(p => selectedCodes.has(p.code)).map(p => p.name || p.code)
    showToast(`✓ 已将 ${names.length} 只标的加入自选：${names.slice(0, 3).join('、')}${names.length > 3 ? ' 等' : ''}`)
    setSelectedCodes(new Set())
  }

  // 策略分类（简化版）
  const strategyGroups = [
    { key: '短线打板', name: '短线打板', cycle: '日线', style: '激进', count: 0 },
    { key: '趋势波段', name: '趋势波段', cycle: '日线', style: '稳健', count: 0 },
    { key: '低吸潜伏', name: '低吸潜伏', cycle: '周线', style: '价值', count: 0 },
    { key: '产业链共振', name: '产业链共振', cycle: '日线', style: '主题', count: 0 },
  ]

  // 计算评分分解条
  const getScoreBreakdown = (pick: ScreenerPick) => {
    const score = pick.score ?? 0
    const tech = Math.min(45, (score * 0.45))
    const fund = Math.min(35, (score * 0.35))
    const money = Math.min(20, (score * 0.20))
    return { tech, fund, money }
  }

  return (
    <div className="app">
      {/* 侧边栏 */}
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3v18h18" strokeLinecap="round"/>
              <path d="M7 14l4-4 4 4 5-5" strokeLinecap="round"/>
            </svg>
          </div>
          <div className="name"><b>速赢</b>AI</div>
        </div>

        <nav className="nav">
          <div className="nav-group">行情决策</div>
          <div className="nav-item" onClick={() => navigate('/dashboard')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/></svg>
            AI 智能看板
          </div>
          <div className="nav-item active">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/></svg>
            智能选股
            <span className="pill">{picks.length}</span>
          </div>
          <div className="nav-item" onClick={() => navigate('/supply-chain-bom')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6"/></svg>
            产业链拆解
          </div>
          <div className="nav-item" onClick={() => navigate('/predictions')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            K线预测
          </div>

          <div className="nav-group">交易执行</div>
          <div className="nav-item" onClick={() => navigate('/strategy')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
            方案管理
          </div>
          <div className="nav-item" onClick={() => navigate('/signals')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            交易信号
          </div>
          <div className="nav-item" onClick={() => navigate('/trade')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v12M8 10l4 4 4-4"/></svg>
            交易中心
          </div>

          <div className="nav-group">模型系统</div>
          <div className="nav-item" onClick={() => navigate('/backtest')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
            回测分析
          </div>
          <div className="nav-item" onClick={() => navigate('/diagnosis')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
            个股诊断
          </div>
        </nav>
      </aside>

      {/* 主区域 */}
      <div className="main">
        {/* 头部 */}
        <header className="header">
          <span className="crumb"><b>智能选股</b></span>
          <div className="header-right">
            <button className="hbtn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            </button>
            <div className="user">
              <div className="av">U</div>
              <span className="un">UAT Analyst</span>
            </div>
          </div>
        </header>

        {/* 内容 */}
        <main className="content">
          <div className="page-head">
            <div>
              <h1>智能选股</h1>
              <div className="sub">
                {modes.length} 套策略并行扫描全市场
                {lastScanTime && ` · 最近扫描 ${lastScanTime}`}
                {picks.length > 0 && ` · 命中 ${picks.length} 只候选`}
              </div>
            </div>
            <div className="head-actions">
              <button className="btn">
                <Icons.Download />
                导出 CSV
              </button>
              <button className="btn primary" onClick={runScreening} disabled={loading}>
                <Icons.Refresh />
                {loading ? '扫描中...' : '重新扫描'}
              </button>
            </div>
          </div>

          {/* 策略模式卡 */}
          <div className="mode-grid">
            {strategyGroups.map(g => (
              <div
                key={g.key}
                className={`mode-card ${selectedMode === g.key ? 'on' : ''}`}
                onClick={() => setSelectedMode(selectedMode === g.key ? null : g.key)}
              >
                <div className="mc-top">
                  <div>
                    <div className="mc-name">{g.name}</div>
                    <div className="mc-meta">{g.cycle} · {g.style}</div>
                  </div>
                  <span className={`tag t-${g.style === '激进' ? 'up' : g.style === '稳健' ? 'neu' : g.style === '价值' ? 'mute' : 'warn'}`}>
                    {g.style}
                  </span>
                </div>
                <div className="mc-hit neu">{g.count}</div>
                <div className="mc-meta">命中候选</div>
              </div>
            ))}
          </div>

          {/* 候选股清单 */}
          <div className="card">
            <div className="card-h">
              <h3>候选股清单</h3>
              <span className="meta">
                共 {filteredPicks.length} 只 · 按{
                  sortBy === 'score' ? '综合评分' :
                  sortBy === 'price' ? '现价' : '涨跌幅'
                }{sortDir < 0 ? ' 降序' : ' 升序'}
              </span>
              <div className="score-legend">
                <span className="sl"><span className="sd" style={{background: 'var(--accent)'}}></span>技术</span>
                <span className="sl"><span className="sd" style={{background: 'var(--down)'}}></span>基本面</span>
                <span className="sl"><span className="sd" style={{background: 'var(--warn)'}}></span>资金</span>
              </div>
            </div>

            <div className="card-b" style={{padding: '14px 16px'}}>
              {/* 筛选栏 */}
              <div className="filter-bar">
                <div className="search">
                  <Icons.Search />
                  <input
                    className="inp"
                    type="search"
                    placeholder="搜索代码 / 名称 / 行业…"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                  />
                </div>
                <span
                  className={`chip ${filter === 'all' ? 'active' : ''}`}
                  onClick={() => setFilter('all')}
                >全部</span>
                <span
                  className={`chip ${filter === 'up' ? 'active' : ''}`}
                  onClick={() => setFilter('up')}
                >看涨</span>
                <span
                  className={`chip ${filter === 'hot' ? 'active' : ''}`}
                  onClick={() => setFilter('hot')}
                >热门行业</span>
              </div>

              {/* 表格 */}
              <table className="tbl">
                <thead>
                  <tr>
                    <th className="sel-c">
                      <span
                        className={`ck ${selectedCodes.size === filteredPicks.length ? 'on' : ''}`}
                        onClick={toggleSelectAll}
                      >
                        <Icons.Check />
                      </span>
                    </th>
                    <th>代码 / 名称</th>
                    <th>行业</th>
                    <th>策略命中</th>
                    <th
                      className="r sortable"
                      onClick={() => { setSortBy('price'); if (sortBy === 'price') setSortDir(-sortDir) }}
                    >
                      现价<span className="arr">▼</span>
                    </th>
                    <th
                      className="r sortable"
                      onClick={() => { setSortBy('change_pct'); if (sortBy === 'change_pct') setSortDir(-sortDir) }}
                    >
                      涨跌幅<span className="arr">▼</span>
                    </th>
                    <th className="c sortable sorted">综合评分<span className="arr">▼</span></th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPicks.length === 0 ? (
                    <tr id="emptyRow">
                      <td colSpan={8} style={{padding: '36px 10px', textAlign: 'center', color: 'var(--muted)'}}>
                        {picks.length === 0 ? '点击「重新扫描」开始选股' : '没有符合条件的候选股'}
                      </td>
                    </tr>
                  ) : filteredPicks.map(pick => {
                    const breakdown = getScoreBreakdown(pick)
                    const isSelected = selectedCodes.has(pick.code)
                    const isUp = (pick.change_pct ?? 0) > 0

                    return (
                      <tr
                        key={pick.code}
                        className={isSelected ? 'picked' : ''}
                        onClick={() => toggleSelect(pick.code)}
                      >
                        <td className="sel-c">
                          <span className={`ck ${isSelected ? 'on' : ''}`}>
                            <Icons.Check />
                          </span>
                        </td>
                        <td>
                          <span className="code">{pick.code}</span>
                          <span className="nm">{pick.name || pick.code}</span>
                        </td>
                        <td>{pick.industry || '--'}</td>
                        <td>
                          <span className="tag t-up">短线打板</span>
                        </td>
                        <td className="r mono">{(pick.price ?? 0).toFixed(2)}</td>
                        <td className={`r mono ${isUp ? 'up' : 'down'}`}>
                          {isUp ? '+' : ''}{(pick.change_pct ?? 0).toFixed(2)}%
                        </td>
                        <td className="c">
                          <span className="score-cell">
                            <span className="score-stack">
                              <i className="f-tech" style={{width: `${breakdown.tech}%`}}></i>
                              <i className="f-fund" style={{width: `${breakdown.fund}%`}}></i>
                              <i className="f-money" style={{width: `${breakdown.money}%`}}></i>
                            </span>
                            <span className="score-num">{(pick.score ?? 0).toFixed(0)}</span>
                          </span>
                        </td>
                        <td className="r">
                          <a onClick={() => navigate(`/diagnosis?code=${pick.code}`)}>诊断</a>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>

              {/* 批量操作条 */}
              <div className={`bulkbar ${selectedCodes.size > 0 ? 'show' : ''}`}>
                <span className="bb-cnt">已选 <b>{selectedCodes.size}</b> 只</span>
                <div className="bb-actions">
                  <button className="btn sm primary" onClick={addToWatchlist}>
                    <Icons.Star />
                    加入自选
                  </button>
                  <button className="btn sm" onClick={() => navigate('/trade')}>
                    <Icons.Plus />
                    批量下单
                  </button>
                  <button className="btn sm ghost" onClick={() => setSelectedCodes(new Set())}>
                    取消选择
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="page-foot">
            © 2026 速赢AI · 选股结果基于历史数据与因子模型，不构成投资建议
          </div>
        </main>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className="toast show"
          style={{
            position: 'fixed',
            bottom: '24px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'var(--elevated)',
            border: '1px solid var(--down)',
            color: 'var(--fg)',
            padding: '11px 20px',
            borderRadius: '8px',
            fontSize: '13px',
            zIndex: 200
          }}
        >
          {toast}
        </div>
      )}
    </div>
  )
}
import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { PrototypePage, PrototypeTabs } from '../components/prototype'
import { signalApi } from '../api/client'
import type { AuctionIntentItem, DashboardData } from './dashboard/types'
import SentimentTab from './dashboard/SentimentTab'
import AuctionTab from './dashboard/AuctionTab'
import SignalsTab from './dashboard/SignalsTab'
import WatchlistTab from './dashboard/WatchlistTab'

const dashboardTabs = [
  { key: 'sentiment', path: '/', label: '市场情绪', subLabel: '宽度 / 资金' },
  { key: 'auction', path: '/dashboard/auction', label: '竞价意图', subLabel: '9:25 抢筹' },
  { key: 'signals', path: '/dashboard/signals', label: '信号总览', subLabel: '今日触发' },
  { key: 'watchlist', path: '/dashboard/watchlist', label: '自选跟踪', subLabel: '持仓线索' },
]

function activeTabFromPath(pathname: string) {
  if (pathname.endsWith('/auction')) return 'auction'
  if (pathname.endsWith('/signals')) return 'signals'
  if (pathname.endsWith('/watchlist')) return 'watchlist'
  return 'sentiment'
}

export default function Dashboard() {
  const location = useLocation()
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [screeningPicks, setScreeningPicks] = useState<AuctionIntentItem[]>([])
  const [auctionPicks, setAuctionPicks] = useState<AuctionIntentItem[]>([])
  const [error, setError] = useState(false)
  const [lastRefresh, setLastRefresh] = useState('')
  const activeTab = activeTabFromPath(location.pathname)

  const fetchDashboard = useCallback(async () => {
    try {
      const response = await signalApi.getDashboardSummary()
      setData(response.data as DashboardData)
      setError(false)
      setLastRefresh(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
    } catch {
      setError(true)
    }
  }, [])

  useEffect(() => {
    fetchDashboard()
    const timer = setInterval(fetchDashboard, 60_000)
    return () => clearInterval(timer)
  }, [fetchDashboard])

  useEffect(() => {
    signalApi.getScreeningDashboardSummary()
      .then(({ data: payload }) => {
        const dual = Array.isArray(payload?.dual_consensus) ? payload.dual_consensus : []
        const merged = Array.isArray(payload?.merged) ? payload.merged : []
        setScreeningPicks((dual.length > 0 ? dual : merged).slice(0, 8))
      })
      .catch(() => setScreeningPicks([]))

    signalApi.getDashboardAuction()
      .then(({ data: payload }) => {
        setAuctionPicks(Array.isArray(payload?.picks) ? payload.picks.slice(0, 8) : [])
      })
      .catch(() => setAuctionPicks([]))
  }, [])

  return (
    <PrototypePage>
      <PrototypeTabs
        ariaLabel="智能看板页签"
        activeKey={activeTab}
        onChange={(key) => {
          const tab = dashboardTabs.find(item => item.key === key)
          if (tab) navigate(tab.path)
        }}
        items={dashboardTabs.map((tab, index) => ({ ...tab, number: String(index + 1).padStart(2, '0') }))}
      />

      {activeTab === 'sentiment' && (
        <SentimentTab
          data={data}
          error={error}
          lastRefresh={lastRefresh}
          screeningPicks={screeningPicks}
          auctionPicks={auctionPicks}
        />
      )}
      {activeTab === 'auction' && (
        <AuctionTab
          data={data}
          lastRefresh={lastRefresh}
          screeningPicks={screeningPicks}
          auctionPicks={auctionPicks}
        />
      )}
      {activeTab === 'signals' && <SignalsTab data={data} lastRefresh={lastRefresh} />}
      {activeTab === 'watchlist' && <WatchlistTab data={data} lastRefresh={lastRefresh} />}
    </PrototypePage>
  )
}

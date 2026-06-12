import { useState, useEffect, useCallback, useRef } from 'react'
import { message } from 'antd'
import { liveTradeApi } from '../api/liveTrade'

export type TradeMode = 'paper' | 'live'
export type BrokerStatus = 'connected' | 'disconnected' | 'connecting' | 'error'

export interface RiskConfig {
  large_order_threshold: number
  max_position_pct?: number
  max_single_amount?: number
}

export interface CircuitBreakerState {
  account_id: string
  status: 'NORMAL' | 'TRIGGERED'
  triggered_at: string | null
  daily_pnl: number
  initial_capital: number
  daily_loss_pct: number
  threshold_pct: number
  cooldown_minutes: number
  can_trade: boolean
  date: string
}

export interface PreCheckResult {
  passed: boolean
  requires_confirmation?: boolean
  confirm_reason?: string
  checks: Array<{
    rule: string
    level: string  // 'pass' | 'warn' | 'reject'
    message: string
    detail?: Record<string, any>
  }>
}

export interface OrderParams {
  code: string
  direction: string
  price: number
  volume: number
}

export interface UseLiveTradeReturn {
  mode: TradeMode
  setMode: (m: TradeMode) => void
  brokerStatus: BrokerStatus
  riskConfig: RiskConfig | null
  circuitBreaker: CircuitBreakerState | null
  apiPrefix: string
  connectBroker: () => Promise<void>
  placeOrder: (
    params: OrderParams,
    callbacks: {
      onPreCheckFailed?: (result: PreCheckResult) => void
      onLargeOrderConfirm?: (params: OrderParams) => Promise<boolean>
    }
  ) => Promise<{ success: boolean; data?: any; error?: string }>
}

export function useLiveTrade(): UseLiveTradeReturn {
  const [mode, setModeState] = useState<TradeMode>(() => {
    return (localStorage.getItem('trade_mode') as TradeMode) || 'paper'
  })
  const [brokerStatus, setBrokerStatus] = useState<BrokerStatus>('disconnected')
  const [riskConfig, setRiskConfig] = useState<RiskConfig | null>(null)
  const [circuitBreaker, setCircuitBreaker] = useState<CircuitBreakerState | null>(null)

  const prevBrokerStatus = useRef<BrokerStatus>('disconnected')

  const apiPrefix = '/api/v1/trade'  // paper/live mode controlled by query param ?mode=

  // Persist mode
  const setMode = useCallback((m: TradeMode) => {
    setModeState(m)
    localStorage.setItem('trade_mode', m)
    if (m === 'live') {
      // Reset broker status when switching to live
      setBrokerStatus('disconnected')
    }
  }, [])

  // Fetch risk config on mount
  useEffect(() => {
    liveTradeApi.getRiskConfig()
      .then(r => setRiskConfig(r.data))
      .catch(() => {
        // No fallback — threshold only from backend to avoid config inconsistency
        setRiskConfig(null)
      })
  }, [])

  // Poll broker status (live mode only, every 10s)
  useEffect(() => {
    if (mode !== 'live') return

    const pollBroker = () => {
      liveTradeApi.getBrokerStatus()
        .then(r => {
          const status = r.data?.status || 'disconnected'
          setBrokerStatus(status)
          if (prevBrokerStatus.current !== 'disconnected' && status === 'disconnected') {
            message.warning('券商连接已断开')
          }
          if (prevBrokerStatus.current !== 'connected' && status === 'connected') {
            message.success('券商已连接')
          }
          prevBrokerStatus.current = status
        })
        .catch(() => {
          setBrokerStatus('disconnected')
        })
    }

    pollBroker()
    const timer = setInterval(pollBroker, 10000)
    return () => clearInterval(timer)
  }, [mode])

  // Poll circuit breaker status (live mode only, every 30s)
  useEffect(() => {
    if (mode !== 'live') return

    const pollBreaker = () => {
      liveTradeApi.getCircuitBreakerStatus()
        .then(r => {
          const breakers = r.data?.breakers || []
          setCircuitBreaker(breakers[0] || null)
        })
        .catch(() => setCircuitBreaker(null))
    }

    pollBreaker()
    const timer = setInterval(pollBreaker, 30000)
    return () => clearInterval(timer)
  }, [mode])

  // Connect to broker
  const connectBroker = useCallback(async () => {
    setBrokerStatus('connecting')
    try {
      const r = await liveTradeApi.connectBroker()
      setBrokerStatus(r.data?.status || 'connected')
      if (r.data?.status === 'connected') {
        message.success('券商连接成功')
      }
    } catch {
      setBrokerStatus('error')
      message.error('券商连接失败，请检查网络或联系管理员')
    }
  }, [])

  // Place order with full risk control flow
  const placeOrder = useCallback(async (
    params: OrderParams,
    callbacks: {
      onPreCheckFailed?: (result: PreCheckResult) => void
      onLargeOrderConfirm?: (params: OrderParams) => Promise<boolean>
    },
  ): Promise<{ success: boolean; data?: any; error?: string }> => {
    // Step 1: Risk pre-check (live mode only)
    if (mode === 'live') {
      try {
        const checkResult = await liveTradeApi.preCheck(params)
        const preCheck: PreCheckResult = checkResult.data

        if (!preCheck.passed) {
          callbacks.onPreCheckFailed?.(preCheck)
          return { success: false, error: '风控检查未通过' }
        }

        // Show non-blocking warnings (level === 'warn')
        const warnings = preCheck.checks?.filter(c => c.level === 'warn') || []
        warnings.forEach(w => {
          message.warning(w.message)
        })
      } catch (err: any) {
        const errMsg = err?.response?.data?.detail || '风控检查服务异常'
        message.error(errMsg)
        return { success: false, error: errMsg }
      }
    }

    // Step 2: Large order check (live mode only, only when backend config loaded)
    const largeOrderThreshold = riskConfig?.large_order_threshold
    if (mode === 'live' && largeOrderThreshold != null) {
      const estimatedAmount = params.price > 0
        ? params.price * params.volume
        : 0 // Market order - cannot estimate, always confirm

      if (estimatedAmount === 0 || estimatedAmount >= largeOrderThreshold) {
        const confirmed = await callbacks.onLargeOrderConfirm?.(params)
        if (!confirmed) {
          return { success: false, error: '用户取消大额交易' }
        }
      }
    }

    // Step 3: Submit order
    try {
      if (mode === 'paper') {
        const r = await fetch(`${apiPrefix}/order`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code: params.code,
            direction: params.direction,
            price: params.price,
            volume: params.volume,
          }),
        })
        const data = await r.json()
        if (r.ok) {
          message.success(data.message || '下单成功')
          return { success: true, data }
        } else {
          const errMsg = data.detail || '下单失败'
          message.error(errMsg)
          return { success: false, error: errMsg }
        }
      } else {
        const r = await liveTradeApi.placeOrder(params.code, params.direction, params.volume, params.price)
        const data = r.data
        message.success(data.message || '下单成功')
        return { success: true, data }
      }
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail || '交易服务未连接'
      message.error(errMsg)
      return { success: false, error: errMsg }
    }
  }, [mode, riskConfig])

  return {
    mode,
    setMode,
    brokerStatus,
    riskConfig,
    circuitBreaker,
    apiPrefix,
    connectBroker,
    placeOrder,
  }
}

import { useState, useEffect, useCallback, useRef } from 'react'
import { message } from 'antd'
import axios from 'axios'
import { tradeApi } from '../api/domains/trade/api'
import type { BrokerConnectRequest, PlaceOrderRequest } from '../api/types'

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
  direction: PlaceOrderRequest['direction']
  price: number
  volume: number
  trade_mode?: TradeMode
  decision_context_id?: string
  candidate_id?: string
  plan_id?: string
}

export interface UseLiveTradeReturn {
  mode: TradeMode
  setMode: (m: TradeMode) => void
  brokerStatus: BrokerStatus
  riskConfig: RiskConfig | null
  circuitBreaker: CircuitBreakerState | null
  apiPrefix: string
  connectBroker: (config: BrokerConnectRequest) => Promise<void>
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
    // P2-01: whitelist-validate the stored value instead of blindly casting —
    // a tampered localStorage ('foobar') must not pollute state.
    const stored = typeof window !== 'undefined' ? localStorage.getItem('trade_mode') : null
    return stored === 'live' || stored === 'paper' ? stored : 'paper'
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
    tradeApi.getRiskConfig()
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
      tradeApi.getBrokerStatus()
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
      tradeApi.getCircuitBreakerStatus()
        .then(r => {
          const breakers = r.data?.breakers || []
          setCircuitBreaker(breakers[0] || null)
        })
        .catch((err: unknown) => {
          // P0-04: error triage — do NOT silently clear breaker state.
          // - 404 / explicit "no breaker configured" response → legitimate null (no breaker)
          // - network error / 401 / 403 / 5xx → RETAIN last known state so the risk
          //   warning stays visible; a transient blip must not mask a triggered breaker.
          if (axios.isAxiosError(err) && err.response?.status === 404) {
            setCircuitBreaker(null)
            return
          }
          // Network/server error: keep previous breaker state, log for debugging.
          // Intentionally no message popup — this polls every 30s and would spam users.
          // eslint-disable-next-line no-console
          console.warn('[useLiveTrade] circuit breaker poll failed, retaining last state', err)
        })
    }

    pollBreaker()
    const timer = setInterval(pollBreaker, 30000)
    return () => clearInterval(timer)
  }, [mode])

  // Connect to broker
  const connectBroker = useCallback(async (config: BrokerConnectRequest) => {
    setBrokerStatus('connecting')
    try {
      const r = await tradeApi.connectBroker(config)
      setBrokerStatus(r.data?.status || 'connected')
      if (r.data?.status === 'connected') {
        message.success(config.environment === 'sandbox' ? 'QMT Sandbox 已连接' : '券商连接成功')
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
    const effectiveMode = params.trade_mode || mode

    // Step 1: Risk pre-check for both paper and live modes. The backend owns the
    // same verdict contract in both paths, so the UI can present one risk gate.
    try {
      const checkResult = await tradeApi.preCheck({ ...params, trade_mode: effectiveMode })
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
      const status = err?.response?.status
      if (effectiveMode === 'paper' && (status === 404 || status === 405)) {
        message.warning('独立预检接口不可用，将由下单接口执行风控')
      } else {
      const detail = err?.response?.data?.detail
      const errMsg = typeof detail === 'string'
        ? detail
        : detail?.detail || '风控检查服务异常'
      message.error(errMsg)
      return { success: false, error: errMsg }
      }
    }

    // Step 2: Large order confirmation (only when backend config loaded;
    // server also enforces this via 409 CONFIRMATION_REQUIRED)
    const largeOrderThreshold = riskConfig?.large_order_threshold
    let largeOrderConfirmed = false
    if (largeOrderThreshold != null) {
      const estimatedAmount = params.price > 0
        ? params.price * params.volume
        : 0 // Market order - cannot estimate, always confirm

      if (estimatedAmount === 0 || estimatedAmount >= largeOrderThreshold) {
        const confirmed = await callbacks.onLargeOrderConfirm?.(params)
        if (!confirmed) {
          return { success: false, error: '用户取消大额交易' }
        }
        largeOrderConfirmed = true
      }
    }

    // Step 3: Submit order
    // P0-01: paper/live unified through the axios-wrapped tradeApi.placeOrder.
    // Previously the paper branch used a raw fetch() that bypassed client.ts — no
    // Authorization header, no 401 refresh, no withCredentials cookie. Now both modes
    // go through the single axios instance so the auth contract is consistent. The
    // backend decides paper vs live from its own account/broker config.
    try {
      const r = await tradeApi.placeOrder({ ...params, trade_mode: effectiveMode, confirmed: largeOrderConfirmed })
      const data = r.data
      message.success(data.message || '下单成功')
      return { success: true, data }
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      const errMsg = typeof detail === 'string'
        ? detail
        : detail?.detail || '交易服务未连接'
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

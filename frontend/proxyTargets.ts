type Env = Record<string, string | undefined>

export interface ProxyTargets {
  auth: string
  screener: string
  prediction: string
  strategy: string
  signal: string
  alert: string
  trade: string
  backtest: string
  training: string
  diagnosis: string
  gateway: string
}

export function resolveProxyTargets(env: Env): ProxyTargets {
  return {
    auth: env.VITE_AUTH_SERVICE_URL || 'http://localhost:9001',
    screener: env.VITE_SCREENER_SERVICE_URL || 'http://localhost:8001',
    prediction: env.VITE_PREDICTION_SERVICE_URL || 'http://localhost:8002',
    strategy: env.VITE_STRATEGY_SERVICE_URL || 'http://localhost:8003',
    signal: env.VITE_SIGNAL_SERVICE_URL || 'http://localhost:8004',
    alert: env.VITE_ALERT_SERVICE_URL || 'http://localhost:8005',
    trade: env.VITE_TRADE_SERVICE_URL || 'http://localhost:8006',
    backtest: env.VITE_BACKTEST_SERVICE_URL || 'http://localhost:8007',
    training: env.VITE_TRAINING_SERVICE_URL || 'http://localhost:8008',
    diagnosis: env.VITE_DIAGNOSIS_SERVICE_URL || 'http://localhost:8009',
    gateway: env.VITE_GATEWAY_SERVICE_URL || 'http://localhost:8080',
  }
}

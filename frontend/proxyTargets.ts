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

// 是否有任一 VITE_* env 覆盖。无覆盖时走 89xx 默认（=suying-uat 远程栈）。
function hasAnyViteOverride(env: Env): boolean {
  return Boolean(
    env.VITE_AUTH_SERVICE_URL ||
      env.VITE_SCREENER_SERVICE_URL ||
      env.VITE_PREDICTION_SERVICE_URL ||
      env.VITE_STRATEGY_SERVICE_URL ||
      env.VITE_SIGNAL_SERVICE_URL ||
      env.VITE_ALERT_SERVICE_URL ||
      env.VITE_TRADE_SERVICE_URL ||
      env.VITE_BACKTEST_SERVICE_URL ||
      env.VITE_TRAINING_SERVICE_URL ||
      env.VITE_DIAGNOSIS_SERVICE_URL ||
      env.VITE_GATEWAY_SERVICE_URL,
  )
}

export function resolveProxyTargets(env: Env): ProxyTargets {
  // 默认值指向 suying-uat 栈（PL 批准 2026-07-03）。原 180xx 指向已断链的 uat-adr013
  // 栈（无 postgres），是"前端无法使用"根因之一。suying-uat 端口 scheme = 主服务端口
  // 映射 +900（auth 8900 / screener 8901 / … / diagnosis 8909 / gateway 8980）。
  // strategy(8903) / training(8908) 当前 suying-uat 未起容器，但保持 89xx scheme 一致，
  // 容器起后即生效；行情决策板块不依赖这两个服务。单服务仍可用 VITE_* env 覆盖。
  //
  // 防护（W-2）：89xx = suying-uat 远程栈。若本机另起 180xx dev 栈但忘记设 VITE_* env，
  // 前端会静默连 UAT 而非本地 dev 栈——dev 模式下显式 warn，避免误连。
  if (import.meta.env.DEV && !hasAnyViteOverride(env)) {
    // eslint-disable-next-line no-console
    console.warn(
      '[proxyTargets] 默认连 suying-uat 远程栈（89xx）。若本机另起 dev 栈，请设 VITE_*_SERVICE_URL 指向本地端口。',
    )
  }
  return {
    auth: env.VITE_AUTH_SERVICE_URL || 'http://127.0.0.1:8900',
    screener: env.VITE_SCREENER_SERVICE_URL || 'http://127.0.0.1:8901',
    prediction: env.VITE_PREDICTION_SERVICE_URL || 'http://127.0.0.1:8902',
    strategy: env.VITE_STRATEGY_SERVICE_URL || 'http://127.0.0.1:8903',
    signal: env.VITE_SIGNAL_SERVICE_URL || 'http://127.0.0.1:8904',
    alert: env.VITE_ALERT_SERVICE_URL || 'http://127.0.0.1:8905',
    trade: env.VITE_TRADE_SERVICE_URL || 'http://127.0.0.1:8906',
    backtest: env.VITE_BACKTEST_SERVICE_URL || 'http://127.0.0.1:8907',
    training: env.VITE_TRAINING_SERVICE_URL || 'http://127.0.0.1:8908',
    diagnosis: env.VITE_DIAGNOSIS_SERVICE_URL || 'http://127.0.0.1:8909',
    gateway: env.VITE_GATEWAY_SERVICE_URL || 'http://127.0.0.1:8980',
  }
}

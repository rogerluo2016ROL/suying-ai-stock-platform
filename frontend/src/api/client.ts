import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Screener
export const screenerApi = {
  getModes: () => api.get('/screener/modes'),
  run: (mode: string, topN = 30) => api.post(`/screener/run?mode=${mode}&top_n=${topN}`),
};

// Prediction
export const predictionApi = {
  getStatus: () => api.get('/prediction/status'),
  predict: (code: string, days = 30) => api.post(`/prediction/predict/${code}?pred_days=${days}`),
  predictBatch: (codes: string[], days = 30) =>
    api.post(`/prediction/predict-batch?pred_days=${days}`, codes),
};

// Strategy
export const strategyApi = {
  generate: (picks: any[], capital = 1_000_000) =>
    api.post(`/strategy/generate?capital=${capital}`, picks),
  getTemplates: () => api.get('/strategy/templates'),
  getPlans: () => api.get('/strategy/plans'),
};

// Signal
export const signalApi = {
  getLevels: () => api.get('/signal/levels'),
  getLive: (session = 'intra') => api.get(`/signal/live?session=${session}`),
  getHistory: (code?: string) => api.get(`/signal/history${code ? `?code=${code}` : ''}`),
};

// Alert
export const alertApi = {
  getChannels: () => api.get('/alert/channels'),
  getConfig: () => api.get('/alert/config'),
};

// Trade
export const tradeApi = {
  getAccount: () => api.get('/trade/account'),
  getPositions: () => api.get('/trade/positions'),
  placeOrder: (code: string, direction: string, volume: number, price = 0) =>
    api.post(`/trade/order?code=${code}&direction=${direction}&volume=${volume}&price=${price}`),
};

// Backtest
export const backtestApi = {
  getFactors: () => api.get('/backtest/factors'),
  run: (mode = 'all', windows = 3) => api.post(`/backtest/run?mode=${mode}&windows=${windows}`),
};

// Diagnosis
export const diagnosisApi = {
  analyze: (code: string) => api.post(`/diagnosis/analyze?code=${code}`),
  compare: (codes: string[]) => api.post('/diagnosis/compare', codes),
};

// Health
export const healthApi = {
  check: (service: string) => api.get(`/${service}/../health`).catch(() => ({ data: { status: 'offline' } })),
};

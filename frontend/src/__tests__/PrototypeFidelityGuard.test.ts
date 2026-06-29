const pageSources = import.meta.glob('../pages/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const productionPages = [
  'Dashboard.tsx',
  'OpenDecision.tsx',
  'Screener.tsx',
  'SupplyChainBom.tsx',
  'Predictions.tsx',
  'Signals.tsx',
  'Trade.tsx',
  'Strategy.tsx',
  'AutoTrade.tsx',
  'RiskControl.tsx',
  'Backtest.tsx',
  'Diagnosis.tsx',
  'Training.tsx',
  'ModelRegistry.tsx',
  'DataUpdate.tsx',
  'RuntimeStatus.tsx',
]

const forbiddenPrototypeCopy = [
  '等待真实接口',
  '等待真实模型',
  '等待真实因子',
  '等待真实候选',
  '当前保留页面结构',
  '后续接入',
  '后续 BFF 接入',
  '接入后展示',
  'Phase 8',
  '回退样例',
  '暂不可用',
  '暂不可达',
  '数据状态 fallback',
]

describe('prototype fidelity guard', () => {
  it('keeps production prototype pages free of development placeholder copy', () => {
    const offenders = productionPages.flatMap(fileName => {
      const source = pageSources[`../pages/${fileName}`] ?? ''
      return forbiddenPrototypeCopy
        .filter(copy => source.includes(copy))
        .map(copy => `${fileName}: ${copy}`)
    })

    expect(offenders).toEqual([])
  })
})

import type {
  CorrelationCell,
  DecileMetric,
  FactorEvidenceResponse,
  FactorMetric,
} from '../../api/types'

export type FactorEvidenceView =
  | { kind: 'ready'; factors: FactorMetric[]; correlations: CorrelationCell[]; deciles: DecileMetric[] }
  | { kind: 'insufficient'; reasons: string[] }
  | { kind: 'unsupported'; reasons: string[] }

export function toFactorEvidenceView(response: FactorEvidenceResponse): FactorEvidenceView {
  if (response.status === 'ready') {
    return {
      kind: 'ready',
      factors: response.factors,
      correlations: response.correlations,
      deciles: response.deciles,
    }
  }

  return {
    kind: response.status === 'unsupported' ? 'unsupported' : 'insufficient',
    reasons: response.missing_requirements ?? [],
  }
}

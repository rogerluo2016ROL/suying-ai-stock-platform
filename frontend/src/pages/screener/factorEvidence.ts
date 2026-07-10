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

type FactorEvidenceStatus = FactorEvidenceResponse['status']

const INVALID_RESPONSE_REASON = 'invalid_factor_evidence_response'

function unsupportedView(): FactorEvidenceView {
  return { kind: 'unsupported', reasons: [INVALID_RESPONSE_REASON] }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function isOptionalString(value: unknown): value is string | undefined {
  return value === undefined || typeof value === 'string'
}

function isOptionalCount(value: unknown): value is number | undefined {
  return value === undefined || isNonNegativeInteger(value)
}

function isFactorMetric(value: unknown): value is FactorMetric {
  return isRecord(value)
    && isNonEmptyString(value.factor)
    && isOptionalString(value.label)
    && isFiniteNumber(value.ic_mean)
    && isFiniteNumber(value.ic_std)
    && isFiniteNumber(value.icir)
    && isFiniteNumber(value.t_stat)
    && isOptionalCount(value.observations)
}

function isCorrelationCell(value: unknown): value is CorrelationCell {
  return isRecord(value)
    && isNonEmptyString(value.factor_x)
    && isNonEmptyString(value.factor_y)
    && isFiniteNumber(value.correlation)
    && isOptionalCount(value.observations)
}

function isDecileMetric(value: unknown): value is DecileMetric {
  return isRecord(value)
    && isNonEmptyString(value.decile)
    && isOptionalString(value.description)
    && isFiniteNumber(value.cumulative_return_pct)
    && (value.daily_return_pct === undefined || isFiniteNumber(value.daily_return_pct))
    && isOptionalCount(value.observations)
}

function isFactorMetricArray(value: unknown): value is FactorMetric[] {
  return Array.isArray(value) && value.every(isFactorMetric)
}

function isCorrelationCellArray(value: unknown): value is CorrelationCell[] {
  return Array.isArray(value) && value.every(isCorrelationCell)
}

function isDecileMetricArray(value: unknown): value is DecileMetric[] {
  return Array.isArray(value) && value.every(isDecileMetric)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

function isKnownStatus(value: unknown): value is FactorEvidenceStatus {
  return value === 'ready'
    || value === 'insufficient_data'
    || value === 'insufficient'
    || value === 'unsupported'
}

export function isReadyFactorEvidenceView(value: unknown): value is Extract<FactorEvidenceView, { kind: 'ready' }> {
  return isRecord(value)
    && value.kind === 'ready'
    && isFactorMetricArray(value.factors)
    && isCorrelationCellArray(value.correlations)
    && isDecileMetricArray(value.deciles)
}

export function toFactorEvidenceView(response: unknown): FactorEvidenceView {
  if (!isRecord(response) || !isKnownStatus(response.status)) {
    return unsupportedView()
  }

  const observations = response.observations
  const tradeDates = response.trade_dates
  const missingRequirements = response.missing_requirements

  if (!isNonNegativeInteger(observations)
    || !isNonNegativeInteger(tradeDates)
    || (response.status === 'ready' && observations === 0)
    || !isFactorMetricArray(response.factors)
    || !isCorrelationCellArray(response.correlations)
    || !isDecileMetricArray(response.deciles)
    || (missingRequirements !== undefined && !isStringArray(missingRequirements))) {
    return unsupportedView()
  }

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
    reasons: missingRequirements ?? [],
  }
}

/** Strategy 域类型 (从 client.ts 拆出, C 域拆分)。 */

/** A screener pick passed to strategy generation / plan picks. */
export interface StrategyPick {
  candidate_id?: string
  source_module?: string
  source_mode?: string
  visibility?: 'private' | 'tenant_shared' | 'public'
  data_scope?: 'public' | 'tenant' | 'user' | 'account'
  code: string
  name?: string
  price?: number
  score?: number
  grade?: string
  [key: string]: unknown
}

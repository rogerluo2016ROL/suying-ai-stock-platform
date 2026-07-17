/** Trade 域类型 (从 client.ts 拆出, C 域拆分)。 */

/** Trade order record (audit log / orders list). */
export interface TradeOrder {
  id?: string | number
  code: string
  direction: string
  price: number
  volume: number
  status?: string
  time?: string
  filled_at?: string
  [key: string]: unknown
}

/** Trade account summary. */
export interface TradeAccount {
  total_capital?: number
  total_assets?: number
  total_pnl?: number
  available?: number
  market_value?: number
  [key: string]: unknown
}

import { http } from '@/lib/http'

export interface AuctionStatus {
  enabled: boolean
  task_id: number | null
  is_running: boolean
  site_base: string
  interval: number
  keyword_rules: string[]
  categories: string[]
  result_file: string
  last_run: string | null
  last_total: number
  last_saved: number
  last_recommended: number
  item_count: number
}

export interface AuctionItem {
  商品信息: Record<string, any>
  卖家信息?: Record<string, any>
  ai_analysis?: {
    is_recommended?: boolean
    reason?: string
    matched_keywords?: string[]
    keyword_hit_count?: number
  }
  [key: string]: any
}

export interface AuctionSeriesPoint {
  mark: string
  name: string
  sex: string
  weight: string
  gene: string
  category: string
  img: string
  price: number
  start_price: number
  current_bid: number
  bid_num: number
  freight: number
  has_bid: boolean
  status: string
  off_time: string
  date: string
}

export async function getAuctionStatus(): Promise<AuctionStatus> {
  return http('/api/auction/status')
}

export async function getAuctionItems(): Promise<{ items: AuctionItem[] }> {
  return http('/api/auction/items')
}

export async function getAuctionHits(): Promise<{ items: AuctionItem[] }> {
  return http('/api/auction/hits')
}

export async function getAuctionSeries(
  gene: string,
  category?: string,
): Promise<{ gene: string; category: string | null; points: AuctionSeriesPoint[] }> {
  const query = new URLSearchParams({ gene })
  if (category) query.set('category', category)
  return http(`/api/auction/history/series?${query.toString()}`)
}

export async function refreshAuction(): Promise<{ total: number; saved: number; recommended: number }> {
  return http('/api/auction/refresh', { method: 'POST' })
}

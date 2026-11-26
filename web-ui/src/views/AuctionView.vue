<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  getAuctionStatus,
  getAuctionItems,
  getAuctionSeries,
  refreshAuction,
  type AuctionItem,
  type AuctionSeriesPoint,
  type AuctionStatus,
} from '@/api/auction'
import { startTask, stopTask } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import Badge from '@/components/ui/badge/Badge.vue'
import Switch from '@/components/ui/switch/Switch.vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import GenePriceChart from '@/components/auction/GenePriceChart.vue'
import { toast } from '@/components/ui/toast'
import { Loader2, RefreshCcw, Clock } from 'lucide-vue-next'

const status = ref<AuctionStatus | null>(null)
const items = ref<AuctionItem[]>([])
const loading = ref(false)
const toggling = ref(false)

const nowTick = ref(Date.now())
const mountAt = Date.now()
let timer: number | undefined

const geneDialogOpen = ref(false)
const activeGene = ref('')
const activeCategory = ref('')
const series = ref<AuctionSeriesPoint[]>([])
const seriesLoading = ref(false)

async function loadStatus() {
  status.value = await getAuctionStatus()
}

async function loadItems() {
  const res = await getAuctionItems()
  items.value = res.items
}

async function refresh() {
  loading.value = true
  try {
    await refreshAuction()
    await Promise.all([loadStatus(), loadItems()])
  } catch {
    toast({ title: '刷新失败', variant: 'destructive' })
  } finally {
    loading.value = false
  }
}

async function toggleMonitor(checked: boolean) {
  if (!status.value) return
  toggling.value = true
  try {
    const id = status.value.task_id ?? 0
    if (checked) await startTask(id)
    else await stopTask(id)
    await loadStatus()
  } catch {
    toast({ title: '操作失败', variant: 'destructive' })
  } finally {
    toggling.value = false
  }
}

// ---------- 倒计时 ----------
function parseTime(v: unknown): number | null {
  if (!v) return null
  const t = Date.parse(String(v).replace(' ', 'T'))
  return Number.isNaN(t) ? null : t
}

function remainSeconds(item: AuctionItem): number | null {
  const info = item.商品信息 || {}
  const end = parseTime(info['结束时间'])
  if (end != null) return Math.max(0, Math.round((end - nowTick.value) / 1000))
  const sec = Number(info['剩余时间(秒)'])
  if (!Number.isNaN(sec) && sec > 0) {
    return Math.max(0, sec - Math.floor((nowTick.value - mountAt) / 1000))
  }
  return null
}

function fmtCountdown(sec: number | null): string {
  if (sec == null) return '—'
  if (sec <= 0) return '已结拍'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${String(h).padStart(2, '0')}:${mm}:${ss}` : `${mm}:${ss}`
}

// ---------- 展示辅助 ----------
function yuan(v: unknown): string {
  const n = Number(v)
  if (v == null || v === '' || Number.isNaN(n)) return '—'
  return `¥${n}`
}

function sexBadge(sex: string) {
  if (!sex) return { cls: 'bg-slate-100 text-slate-500 border-slate-200', label: '未知' }
  if (sex.includes('母')) return { cls: 'bg-pink-100 text-pink-600 border-pink-200', label: sex }
  if (sex.includes('公')) return { cls: 'bg-blue-100 text-blue-600 border-blue-200', label: sex }
  return { cls: 'bg-slate-100 text-slate-500 border-slate-200', label: sex }
}

function tagList(info: Record<string, any>): string[] {
  if (Array.isArray(info['标签列表']) && info['标签列表'].length) return info['标签列表']
  const raw = String(info['标签'] || '')
  return raw.split(/[、,，]/).map((s) => s.trim()).filter(Boolean)
}

function canOpenGene(gene: string) {
  return gene && gene !== '其他'
}

async function openGene(gene: string, category: string) {
  if (!canOpenGene(gene)) return
  activeGene.value = gene
  activeCategory.value = category
  geneDialogOpen.value = true
  seriesLoading.value = true
  series.value = []
  try {
    const res = await getAuctionSeries(gene, category || undefined)
    series.value = res.points
  } catch {
    toast({ title: '行情加载失败', variant: 'destructive' })
  } finally {
    seriesLoading.value = false
  }
}

const recommendedCount = computed(
  () => items.value.filter((it) => it.ai_analysis?.is_recommended === true).length,
)

onMounted(() => {
  loadStatus()
  loadItems()
  timer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">拍卖站监控</h1>
        <p class="mt-1 text-sm text-slate-500">
          易宠宝拍卖站在拍玉米蛇 / 王蛇；命中任务管理里配置的重点关键词才会进入结果查看。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-2 rounded-2xl border border-slate-200/70 bg-white/80 px-3 py-2">
          <Switch
            :model-value="status?.enabled === true"
            :disabled="toggling"
            @update:model-value="toggleMonitor"
          />
          <span class="text-sm font-semibold text-slate-700">
            {{ status?.enabled ? '监控中' : '已停止' }}
          </span>
        </div>
        <Button :disabled="loading" @click="refresh">
          <Loader2 v-if="loading" class="mr-1.5 h-4 w-4 animate-spin" />
          <RefreshCcw v-else class="mr-1.5 h-4 w-4" />
          刷新
        </Button>
      </div>
    </div>

    <div class="flex items-center gap-4 text-xs font-semibold text-slate-500">
      <span>在拍 {{ items.length }} 件</span>
      <span>重点命中 {{ recommendedCount }} 件</span>
      <span v-if="status?.keyword_rules?.length">重点词：{{ status.keyword_rules.join('、') }}</span>
    </div>

    <div v-if="loading && items.length === 0" class="app-surface text-center py-12 text-gray-500">
      正在采集…
    </div>
    <div
      v-else-if="items.length === 0"
      class="app-surface text-center py-12 text-gray-500"
    >
      暂无在拍名单，可点击右上角刷新，或在任务管理中启用拍卖站监控。
    </div>

    <div v-else class="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <Card
        v-for="item in items"
        :key="item.商品信息['商品ID']"
        class="group flex flex-col h-full overflow-hidden rounded-2xl border-none bg-white/80 shadow-glass backdrop-blur-sm transition-all duration-300 hover:shadow-card-hover"
      >
        <!-- 图片头 -->
        <div class="relative aspect-[4/3] overflow-hidden">
          <div v-if="!item.商品信息['商品图片列表']?.[0]" class="absolute inset-0 bg-slate-200 animate-pulse" />
          <img
            v-else
            :src="item.商品信息['商品图片列表'][0]"
            :alt="item.商品信息['商品标题']"
            class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-110"
            loading="lazy"
          />
          <div class="absolute left-3 top-3 flex gap-1.5">
            <Badge :class="sexBadge(item.商品信息['性别']).cls" variant="outline" class="border">
              {{ sexBadge(item.商品信息['性别']).label }}
            </Badge>
            <Badge
              v-if="canOpenGene(item.商品信息['基因'])"
              variant="outline"
              class="border-violet-200 bg-violet-50 text-violet-600 cursor-pointer hover:bg-violet-100"
              @click="openGene(item.商品信息['基因'], item.商品信息['分类'])"
            >
              {{ item.商品信息['基因'] }}
            </Badge>
          </div>
          <div class="absolute right-3 top-3">
            <Badge variant="secondary" class="bg-slate-900/75 text-white backdrop-blur-md">
              {{ item.商品信息['状态'] || '在拍' }}
            </Badge>
          </div>
        </div>

        <CardHeader class="p-4 pb-2">
          <CardTitle class="line-clamp-2 text-base font-semibold leading-snug text-slate-800">
            {{ item.商品信息['商品标题'] }}
          </CardTitle>
          <div class="mt-2 flex items-center gap-1.5 text-sm font-semibold" :class="(remainSeconds(item) ?? 1) <= 300 ? 'text-rose-600' : 'text-slate-600'">
            <Clock class="h-4 w-4" />
            {{ fmtCountdown(remainSeconds(item)) }}
          </div>
          <div class="mt-1.5 flex items-baseline gap-2">
            <span class="text-2xl font-bold tracking-tight text-rose-600">
              {{ Number(item.商品信息['当前拍价']) > 0 ? yuan(item.商品信息['当前拍价']) : yuan(item.商品信息['起拍价']) }}
            </span>
            <span class="text-xs text-slate-400">含运费成交 {{ yuan(item.商品信息['成交价']) }}</span>
          </div>
        </CardHeader>

        <CardContent class="flex-grow p-4 pt-2">
          <div class="grid grid-cols-2 gap-2">
            <div class="rounded-xl bg-slate-50/70 p-2.5">
              <div class="text-[10px] font-medium text-slate-400">起拍价</div>
              <div class="text-sm font-bold text-slate-700">{{ yuan(item.商品信息['起拍价']) }}</div>
            </div>
            <div class="rounded-xl bg-slate-50/70 p-2.5">
              <div class="text-[10px] font-medium text-slate-400">运费</div>
              <div class="text-sm font-bold text-slate-700">{{ yuan(item.商品信息['运费']) }}</div>
            </div>
            <div class="rounded-xl bg-slate-50/70 p-2.5">
              <div class="text-[10px] font-medium text-slate-400">加价幅度</div>
              <div class="text-sm font-bold text-slate-700">{{ yuan(item.商品信息['加价幅度']) }}</div>
            </div>
            <div class="rounded-xl bg-slate-50/70 p-2.5">
              <div class="text-[10px] font-medium text-slate-400">保证金</div>
              <div class="text-sm font-bold text-slate-700">{{ yuan(item.商品信息['保证金']) }}</div>
            </div>
          </div>

          <div class="mt-3 flex items-center justify-between text-xs text-slate-500">
            <span>出价人数 {{ item.商品信息['出价人数'] ?? 0 }}</span>
            <span v-if="item.商品信息['克重']">{{ item.商品信息['克重'] }}</span>
          </div>

          <div v-if="tagList(item.商品信息).length" class="mt-3 flex flex-wrap gap-1.5">
            <Badge
              v-for="tag in tagList(item.商品信息)"
              :key="tag"
              variant="outline"
              class="border-slate-200/70 bg-slate-50 text-slate-500"
            >
              {{ tag }}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 基因历史曲线弹窗 -->
    <Dialog v-model:open="geneDialogOpen">
      <DialogContent class="sm:max-w-[720px]">
        <DialogHeader>
          <DialogTitle>{{ activeGene }} · 历史结拍价</DialogTitle>
          <DialogDescription>
            成交价口径：有人出价 = 最高出价 + 运费；无人出价 = 起拍价 + 运费。
          </DialogDescription>
        </DialogHeader>
        <div v-if="seriesLoading" class="py-10 text-center text-sm text-slate-500">加载中…</div>
        <GenePriceChart v-else :points="series" />
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useResults } from '@/composables/useResults'
import ResultsFilterBar from '@/components/results/ResultsFilterBar.vue'
import ResultsGrid from '@/components/results/ResultsGrid.vue'
import ResultsInsightsPanel from '@/components/results/ResultsInsightsPanel.vue'
import { Button } from '@/components/ui/button'
import Badge from '@/components/ui/badge/Badge.vue'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'
import { getAuctionHits, type AuctionItem } from '@/api/auction'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const { t } = useI18n()
const router = useRouter()

const {
  files,
  selectedFile,
  results,
  insights,
  filters,
  isLoading,
  error,
  refreshResults,
  exportSelectedResults,
  deleteSelectedFile,
  toggleItemBlock,
  blacklistKeywords,
  isSavingBlacklist,
  saveBlacklistRules,
  fileOptions,
  isFileOptionsReady,
} = useResults()

// 拍卖站重点检查内容：仅展示命中重点关键词的拍品
const auctionHits = ref<AuctionItem[]>([])
const hitsLoading = ref(false)

async function loadHits() {
  hitsLoading.value = true
  try {
    const res = await getAuctionHits()
    auctionHits.value = res.items
  } catch {
    auctionHits.value = []
  } finally {
    hitsLoading.value = false
  }
}

onMounted(loadHits)

async function handleRefresh() {
  await refreshResults()
  await loadHits()
}

function parseTime(v: unknown): number | null {
  if (!v) return null
  const parsed = Date.parse(String(v).replace(' ', 'T'))
  return Number.isNaN(parsed) ? null : parsed
}

function hitRemainSeconds(item: AuctionItem): number | null {
  const info = item.商品信息 || {}
  const end = parseTime(info['结束时间'])
  if (end != null) return Math.max(0, Math.round((end - Date.now()) / 1000))
  const sec = Number(info['剩余时间(秒)'])
  return !Number.isNaN(sec) && sec > 0 ? Math.max(0, sec) : null
}

function fmtHitCountdown(sec: number | null): string {
  if (sec == null) return '—'
  if (sec <= 0) return '已结拍'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${String(h).padStart(2, '0')}:${mm}:${ss}` : `${mm}:${ss}`
}

function hitYuan(v: unknown): string {
  const n = Number(v)
  if (v == null || v === '' || Number.isNaN(n)) return '—'
  return `¥${n}`
}

function hitSexBadge(sex: string) {
  if (!sex) return { cls: 'bg-slate-100 text-slate-500 border-slate-200', label: '未知' }
  if (sex.includes('母')) return { cls: 'bg-pink-100 text-pink-600 border-pink-200', label: sex }
  if (sex.includes('公')) return { cls: 'bg-blue-100 text-blue-600 border-blue-200', label: sex }
  return { cls: 'bg-slate-100 text-slate-500 border-slate-200', label: sex }
}

function hitTagList(info: Record<string, any>): string[] {
  if (Array.isArray(info['标签列表']) && info['标签列表'].length) return info['标签列表']
  return String(info['标签'] || '').split(/[、,，]/).map((s) => s.trim()).filter(Boolean)
}

const isDeleteDialogOpen = ref(false)
const isBlacklistDialogOpen = ref(false)
const blacklistDraft = ref('')

const selectedTaskLabel = computed(() => {
  if (!selectedFile.value || fileOptions.value.length === 0) return null
  const match = fileOptions.value.find((option) => option.value === selectedFile.value)
  if (!match) return null
  return match.taskName || null
})

const deleteConfirmText = computed(() => {
  return selectedTaskLabel.value
    ? t('results.filters.deleteDialogWithTask', { task: selectedTaskLabel.value })
    : t('results.filters.deleteDialogFallback')
})

function openDeleteDialog() {
  if (!selectedFile.value) {
    toast({
      title: t('results.filters.noResultToDelete'),
      variant: 'destructive',
    })
    return
  }
  isDeleteDialogOpen.value = true
}

function openBlacklistDialog() {
  if (!selectedFile.value) {
    toast({
      title: t('results.filters.noResultSelected'),
      variant: 'destructive',
    })
    return
  }
  blacklistDraft.value = blacklistKeywords.value.join('\n')
  isBlacklistDialogOpen.value = true
}

function handleExportResults() {
  if (!selectedFile.value) {
    toast({
      title: t('results.filters.noResultToExport'),
      variant: 'destructive',
    })
    return
  }
  exportSelectedResults()
}

async function handleDeleteResults() {
  if (!selectedFile.value) return
  try {
    await deleteSelectedFile(selectedFile.value)
    toast({ title: t('results.filters.resultDeleted') })
  } catch (e) {
    toast({
      title: t('results.filters.deleteFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    isDeleteDialogOpen.value = false
  }
}

function parseBlacklistKeywords(input: string) {
  return input
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

async function handleSaveBlacklistRules() {
  try {
    await saveBlacklistRules(parseBlacklistKeywords(blacklistDraft.value))
    toast({ title: t('results.filters.blacklistSaved') })
    isBlacklistDialogOpen.value = false
  } catch (e) {
    toast({
      title: t('results.filters.blacklistSaveFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-gray-800 mb-6">
      {{ t('results.title') }}
    </h1>

    <div v-if="error" class="app-alert-error mb-4" role="alert">
      <strong class="font-bold">{{ t('common.error') }}</strong>
      <span class="block sm:inline">{{ error.message }}</span>
    </div>

    <ResultsFilterBar
      :files="files"
      :file-options="fileOptions"
      :is-ready="isFileOptionsReady"
      v-model:selectedFile="selectedFile"
      v-model:aiRecommendedOnly="filters.ai_recommended_only"
      v-model:keywordRecommendedOnly="filters.keyword_recommended_only"
      v-model:includeHidden="filters.include_hidden"
      v-model:sortBy="filters.sort_by"
      v-model:sortOrder="filters.sort_order"
      :is-loading="isLoading"
      @refresh="handleRefresh"
      @manage-blacklist="openBlacklistDialog"
      @export="handleExportResults"
      @delete="openDeleteDialog"
    />

    <ResultsInsightsPanel :insights="insights" :selected-task-label="selectedTaskLabel" />

    <ResultsGrid :results="results" :is-loading="isLoading" @toggle-block="toggleItemBlock" />

    <!-- 拍卖站重点检查内容：仅命中重点关键词的拍品 -->
    <section class="mt-10">
      <div class="mb-4 flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <h2 class="text-lg font-bold text-slate-800">拍卖站重点检查内容</h2>
        <span class="text-xs text-slate-400">命中任务管理里配置的重点关键词才会显示</span>
      </div>

      <div v-if="hitsLoading" class="app-surface py-8 text-center text-sm text-slate-500">
        加载中…
      </div>
      <div
        v-else-if="auctionHits.length === 0"
        class="app-surface rounded-2xl border border-dashed border-slate-200 px-6 py-10 text-center"
      >
        <p class="text-sm text-slate-500">暂未命中拍卖站重点关键词。</p>
        <Button variant="outline" class="mt-4" @click="router.push({ name: 'Tasks' })">
          去任务管理配置重点监控词
        </Button>
      </div>

      <div v-else class="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <div
          v-for="item in auctionHits"
          :key="item.商品信息['商品ID']"
          class="group flex h-full flex-col overflow-hidden rounded-2xl border-none bg-white/80 shadow-glass backdrop-blur-sm transition-all duration-300 hover:shadow-card-hover"
        >
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
              <Badge :class="hitSexBadge(item.商品信息['性别']).cls" variant="outline" class="border">
                {{ hitSexBadge(item.商品信息['性别']).label }}
              </Badge>
              <Badge v-if="item.商品信息['基因'] && item.商品信息['基因'] !== '其他'" variant="outline" class="border-violet-200 bg-violet-50 text-violet-600">
                {{ item.商品信息['基因'] }}
              </Badge>
            </div>
          </div>
          <div class="flex flex-grow flex-col p-4">
            <p class="line-clamp-2 text-base font-semibold leading-snug text-slate-800">
              {{ item.商品信息['商品标题'] }}
            </p>
            <div class="mt-1.5 flex items-center gap-1.5 text-sm font-semibold text-slate-600">
              结拍倒计时 {{ fmtHitCountdown(hitRemainSeconds(item)) }}
            </div>
            <div class="mt-1.5 flex items-baseline gap-2">
              <span class="text-2xl font-bold tracking-tight text-rose-600">
                {{ Number(item.商品信息['当前拍价']) > 0 ? hitYuan(item.商品信息['当前拍价']) : hitYuan(item.商品信息['起拍价']) }}
              </span>
              <span class="text-xs text-slate-400">含运费成交 {{ hitYuan(item.商品信息['成交价']) }}</span>
            </div>
            <div v-if="hitTagList(item.商品信息).length" class="mt-3 flex flex-wrap gap-1.5">
              <Badge
                v-for="tag in hitTagList(item.商品信息)"
                :key="tag"
                variant="outline"
                class="border-slate-200/70 bg-slate-50 text-slate-500"
              >
                {{ tag }}
              </Badge>
            </div>
          </div>
        </div>
      </div>
    </section>

    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{{ t('results.filters.deleteDialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ deleteConfirmText }}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button variant="destructive" :disabled="isLoading" @click="handleDeleteResults">
            {{ t('results.filters.confirmDelete') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isBlacklistDialogOpen">
      <DialogContent class="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{{ t('results.filters.blacklistDialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ t('results.filters.blacklistDialogDescription') }}
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-2">
          <label class="text-sm font-medium text-slate-700">
            {{ t('results.filters.blacklistRulesLabel') }}
          </label>
          <Textarea
            v-model="blacklistDraft"
            class="min-h-[180px]"
            :placeholder="t('results.filters.blacklistRulesPlaceholder')"
          />
          <p class="text-xs leading-5 text-slate-500">
            {{ t('results.filters.blacklistRulesHint') }}
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isBlacklistDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="isSavingBlacklist" @click="handleSaveBlacklistRules">
            {{ t('results.filters.confirmBlacklistSave') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

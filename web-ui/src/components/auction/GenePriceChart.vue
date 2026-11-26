<script setup lang="ts">
import { computed } from 'vue'

interface SeriesPoint {
  mark?: string
  name: string
  price: number | null
  date?: string
  off_time?: string
  sex?: string
  weight?: string
}

const props = defineProps<{
  points: SeriesPoint[]
}>()

const chartWidth = 720
const chartHeight = 240
const padding = 28
const paddingRight = 24

const validPoints = computed(() =>
  props.points.filter((p) => typeof p.price === 'number' && p.price !== null),
)

const valueRange = computed(() => {
  const values = validPoints.value.map((p) => p.price as number)
  if (values.length === 0) return { min: 0, max: 1 }
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) return { min: min - 1, max: max + 1 }
  const pad = (max - min) * 0.15
  return { min: min - pad, max: max + pad }
})

function resolveX(index: number) {
  if (validPoints.value.length <= 1) return chartWidth / 2
  const usable = chartWidth - padding - paddingRight
  return padding + (usable / (validPoints.value.length - 1)) * index
}

function resolveY(value: number) {
  const usableHeight = chartHeight - padding * 2
  const ratio = (value - valueRange.value.min) / (valueRange.value.max - valueRange.value.min)
  return chartHeight - padding - ratio * usableHeight
}

const linePath = computed(() => {
  if (validPoints.value.length === 0) return ''
  return validPoints.value
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${resolveX(i)} ${resolveY(p.price as number)}`)
    .join(' ')
})

const areaPath = computed(() => {
  if (validPoints.value.length === 0) return ''
  const firstX = resolveX(0)
  const lastX = resolveX(validPoints.value.length - 1)
  const baseline = chartHeight - padding
  return `${linePath.value} L ${lastX} ${baseline} L ${firstX} ${baseline} Z`
})

function labelOf(point: SeriesPoint) {
  const raw = point.date || point.off_time || ''
  if (!raw) return ''
  return raw.slice(5, 10)
}
</script>

<template>
  <div class="app-surface-subtle p-4">
    <div class="mb-3 flex items-center gap-1.5 text-xs uppercase tracking-[0.22em] text-slate-500">
      <span class="h-2.5 w-2.5 rounded-full bg-sky-600" />
      历史结拍价（含运费）
    </div>

    <div
      v-if="validPoints.length === 0"
      class="rounded-2xl border border-dashed border-slate-200 bg-white/70 px-4 py-10 text-center text-sm text-slate-500"
    >
      暂无该基因的历史成交记录
    </div>

    <svg
      v-else
      :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
      class="h-[240px] w-full"
      role="img"
      aria-label="基因历史结拍价曲线"
    >
      <defs>
        <linearGradient id="gene-area-fill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="#0284c7" stop-opacity="0.24" />
          <stop offset="100%" stop-color="#0284c7" stop-opacity="0" />
        </linearGradient>
      </defs>

      <g>
        <line
          v-for="index in 4"
          :key="index"
          :x1="padding"
          :x2="chartWidth - paddingRight"
          :y1="padding + ((chartHeight - padding * 2) / 4) * (index - 1)"
          :y2="padding + ((chartHeight - padding * 2) / 4) * (index - 1)"
          stroke="#cbd5e1"
          stroke-dasharray="4 6"
        />
      </g>

      <path :d="areaPath" fill="url(#gene-area-fill)" />
      <path :d="linePath" fill="none" stroke="#0284c7" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />

      <g v-for="(point, index) in validPoints" :key="point.mark || index">
        <circle
          :cx="resolveX(index)"
          :cy="resolveY(point.price as number)"
          r="5"
          fill="#0284c7"
          stroke="#fff"
          stroke-width="2"
        />
        <text
          :x="resolveX(index)"
          :y="resolveY(point.price as number) - 10"
          text-anchor="middle"
          fill="#0f172a"
          font-size="12"
          font-weight="600"
        >
          ¥{{ point.price }}
        </text>
        <text
          :x="resolveX(index)"
          :y="chartHeight - 8"
          text-anchor="middle"
          fill="#64748b"
          font-size="11"
        >
          {{ labelOf(point) || `#${index + 1}` }}
        </text>
      </g>
    </svg>

    <div class="mt-3 grid max-h-32 gap-2 overflow-y-auto">
      <div
        v-for="(point, index) in validPoints"
        :key="point.mark || index"
        class="flex items-center justify-between rounded-xl border border-slate-100 bg-white/70 px-3 py-1.5 text-xs"
      >
        <span class="truncate text-slate-700">{{ point.name || '未命名' }}</span>
        <span class="ml-3 shrink-0 font-semibold text-sky-700">¥{{ point.price }}</span>
      </div>
    </div>
  </div>
</template>

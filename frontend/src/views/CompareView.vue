<template>
  <div class="page">
    <div>
      <h1 style="margin-bottom: 4px">双 Run 对照</h1>
      <p class="muted" style="margin-top: 0">并排比较两条 Run 的血缘指纹与关键指标</p>
    </div>

    <!-- 选择区 -->
    <div class="card" style="margin-bottom: 16px">
      <div class="grid-2">
        <n-form-item label="Run A" :show-feedback="false">
          <n-select
            v-model:value="runA"
            filterable
            clearable
            :options="optionsA"
            placeholder="选择第一条 Run"
          />
        </n-form-item>
        <n-form-item label="Run B" :show-feedback="false">
          <n-select
            v-model:value="runB"
            filterable
            clearable
            :options="optionsB"
            placeholder="选择第二条 Run"
          />
        </n-form-item>
      </div>
      <div style="display: flex; gap: 8px; margin-top: 8px">
        <n-button type="primary" :loading="loading" :disabled="!runA || !runB" @click="compare">
          对比
        </n-button>
        <n-button :disabled="!runA && !runB" @click="swap">交换 A/B</n-button>
      </div>
    </div>

    <!-- 结果区 -->
    <template v-if="result">
      <n-alert
        v-if="diffItems.length"
        type="warning"
        title="发现差异项"
        style="margin-bottom: 16px"
      >
        <ul style="margin: 4px 0 0; padding-left: 18px">
          <li v-for="(item, i) in diffItems" :key="i">{{ item }}</li>
        </ul>
      </n-alert>
      <n-alert v-else type="success" title="两条 Run 的指纹与指标名集合一致" style="margin-bottom: 16px" />

      <div class="grid-2" style="margin-bottom: 16px">
        <div v-for="side in ['a', 'b']" :key="side" class="card">
          <h3 style="margin-top: 0">
            Run {{ side.toUpperCase() }}：{{ result[side].project }} / {{ result[side].name }}
            <n-tag :type="statusMap[result[side].status]?.type || 'default'" size="small">
              {{ statusMap[result[side].status]?.label || result[side].status }}
            </n-tag>
          </h3>
          <div style="display: grid; gap: 10px">
            <div>
              <div class="muted">
                code_commit_sha
                <n-tag v-if="!result.diff.code_commit_same" type="warning" size="tiny">不同</n-tag>
              </div>
              <div class="mono" :class="{ 'diff-hl': !result.diff.code_commit_same }">
                {{ result[side].code_commit_sha }}
              </div>
            </div>
            <div>
              <div class="muted">
                dataset_content_sha256
                <n-tag v-if="!result.diff.dataset_same" type="warning" size="tiny">不同</n-tag>
              </div>
              <div class="mono" :class="{ 'diff-hl': !result.diff.dataset_same }">
                {{ result[side].dataset_content_sha256 }}
              </div>
            </div>
            <div>
              <div class="muted">started_by / started_at</div>
              <div>
                {{ result[side].started_by }} · {{ formatTime(result[side].started_at) }}
              </div>
            </div>
            <div>
              <div class="muted">finished_at</div>
              <div>
                {{ result[side].finished_at ? formatTime(result[side].finished_at) : '—' }}
              </div>
            </div>
          </div>
          <p v-if="result[side].result_summary" style="margin-bottom: 0">
            <strong>结果：</strong>{{ result[side].result_summary }}
          </p>
          <p v-if="result[side].abort_reason" style="margin-bottom: 0">
            <strong>中止：</strong>{{ result[side].abort_reason }}
          </p>
        </div>
      </div>

      <div class="card">
        <h3 style="margin-top: 0">关键指标对照（同名取最新 step）</h3>
        <n-data-table
          :columns="metricColumns"
          :data="result.diff.metrics"
          :row-class-name="metricRowClass"
          :bordered="false"
          size="small"
        />
      </div>
    </template>
    <div v-else class="card">
      <n-empty description="选择两条 Run 后点击「对比」,此处展示对照结果" />
    </div>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NTag, useMessage } from 'naive-ui'
import { compareRuns, listRuns } from '../api/client'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const runs = ref([])
const runA = ref(null)
const runB = ref(null)
const result = ref(null)
const loading = ref(false)

const statusMap = {
  running: { type: 'info', label: '进行中' },
  completed: { type: 'success', label: '已完成' },
  aborted: { type: 'warning', label: '已中止' },
}

function toOption(r) {
  const s = statusMap[r.status]?.label || r.status
  return { label: `${r.project} / ${r.name}（${s}）`, value: r.id }
}

const optionsA = computed(() => runs.value.filter((r) => r.id !== runB.value).map(toOption))
const optionsB = computed(() => runs.value.filter((r) => r.id !== runA.value).map(toOption))

const diffItems = computed(() => {
  if (!result.value) return []
  const d = result.value.diff
  const items = []
  if (!d.code_commit_same) items.push('code_commit_sha 指纹不同')
  if (!d.dataset_same) items.push('dataset_content_sha256 指纹不同')
  if (d.metric_names_only_a.length) items.push(`指标名仅 A 有:${d.metric_names_only_a.join('、')}`)
  if (d.metric_names_only_b.length) items.push(`指标名仅 B 有:${d.metric_names_only_b.join('、')}`)
  return items
})

function formatMetric(value, step) {
  if (value === null || value === undefined) return '—'
  return `${value} @ step ${step}`
}

const metricColumns = [
  { title: '指标名', key: 'name' },
  {
    title: 'Run A 最新值',
    key: 'a',
    render: (row) => formatMetric(row.a_value, row.a_step),
  },
  {
    title: 'Run B 最新值',
    key: 'b',
    render: (row) => formatMetric(row.b_value, row.b_step),
  },
  {
    title: '差异',
    key: 'flag',
    render(row) {
      if (!row.in_b) return h(NTag, { type: 'warning', size: 'small' }, { default: () => '仅 A' })
      if (!row.in_a) return h(NTag, { type: 'warning', size: 'small' }, { default: () => '仅 B' })
      if (row.value_differs) {
        return h(NTag, { type: 'info', size: 'small' }, { default: () => '值不同' })
      }
      return '—'
    },
  },
]

function metricRowClass(row) {
  return !row.in_a || !row.in_b ? 'diff-row' : ''
}

function formatTime(v) {
  return new Date(v).toLocaleString()
}

async function compare() {
  if (!runA.value || !runB.value) return
  if (runA.value === runB.value) {
    message.warning('请选择两条不同的 Run')
    return
  }
  loading.value = true
  try {
    result.value = await compareRuns(runA.value, runB.value)
    router.replace({ query: { a: runA.value, b: runB.value } })
  } catch (e) {
    result.value = null
    message.error(e.message || '对照加载失败')
  } finally {
    loading.value = false
  }
}

function swap() {
  const a = runA.value
  runA.value = runB.value
  runB.value = a
  if (runA.value && runB.value) compare()
}

onMounted(async () => {
  try {
    runs.value = await listRuns()
  } catch (e) {
    message.error(e.message || 'Run 列表加载失败')
    return
  }
  const { a, b } = route.query
  if (typeof a === 'string' && typeof b === 'string') {
    runA.value = a
    runB.value = b
    compare()
  }
})
</script>

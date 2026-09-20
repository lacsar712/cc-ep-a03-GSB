<template>
  <div class="page">
    <div>
      <h1 style="margin-bottom: 4px">Run 对照</h1>
      <p class="muted" style="margin-top: 0">选择两条 Run，并排比较血缘指纹、状态与关键指标</p>
    </div>

    <!-- 选择区 -->
    <div class="card" style="margin: 16px 0">
      <div class="grid-2">
        <n-form-item label="Run A" :show-feedback="false">
          <n-select
            v-model:value="leftId"
            :options="runOptions"
            :loading="loadingRuns"
            clearable
            filterable
            placeholder="选择第一条 Run"
          />
        </n-form-item>
        <n-form-item label="Run B" :show-feedback="false">
          <n-select
            v-model:value="rightId"
            :options="runOptions"
            :loading="loadingRuns"
            clearable
            filterable
            placeholder="选择第二条 Run"
          />
        </n-form-item>
      </div>
      <n-alert
        v-if="leftId && leftId === rightId"
        type="info"
        :bordered="false"
        style="margin-top: 8px"
      >
        两侧选择了同一条 Run，对照结果将完全一致。
      </n-alert>
    </div>

    <!-- 结果区 -->
    <template v-if="both">
      <div v-if="loadingCmp" class="card muted">加载对照数据…</div>
      <template v-else-if="left && right">
        <div class="card" style="margin-bottom: 16px">
          <h3 style="margin-top: 0">差异摘要</h3>
          <ul v-if="diffItems.length" style="margin: 0; padding-left: 18px">
            <li v-for="(d, i) in diffItems" :key="i">{{ d }}</li>
          </ul>
          <p v-else class="muted" style="margin: 0">两条 Run 的指纹、状态与指标完全一致，无差异项。</p>
        </div>

        <div class="card" style="margin-bottom: 16px">
          <h3 style="margin-top: 0">血缘与状态</h3>
          <table class="cmp-table">
            <thead>
              <tr>
                <th style="width: 200px">字段</th>
                <th>Run A · {{ left.project }} / {{ left.name }}</th>
                <th>Run B · {{ right.project }} / {{ right.name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr :class="{ diff: left.status !== right.status }">
                <td>状态</td>
                <td>
                  <n-tag size="small" :type="statusType(left.status)">
                    {{ statusLabel(left.status) }}
                  </n-tag>
                </td>
                <td>
                  <n-tag size="small" :type="statusType(right.status)">
                    {{ statusLabel(right.status) }}
                  </n-tag>
                </td>
              </tr>
              <tr :class="{ diff: left.dataset_content_sha256 !== right.dataset_content_sha256 }">
                <td>dataset_content_sha256</td>
                <td class="mono">{{ left.dataset_content_sha256 }}</td>
                <td class="mono">{{ right.dataset_content_sha256 }}</td>
              </tr>
              <tr :class="{ diff: left.code_commit_sha !== right.code_commit_sha }">
                <td>code_commit_sha</td>
                <td class="mono">{{ left.code_commit_sha }}</td>
                <td class="mono">{{ right.code_commit_sha }}</td>
              </tr>
              <tr>
                <td>started_by / started_at</td>
                <td>{{ left.started_by }} · {{ formatTime(left.started_at) }}</td>
                <td>{{ right.started_by }} · {{ formatTime(right.started_at) }}</td>
              </tr>
              <tr>
                <td>finished_at</td>
                <td>{{ left.finished_at ? formatTime(left.finished_at) : '—' }}</td>
                <td>{{ right.finished_at ? formatTime(right.finished_at) : '—' }}</td>
              </tr>
              <tr v-if="left.result_summary || right.result_summary">
                <td>结果摘要</td>
                <td>{{ left.result_summary || '—' }}</td>
                <td>{{ right.result_summary || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h3 style="margin-top: 0">关键指标对照（各指标取最大 step 值）</h3>
          <table v-if="metricRows.length" class="cmp-table">
            <thead>
              <tr>
                <th>指标</th>
                <th>Run A</th>
                <th>Run B</th>
                <th style="width: 110px">标记</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in metricRows" :key="row.name" :class="{ diff: row.diff }">
                <td class="mono">{{ row.name }}</td>
                <td>{{ row.a ? `${row.a.value} @ step ${row.a.step}` : '—' }}</td>
                <td>{{ row.b ? `${row.b.value} @ step ${row.b.step}` : '—' }}</td>
                <td><span v-if="row.tag" class="diff-badge">{{ row.tag }}</span></td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted" style="margin: 0">两条 Run 均无指标记录。</p>
        </div>
      </template>
    </template>
    <div v-else class="card muted">
      结果区：请在上方选择两条 Run（seed 数据下任选两条已完成 Run 即可看到差异高亮）。
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { getLineage, listRuns } from '../api/client'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const runs = ref([])
const loadingRuns = ref(false)
const loadingCmp = ref(false)
const leftId = ref(null)
const rightId = ref(null)
const left = ref(null)
const right = ref(null)

const statusLabels = { running: '进行中', completed: '已完成', aborted: '已中止' }
const statusTypes = { running: 'info', completed: 'success', aborted: 'warning' }

const statusLabel = (s) => statusLabels[s] || s
const statusType = (s) => statusTypes[s] || 'default'

const runOptions = computed(() =>
  runs.value.map((r) => ({
    label: `${r.project} / ${r.name}（${statusLabel(r.status)}）`,
    value: r.id,
  })),
)

const both = computed(() => Boolean(leftId.value && rightId.value))

function formatTime(v) {
  return new Date(v).toLocaleString()
}

function latestByName(metrics) {
  const map = {}
  for (const m of metrics || []) {
    const cur = map[m.name]
    if (!cur || m.step >= cur.step) map[m.name] = m
  }
  return map
}

const metricRows = computed(() => {
  if (!left.value || !right.value) return []
  const aMap = latestByName(left.value.metrics)
  const bMap = latestByName(right.value.metrics)
  const names = [...new Set([...Object.keys(aMap), ...Object.keys(bMap)])].sort()
  return names.map((name) => {
    const a = aMap[name]
    const b = bMap[name]
    let tag = ''
    if (a && !b) tag = '仅 A 有'
    else if (!a && b) tag = '仅 B 有'
    else if (a.value !== b.value) tag = '值不同'
    return { name, a, b, tag, diff: Boolean(tag) }
  })
})

const diffItems = computed(() => {
  if (!left.value || !right.value) return []
  const items = []
  if (left.value.dataset_content_sha256 !== right.value.dataset_content_sha256) {
    items.push('dataset 指纹不同')
  }
  if (left.value.code_commit_sha !== right.value.code_commit_sha) {
    items.push('code commit 指纹不同')
  }
  if (left.value.status !== right.value.status) {
    items.push(`状态不同：A=${statusLabel(left.value.status)}，B=${statusLabel(right.value.status)}`)
  }
  const onlyA = metricRows.value.filter((r) => r.tag === '仅 A 有').map((r) => r.name)
  const onlyB = metricRows.value.filter((r) => r.tag === '仅 B 有').map((r) => r.name)
  const valDiff = metricRows.value.filter((r) => r.tag === '值不同').map((r) => r.name)
  if (onlyA.length) items.push(`指标名仅 A 有：${onlyA.join('、')}`)
  if (onlyB.length) items.push(`指标名仅 B 有：${onlyB.join('、')}`)
  if (valDiff.length) items.push(`共同指标取值不同：${valDiff.join('、')}`)
  return items
})

watch([leftId, rightId], async ([a, b]) => {
  router.replace({ query: { ...route.query, a: a || undefined, b: b || undefined } })
  left.value = null
  right.value = null
  if (!a || !b) return
  loadingCmp.value = true
  try {
    const [la, lb] = await Promise.all([getLineage(a), getLineage(b)])
    left.value = la
    right.value = lb
  } catch (e) {
    message.error(e.message || '加载对照数据失败')
  } finally {
    loadingCmp.value = false
  }
})

onMounted(async () => {
  loadingRuns.value = true
  try {
    runs.value = await listRuns()
    const qa = route.query.a
    const qb = route.query.b
    if (typeof qa === 'string' && runs.value.some((r) => r.id === qa)) leftId.value = qa
    if (typeof qb === 'string' && runs.value.some((r) => r.id === qb)) rightId.value = qb
  } catch (e) {
    message.error(e.message || '加载 Run 列表失败')
  } finally {
    loadingRuns.value = false
  }
})
</script>

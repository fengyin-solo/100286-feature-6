<template>
  <section class="page" data-module="tree">
    <header class="page-head">
      <div>
        <h2>乔木管理</h2>
        <p class="page-desc">生长正常 → 长势衰弱 → 濒危 → 已枯死的处置链：复壮登记、枯死缘由、管护交接全程留痕。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记乔木</button>
        <button class="btn" type="button" @click="exportRows">导出乔木清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>树木编号</span>
        <input v-model="keyword" placeholder="按树木编号检索" />
      </label>
      <label class="filter-item">
        <span>长势</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>复壮记录</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ display(row, column) }}</td>
          <td>
            <template v-if="rejuvenations(row).length">
              <p v-for="(rec, idx) in rejuvenations(row)" :key="idx" class="inline-note">
                {{ rec['管护人'] }} · {{ rec['时间'] }}<br />{{ rec['复壮措施'] }}
              </p>
            </template>
            <span v-else-if="row.status === '长势衰弱'" class="warn-text">待认领复壮</span>
            <span v-else>—</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action.key"
              class="link"
              type="button"
              @click="openAction(action, row)"
            >
              {{ action.label }}
            </button>
            <button class="link" type="button" @click="openHistory(row)">历程</button>
            <button class="link" type="button" @click="openKeeperFor(row)">管护交接</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无乔木数据，可先登记乔木</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条乔木记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记乔木 -->
    <div v-if="createOpen" class="modal-mask" @click.self="createOpen = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记乔木</h3>
        <p class="modal-tip">胸径、冠幅为空不许落库。</p>
        <label v-for="field in createFields" :key="field.key" class="modal-field">
          <span>{{ field.label }}<em v-if="field.required">*</em></span>
          <input v-model="createForm[field.key]" :placeholder="`请填写${field.label}`" />
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="createOpen = false">取消</button>
          <button class="btn primary" type="submit">落库</button>
        </div>
      </form>
    </div>

    <!-- 处置动作 -->
    <div v-if="actionOpen" class="modal-mask" @click.self="actionOpen = false">
      <form class="modal" @submit.prevent="submitAction">
        <h3>{{ currentAction?.label }} · {{ activeRow?.['树木编号'] }}</h3>
        <p class="modal-tip">{{ actionHint }}</p>
        <label class="modal-field">
          <span>管护人<em>*</em></span>
          <input v-model="actionForm.operator" placeholder="执行本步骤的管护人" />
        </label>
        <label v-if="currentAction?.key === '记录衰弱'" class="modal-field">
          <span>衰弱说明</span>
          <textarea v-model="actionForm['衰弱说明']" rows="3" placeholder="症状描述；重复登记以最后一版为准"></textarea>
        </label>
        <label v-if="currentAction?.key === '登记复壮'" class="modal-field">
          <span>复壮措施<em>*</em></span>
          <textarea v-model="actionForm['复壮措施']" rows="3" placeholder="同一管护人重复提交只认第一次"></textarea>
        </label>
        <label v-if="currentAction?.key === '登记枯死'" class="modal-field">
          <span>枯死缘由<em>*</em></span>
          <textarea v-model="actionForm['枯死缘由']" rows="3" placeholder="确认枯死必须写明缘由"></textarea>
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="actionOpen = false">取消</button>
          <button class="btn primary" type="submit">提交</button>
        </div>
      </form>
    </div>

    <!-- 管护交接 -->
    <div v-if="keeperOpen" class="modal-mask" @click.self="keeperOpen = false">
      <form class="modal" @submit.prevent="submitHandover">
        <h3>管护交接 · {{ activeRow?.['树木编号'] }}</h3>
        <p class="modal-tip" v-if="activeRow?.['管护人员']">
          当前管护人：{{ activeRow['管护人员'] }}；交接后仍可在列表中看到上一位管护人。
        </p>
        <label class="modal-field">
          <span>接手管护人<em>*</em></span>
          <input v-model="keeperForm['管护人员']" placeholder="接手管护人姓名" />
        </label>
        <label class="modal-field">
          <span>交接经办人</span>
          <input v-model="keeperForm.operator" placeholder="默认记为接手管护人" />
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="keeperOpen = false">取消</button>
          <button class="btn primary" type="submit">确认交接</button>
        </div>
      </form>
    </div>

    <!-- 处置历程 -->
    <div v-if="historyOpen" class="modal-mask" @click.self="historyOpen = false">
      <div class="modal">
        <h3>处置历程 · {{ activeRow?.['树木编号'] }}</h3>
        <ul class="timeline">
          <li v-for="(step, idx) in historySteps" :key="idx">
            <div class="timeline-head">
              <strong>{{ step['动作'] }}</strong>
              <span>{{ step['时间'] }} · {{ step['管护人'] }}</span>
            </div>
            <p v-if="step['说明']">{{ step['说明'] }}</p>
          </li>
          <li v-if="!historySteps.length" class="empty-state">暂无处置记录</li>
        </ul>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="historyOpen = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/tree'
const columns = ["树木编号", "树种名称", "胸径", "冠幅", "树龄", "定植日期", "管护人员", "上一位管护人", "树木状态"]
const statuses = ["生长正常", "长势衰弱", "濒危", "已枯死"]

const stats = ref([
  { label: '正常乔木（观察中）', value: 0 },
  { label: '衰弱/濒危乔木', value: 0 },
  { label: '未处理株数', value: 0 },
  { label: '枯死乔木', value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

// 处置链动作按当前长势开放，避免越级流转
const ACTIONS: Record<string, { key: string; label: string }[]> = {
  生长正常: [{ key: '记录衰弱', label: '记录衰弱' }],
  长势衰弱: [{ key: '登记复壮', label: '登记复壮' }, { key: '确认濒危', label: '确认濒危' }],
  濒危: [{ key: '登记复壮', label: '登记复壮' }, { key: '登记枯死', label: '登记枯死' }],
  已枯死: [],
}

const ACTION_HINTS: Record<string, string> = {
  记录衰弱: '重复登记衰弱以最后一版为准，每一步都会记下时间与管护人。',
  登记复壮: '同一管护人重复提交复壮只认第一次；登记后乔木回到观察中。',
  确认濒危: '长势衰弱且已挂复壮记录的乔木才能确认濒危。',
  登记枯死: '只有濒危株可确认枯死，必须写明枯死缘由。',
}

function availableActions(row: Row) {
  return ACTIONS[String(row.status)] ?? []
}
function rejuvenations(row: Row): Row[] {
  return Array.isArray(row['复壮记录']) ? row['复壮记录'] : []
}
function display(row: Row, column: string) {
  if (column === '树木状态') return row.status ?? '—'
  if (column === '上一位管护人') return row[column] || '—'
  return row[column] ?? '—'
}

// ---------------------------------------------------------------- 登记弹窗
const createFields = [
  { key: '树木编号', label: '树木编号', required: true },
  { key: '树种名称', label: '树种名称', required: true },
  { key: '胸径', label: '胸径', required: true },
  { key: '冠幅', label: '冠幅', required: true },
  { key: '树龄', label: '树龄', required: false },
  { key: '定植日期', label: '定植日期', required: false },
  { key: '管护人员', label: '管护人员', required: false },
]
const createOpen = ref(false)
const createForm = reactive<Record<string, string>>({})

function openCreate() {
  createFields.forEach((field) => { createForm[field.key] = '' })
  errorMessage.value = ''
  createOpen.value = true
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message || '乔木登记失败')
    }
    createOpen.value = false
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '乔木登记失败'
  }
}

// ---------------------------------------------------------------- 处置弹窗
const actionOpen = ref(false)
const currentAction = ref<{ key: string; label: string } | null>(null)
const activeRow = ref<Row | null>(null)
const actionForm = reactive<Record<string, string>>({ operator: '' })

const actionHint = ref('')

function openAction(action: { key: string; label: string }, row: Row) {
  currentAction.value = action
  activeRow.value = row
  actionForm.operator = String(row['管护人员'] || '')
  actionForm['衰弱说明'] = String(row['衰弱说明'] || '')
  actionForm['复壮措施'] = ''
  actionForm['枯死缘由'] = ''
  actionHint.value = ACTION_HINTS[action.key] ?? ''
  errorMessage.value = ''
  actionOpen.value = true
}

async function submitAction() {
  if (!currentAction.value || !activeRow.value) return
  errorMessage.value = ''
  const values: Record<string, string> = { action: currentAction.value.key, ...actionForm }
  try {
    const response = await request(`${ENDPOINT}/${activeRow.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message || '处置动作未生效')
    }
    actionOpen.value = false
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '处置动作未生效'
  }
}

// ---------------------------------------------------------------- 交接弹窗
const keeperOpen = ref(false)
const keeperForm = reactive<Record<string, string>>({ '管护人员': '', operator: '' })

function openKeeper() {
  keeperForm['管护人员'] = ''
  keeperForm.operator = ''
  errorMessage.value = ''
  keeperOpen.value = true
}

async function submitHandover() {
  if (!activeRow.value) return
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${activeRow.value.id}/keeper`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...keeperForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message || '管护交接失败')
    }
    keeperOpen.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '管护交接失败'
  }
}

// 交接按钮挂在每一行（已枯死也允许交接备注），通过历程按钮旁的入口打开
function openKeeperFor(row: Row) {
  activeRow.value = row
  openKeeper()
}

// ---------------------------------------------------------------- 历程弹窗
const historyOpen = ref(false)
const historySteps = ref<Row[]>([])

async function openHistory(row: Row) {
  activeRow.value = row
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('乔木明细读取失败')
    const detail = await response.json()
    historySteps.value = Array.isArray(detail['处置历程']) ? detail['处置历程'] : []
    historyOpen.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '乔木明细读取失败'
  }
}

// ---------------------------------------------------------------- 数据加载
function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    stats.value = [
      { label: '正常乔木（观察中）', value: payload['正常乔木'] ?? 0 },
      { label: '衰弱/濒危乔木', value: payload['衰弱乔木'] ?? 0 },
      { label: '未处理株数', value: payload['未处理株数'] ?? 0 },
      { label: '枯死乔木', value: payload['枯死乔木'] ?? 0 },
    ]
  } catch {
    // 看板指标拉不到时保留 0，不阻塞列表
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('乔木列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '乔木列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

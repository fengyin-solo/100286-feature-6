<template>
  <section class="page" data-module="tree">
    <header class="page-head">
      <div>
        <h2>乔木管理</h2>
        <p class="page-desc">生长正常 → 长势衰弱 → 濒危 → 观察中 → 已枯死，每一步留时间、留管护人；衰弱株必须挂上复壮记录。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记乔木</button>
        <button class="btn" type="button" @click="exportRows">导出乔木清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card" :class="{ alert: item.alert }">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p v-if="board['衰弱缺复壮记录']?.length" class="warn-text">
      有 {{ board['衰弱缺复壮记录'].length }} 株衰弱/濒危乔木尚未挂复壮记录，请尽快认领处置。
    </p>

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
          <th>处置</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '树木编号'">
              <button class="link" type="button" @click="openDetail(row)">{{ row[column] ?? '—' }}</button>
            </template>
            <template v-else-if="column === '管护人员'">
              {{ row[column] ?? '—' }}
              <span v-if="handoverOf(row)" class="muted-text" :title="`上一任：${handoverOf(row)?.['管护人']}，交接于 ${handoverOf(row)?.['交接时间']}`">
                （上一任：{{ handoverOf(row)?.['管护人'] }}）
              </span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action.name"
              class="link"
              type="button"
              @click="openAction(action.name, row)"
            >
              {{ action.label }}
            </button>
            <button class="link" type="button" @click="openDetail(row)">处置链</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无乔木数据，可先登记乔木</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条乔木记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 登记乔木 -->
    <div v-if="createOpen" class="modal-mask" @click.self="createOpen = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记乔木</h3>
        <p class="modal-tip">胸径、冠幅为空不许落库。</p>
        <label v-for="field in createFields" :key="field.name" class="form-item">
          <span>{{ field.label }}<em v-if="field.required"> *</em></span>
          <input v-model="createForm[field.name]" :placeholder="`请输入${field.label}`" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="createOpen = false">取消</button>
          <button class="btn primary" type="submit">落库登记</button>
        </div>
      </form>
    </div>

    <!-- 处置动作 -->
    <div v-if="actionOpen" class="modal-mask" @click.self="actionOpen = false">
      <form class="modal" @submit.prevent="submitAction">
        <h3>{{ actionMeta.title }}</h3>
        <p class="modal-tip">{{ actionMeta.tip }}</p>
        <label class="form-item">
          <span>管护人 <em>*</em></span>
          <input v-model="actionForm['管护人员']" placeholder="本次操作的管护人" />
        </label>
        <label v-if="actionName === '记录衰弱'" class="form-item">
          <span>衰弱表现</span>
          <input v-model="actionForm['衰弱表现']" placeholder="如：叶片黄化、抽梢减少" />
        </label>
        <label v-if="actionName === '记录衰弱'" class="form-item">
          <span>衰弱诱因</span>
          <input v-model="actionForm['衰弱诱因']" placeholder="如：积水烂根、病虫蛀干" />
        </label>
        <label v-if="actionName === '登记濒危'" class="form-item">
          <span>濒危说明</span>
          <input v-model="actionForm['濒危说明']" placeholder="如：树冠三分之二枯死" />
        </label>
        <label v-if="actionName === '登记复壮'" class="form-item">
          <span>复壮措施</span>
          <input v-model="actionForm['复壮措施']" placeholder="如：打孔通气、追施复合肥、输液" />
        </label>
        <label v-if="actionName === '确认枯死'" class="form-item">
          <span>枯死缘由 <em>*</em></span>
          <textarea v-model="actionForm['枯死缘由']" rows="3" placeholder="必须写明缘由，如：复壮无效整株失水枯死"></textarea>
        </label>
        <label v-if="actionName === '管护交接'" class="form-item">
          <span>接手管护人 <em>*</em></span>
          <input v-model="actionForm['接手管护人']" placeholder="交接后的管护人姓名" />
        </label>
        <p v-if="actionError" class="error-text">{{ actionError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="actionOpen = false">取消</button>
          <button class="btn primary" type="submit">确认提交</button>
        </div>
      </form>
    </div>

    <!-- 处置链明细 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal modal-wide">
        <h3>{{ detail['树木编号'] }} · {{ detail['树种名称'] }}（{{ detail.status }}）</h3>
        <p class="modal-tip">
          胸径 {{ detail['胸径'] }} ｜ 冠幅 {{ detail['冠幅'] }} ｜ 当前管护人：{{ detail['管护人员'] || '空缺' }}
          <template v-if="detail.handover_from">
            ｜ 上一任管护人：{{ detail.handover_from['管护人'] }}（{{ detail.handover_from['交接时间'] }} 交接）
          </template>
        </p>

        <h4>最近衰弱登记<span class="muted-text">（重复登记以最后一版为准）</span></h4>
        <table v-if="latestWeak" class="data-table sub-table">
          <tbody>
            <tr><th>表现</th><td>{{ latestWeak['表现'] || '—' }}</td><th>诱因</th><td>{{ latestWeak['诱因'] || '—' }}</td></tr>
            <tr><th>登记管护人</th><td>{{ latestWeak['管护人'] }}</td><th>时间</th><td>{{ latestWeak['时间'] }}</td></tr>
          </tbody>
        </table>
        <p v-else class="muted-text">暂无衰弱登记。</p>

        <h4>复壮明细</h4>
        <table class="data-table sub-table">
          <thead>
            <tr><th>衰弱期</th><th>管护人</th><th>措施</th><th>登记时间</th><th>状态</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in detail.rejuvenations" :key="idx">
              <td>第{{ item['衰弱期'] }}轮</td>
              <td>{{ item['管护人'] }}</td>
              <td>{{ item['措施'] || '—' }}</td>
              <td>{{ item['时间'] }}</td>
              <td>{{ item['状态'] }}</td>
            </tr>
            <tr v-if="!detail.rejuvenations?.length">
              <td colspan="5" class="empty-state">尚无复壮记录，长势衰弱/濒危时必须补登记</td>
            </tr>
          </tbody>
        </table>

        <h4>处置时间线</h4>
        <ul class="timeline">
          <li v-for="(event, idx) in detail.timeline" :key="idx">
            <span class="timeline-time">{{ event['时间'] }}</span>
            <span class="timeline-action">{{ event['动作'] }}</span>
            <span class="timeline-who">{{ event['管护人'] }}</span>
            <span class="timeline-note">{{ event['说明'] }}</span>
          </li>
        </ul>

        <div class="modal-actions">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, unknown>
type TimelineEvent = { 动作: string; 管护人: string; 时间: string; 说明: string }
type RejuvRecord = { 衰弱期: number; 管护人: string; 措施: string; 时间: string; 状态: string }
type HandoverInfo = { 管护人: string; 交接时间: string; 交接办理人: string }
type DeclineEpisode = { id: number; weak_record: Record<string, string> | null }
type MissingRejuv = { id: number; 树木编号: string; 管护人员: string }
type TreeBoard = {
  total: number
  未处理株数: number
  生长正常: number
  长势衰弱: number
  濒危: number
  观察中: number
  已枯死: number
  复壮记录数: number
  衰弱缺复壮记录: MissingRejuv[]
}

const ENDPOINT = '/api/tree'
const columns = ['树木编号', '树种名称', '胸径', '冠幅', '树龄', '定植日期', '管护人员', '树木状态']
const statuses = ['生长正常', '长势衰弱', '濒危', '观察中', '已枯死']

const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const successMessage = ref('')

const board = ref<TreeBoard>({
  total: 0,
  未处理株数: 0,
  生长正常: 0,
  长势衰弱: 0,
  濒危: 0,
  观察中: 0,
  已枯死: 0,
  复壮记录数: 0,
  衰弱缺复壮记录: [],
})

const stats = computed(() => [
  { label: '乔木总株数', value: board.value.total, alert: false },
  { label: '未处理株数', value: board.value['未处理株数'], alert: true },
  { label: '长势衰弱', value: board.value['长势衰弱'], alert: false },
  { label: '濒危', value: board.value['濒危'], alert: false },
  { label: '观察中', value: board.value['观察中'], alert: false },
  { label: '已枯死', value: board.value['已枯死'], alert: false },
])

const ACTION_META: Record<string, { label: string; title: string; tip: string }> = {
  记录衰弱: { label: '记录衰弱', title: '登记长势衰弱', tip: '同一株树重复登记衰弱以最后一版为准；每次都会记录时间与管护人。' },
  登记濒危: { label: '转濒危', title: '登记濒危', tip: '仅长势衰弱的乔木可转濒危，濒危株仍计入未处理。' },
  登记复壮: { label: '登记复壮', title: '登记复壮措施', tip: '同一管护人在同一轮衰弱期重复提交，只认第一次；登记后乔木回到观察中。' },
  确认枯死: { label: '确认枯死', title: '确认枯死', tip: '仅观察中的乔木可确认枯死，必须写明缘由。' },
  管护交接: { label: '管护交接', title: '办理管护交接', tip: '只更换管护人、不改变长势；交接后仍可查看上一位管护人。' },
}

function availableActions(row: Row) {
  const status = String(row.status ?? '')
  const allowed: string[] = []
  if (status === '生长正常' || status === '观察中') allowed.push('记录衰弱')
  if (status === '长势衰弱') {
    allowed.push('记录衰弱', '登记濒危', '登记复壮')
  }
  if (status === '濒危') allowed.push('登记复壮')
  if (status === '观察中') allowed.push('确认枯死', '登记复壮')
  if (status !== '已枯死') allowed.push('管护交接')
  return allowed.map((name) => ({ name, ...ACTION_META[name] }))
}

function handoverOf(row: Row): HandoverInfo | null {
  return (row.handover_from as HandoverInfo | null | undefined) ?? null
}

type TreeDetail = Row & {
  status: string
  timeline?: TimelineEvent[]
  rejuvenations?: RejuvRecord[]
  handover_from?: HandoverInfo | null
  decline?: DeclineEpisode | null
}

// --------------------------------------------------------------- 登记乔木
const createFields = [
  { name: '树木编号', label: '树木编号', required: true },
  { name: '树种名称', label: '树种名称', required: true },
  { name: '胸径', label: '胸径', required: true },
  { name: '冠幅', label: '冠幅', required: true },
  { name: '树龄', label: '树龄', required: false },
  { name: '定植日期', label: '定植日期', required: false },
  { name: '管护人员', label: '管护人员', required: false },
] as const

const createOpen = ref(false)
const createError = ref('')
const createForm = reactive<Record<string, string>>({})

function openCreate() {
  createError.value = ''
  for (const key of Object.keys(createForm)) delete createForm[key]
  createForm['管护人员'] = session.operator
  createOpen.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      createError.value = payload.message
      return
    }
    createOpen.value = false
    flash(`乔木 ${createForm['树木编号']} 已落库登记`)
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '登记失败'
  }
}

// --------------------------------------------------------------- 处置动作
const actionOpen = ref(false)
const actionName = ref('')
const actionError = ref('')
const actionTarget = ref<Row | null>(null)
const actionForm = reactive<Record<string, string>>({})

const actionMeta = computed(() => ACTION_META[actionName.value])

function openAction(name: string, row: Row) {
  actionName.value = name
  actionTarget.value = row
  actionError.value = ''
  for (const key of Object.keys(actionForm)) delete actionForm[key]
  actionForm['管护人员'] = String(row['管护人员'] || session.operator)
  if (name === '管护交接') actionForm['管护人员'] = session.operator
  actionOpen.value = true
}

async function submitAction() {
  if (!actionTarget.value) return
  actionError.value = ''
  const id = actionTarget.value.id
  try {
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: actionName.value, ...actionForm } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      actionError.value = payload.message
      return
    }
    actionOpen.value = false
    flash(payload.message)
    await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '操作未生效'
  }
}

// --------------------------------------------------------------- 处置链明细
const detail = ref<TreeDetail | null>(null)

const latestWeak = computed(() => detail.value?.decline?.weak_record ?? null)

async function openDetail(row: Row) {
  detail.value = null
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('明细读取失败')
    detail.value = (await response.json()) as TreeDetail
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '明细读取失败'
  }
}

// --------------------------------------------------------------- 列表与看板
function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function flash(message: string) {
  successMessage.value = message
  window.setTimeout(() => {
    if (successMessage.value === message) successMessage.value = ''
  }, 3000)
}

async function reloadBoard() {
  try {
    const response = await request(`${ENDPOINT}/board`)
    if (response.ok) board.value = await response.json()
  } catch {
    // 看板加载失败不阻塞列表
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
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
    await reloadBoard()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '乔木列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.warn-text {
  margin: 0 0 12px;
  padding: 8px 12px;
  background: #fff7ed;
  border: 1px solid #fdba74;
  border-radius: 6px;
  color: #9a3412;
  font-size: 13px;
}
.stat-card.alert {
  border-color: #f04438;
  background: #fef3f2;
}
.stat-card.alert .stat-value {
  color: #b42318;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.success-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  width: 420px;
  max-height: 86vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal-wide {
  width: 720px;
}
.modal h3 {
  margin: 0 0 4px;
}
.modal h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}
.modal-tip {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 12px;
}
.form-item {
  display: block;
  margin-bottom: 10px;
  font-size: 13px;
}
.form-item span {
  display: block;
  margin-bottom: 4px;
  color: #344054;
}
.form-item em {
  color: #b42318;
  font-style: normal;
}
.form-item input,
.form-item textarea,
.filter-item input,
.filter-item select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.sub-table th,
.sub-table td {
  font-size: 12px;
  padding: 6px 8px;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  border-left: 2px solid var(--border);
}
.timeline li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 0 6px 14px;
  font-size: 12px;
  position: relative;
}
.timeline li::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
}
.timeline-time {
  color: var(--muted);
}
.timeline-action {
  font-weight: 600;
}
.timeline-who {
  color: #075985;
}
.timeline-note {
  flex-basis: 100%;
  color: #475467;
}
</style>

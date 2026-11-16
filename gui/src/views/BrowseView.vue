<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { fetchMemories, fetchMemoryDetail } from '@/api'
import type { Memory, MemoryDetail } from '@/api/types'

const loading = ref(true)
const error = ref('')
const items = ref<Memory[]>([])
const total = ref(0)

const q = ref('')
const typeFilter = ref('')
const supFilter = ref(false)
const page = ref(1)
const pageSize = 20

const detail = ref<MemoryDetail | null>(null)
const detailLoading = ref(false)

const typeLabels: Record<string, string> = {
  semantic: '语义记忆',
  episodic: '情景记忆',
  procedural: '程序记忆',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchMemories({
      q: q.value || undefined,
      type: typeFilter.value || undefined,
      sup: supFilter.value,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    items.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function openDetail(id: string) {
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await fetchMemoryDetail(id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    detailLoading.value = false
  }
}

watch([q, typeFilter, supFilter], () => {
  page.value = 1
  load()
})
watch(page, load)
onMounted(load)
</script>

<template>
  <div>
    <header class="pagehead">
      <div>
        <h1>记忆浏览</h1>
        <p class="sub">检索全部记忆，点开查看完整元数据与内容（当前只读）</p>
      </div>
      <span class="readonly">当前只读 · 写/编辑待开放</span>
    </header>

    <div class="toolbar">
      <input
        v-model="q"
        type="search"
        placeholder="搜索名称或摘要…"
        aria-label="搜索记忆"
        class="search"
      />
      <select v-model="typeFilter" aria-label="按类型过滤" class="select">
        <option value="">全部类型</option>
        <option value="semantic">语义记忆</option>
        <option value="episodic">情景记忆</option>
        <option value="procedural">程序记忆</option>
      </select>
      <label class="check">
        <input v-model="supFilter" type="checkbox" />
        只看被取代
      </label>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state error" role="alert">{{ error }}</div>
    <div v-else-if="!items.length" class="state">无匹配记忆</div>
    <ul v-else class="mem-list" aria-label="记忆列表">
      <li v-for="m in items" :key="m.id" class="mem">
        <button class="mem-main" @click="openDetail(m.id)">
          <span class="ttag">{{ typeLabels[m.type] ?? m.type }}</span>
          <span class="tname">{{ m.name || m.id }}</span>
          <span class="mmeta">boost {{ m.boost }}</span>
        </button>
        <p v-if="m.abstract" class="mabs">{{ m.abstract }}</p>
      </li>
    </ul>

    <div v-if="total > pageSize" class="pager">
      <button :disabled="page <= 1" @click="page--">上一页</button>
      <span>第 {{ page }} 页 · 共 {{ Math.ceil(total / pageSize) }} 页</span>
      <button :disabled="page >= Math.ceil(total / pageSize)" @click="page++">下一页</button>
    </div>

    <!-- 详情抽屉 -->
    <div v-if="detail || detailLoading" class="drawer-mask" @click.self="detail = null">
      <aside class="drawer" role="dialog" aria-label="记忆详情">
        <div v-if="detailLoading" class="state">加载中…</div>
        <template v-else-if="detail">
          <button class="close" aria-label="关闭" @click="detail = null">×</button>
          <h2>{{ detail.meta.name || detail.id }}</h2>
          <h3>元数据</h3>
          <div class="kv-list">
            <div v-for="(v, k) in detail.meta" :key="k" class="kv">
              <span class="k">{{ k }}</span>
              <span class="v">{{ v }}</span>
            </div>
          </div>
          <template v-if="detail.conclusion">
            <h3>结论</h3>
            <p class="body conclusion">{{ detail.conclusion }}</p>
          </template>
          <template v-if="detail.reason">
            <h3>理由</h3>
            <p class="body">{{ detail.reason }}</p>
          </template>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.pagehead {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 22px;
}
.pagehead h1 {
  font-size: 19px;
  font-weight: 600;
}
.sub {
  color: var(--content-secondary);
  font-size: 13px;
  margin-top: 3px;
}
.readonly {
  font-size: 12px;
  color: var(--warning);
  border: 1px solid var(--border-base);
  padding: 5px 12px;
  border-radius: 20px;
  white-space: nowrap;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.search {
  flex: 1;
  min-width: 200px;
  background: var(--surface-panel);
  border: 1px solid var(--border-base);
  color: var(--content-primary);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.select {
  background: var(--surface-panel);
  border: 1px solid var(--border-base);
  color: var(--content-primary);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--content-secondary);
  cursor: pointer;
}

.mem-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mem {
  background: var(--surface-panel);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  box-shadow: var(--shadow-panel);
}
.mem-main {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: var(--content-primary);
}
.tname {
  font-weight: 500;
  font-size: 14px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mmeta {
  font-size: 12px;
  color: var(--content-secondary);
  flex-shrink: 0;
}
.mabs {
  margin-top: 6px;
  font-size: 13px;
  color: var(--content-secondary);
}

.pager {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
  margin-top: 16px;
  font-size: 13px;
  color: var(--content-secondary);
}
.pager button {
  background: var(--surface-panel);
  border: 1px solid var(--border-base);
  color: var(--content-primary);
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
}
.pager button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  display: flex;
  justify-content: flex-end;
}
.drawer {
  background: var(--surface-panel);
  width: min(480px, 90vw);
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  position: relative;
}
.close {
  position: absolute;
  top: 12px;
  right: 16px;
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--content-secondary);
  line-height: 1;
}
.drawer h2 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 10px;
  padding-right: 30px;
}
.drawer h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--content-secondary);
  margin: 16px 0 8px;
}
.body {
  font-size: 13px;
  color: var(--content-primary);
  white-space: pre-wrap;
}
.body.conclusion {
  font-weight: 600;
  font-size: 14px;
}
.kv-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kv {
  display: flex;
  gap: 12px;
  font-size: 13px;
}
.kv .k {
  color: var(--content-secondary);
  flex-shrink: 0;
  min-width: 90px;
}
.kv .v {
  color: var(--content-primary);
  word-break: break-all;
}

.state {
  padding: 24px;
  text-align: center;
  color: var(--content-muted);
}
.state.error {
  color: var(--danger);
}

@media (max-width: 720px) {
  .pagehead {
    flex-direction: column;
    gap: 8px;
  }
  .search {
    min-width: 100%;
  }
}
</style>

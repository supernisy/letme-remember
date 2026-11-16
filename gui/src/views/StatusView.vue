<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchStatus } from '@/api'
import type { Status } from '@/api/types'

const loading = ref(true)
const error = ref('')
const data = ref<Status | null>(null)

const serveStateText: Record<string, string> = {
  running: '运行中',
  idle: '空闲（自退，正常）',
  error: '异常',
}

const serveStateColor: Record<string, string> = {
  running: 'var(--success)',
  idle: 'var(--warning)',
  error: 'var(--danger)',
}

onMounted(async () => {
  try {
    data.value = await fetchStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <header class="pagehead">
      <div>
        <h1>系统状态</h1>
        <p class="sub">运行中各组件的健康状态，以及未来可开关项（当前只读）</p>
      </div>
      <span class="readonly">当前只读 · 写/编辑待开放</span>
    </header>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state error" role="alert">{{ error }}</div>
    <template v-else-if="data">
      <section class="panel">
        <h2 class="section-title">核心服务</h2>
        <div class="status-list">
          <div class="status-item">
            <span class="sdot" :style="{ background: serveStateColor[data.serve_state] ?? 'var(--content-muted)' }"></span>
            <span class="k">常驻召回服务</span>
            <span class="v">{{ serveStateText[data.serve_state] ?? data.serve_state }}</span>
          </div>
          <div class="status-item">
            <span class="sdot" :style="{ background: data.embedding.enabled ? 'var(--success)' : 'var(--content-muted)' }"></span>
            <span class="k">语义检索（embedding）</span>
            <span class="v">{{ data.embedding.enabled ? '启用' : '停用' }} · {{ data.embedding.model }}</span>
          </div>
          <div class="status-item">
            <span class="sdot" :style="{ background: (data.vector.indexed ?? 0) > 0 ? 'var(--success)' : 'var(--content-muted)' }"></span>
            <span class="k">向量库</span>
            <span class="v">已向量化 {{ data.vector.indexed ?? 0 }} 条 · {{ data.vector.dim ?? 0 }} 维</span>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2 class="section-title">数据位置</h2>
        <div class="kv-list">
          <div class="kv"><span>数据目录</span><span>{{ data.data_dir }}</span></div>
          <div class="kv"><span>store 文件</span><span>{{ data.files.store }}</span></div>
          <div class="kv"><span>archive 文件</span><span>{{ data.files.archive }}</span></div>
        </div>
      </section>
    </template>
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

.panel {
  background: var(--surface-panel);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-panel);
}
.section-title {
  font-size: 13px;
  color: var(--content-secondary);
  margin-bottom: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.sdot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.k {
  color: var(--content-secondary);
}
.v {
  margin-left: auto;
  color: var(--content-primary);
  font-weight: 500;
}

.kv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kv {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;
  color: var(--content-secondary);
}
.kv span:last-child {
  color: var(--content-primary);
  text-align: right;
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
}
</style>

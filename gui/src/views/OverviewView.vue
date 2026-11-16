<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchOverview } from '@/api'
import type { Overview } from '@/api/types'

const loading = ref(true)
const error = ref('')
const data = ref<Overview | null>(null)

const typeLabels: Record<string, string> = {
  semantic: '语义记忆',
  episodic: '情景记忆',
  procedural: '程序记忆',
}

const verdict = computed(() => {
  if (!data.value) return { text: '加载中', level: 'loading' }
  const h = data.value.health
  const consistency = (h.consistency?.score as number) ?? 100
  const freshness = (h.freshness?.score as number) ?? 100
  if (consistency < 80 || freshness < 60) {
    return { text: '需要处理', level: 'warn' }
  }
  return { text: '健康', level: 'ok' }
})

onMounted(async () => {
  try {
    data.value = await fetchOverview()
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
        <h1>总览</h1>
        <p class="sub">一句话健康判定，再下钻看细节</p>
      </div>
    </header>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state error" role="alert">{{ error }}</div>
    <template v-else-if="data">
      <!-- 健康判定 -->
      <section class="verdict" :data-level="verdict.level">
        <span class="vdot" aria-hidden="true"></span>
        <div>
          <div class="vtext">{{ verdict.text }}</div>
          <div class="vsub">共 {{ data.total }} 条记忆 · {{ data.files.store }} 条在库 · {{ data.files.archive }} 条归档</div>
        </div>
      </section>

      <!-- 类型分布 -->
      <section class="panel">
        <h2 class="section-title">记忆类型分布</h2>
        <div class="type-grid">
          <div v-for="(label, t) in typeLabels" :key="t" class="type-card">
            <span class="tname">{{ label }}</span>
            <span class="tnum">{{ data.type_count[t] ?? 0 }}</span>
          </div>
        </div>
      </section>

      <!-- 数据状态 -->
      <section class="panel">
        <h2 class="section-title">数据状态</h2>
        <div class="kv-list">
          <div class="kv"><span>已被取代</span><span>{{ data.superseded }} 条</span></div>
          <div class="kv"><span>含来源链</span><span>{{ data.has_provenance }} 条</span></div>
          <div class="kv"><span>含 boost 排序乘数</span><span>{{ data.has_boost }} 条</span></div>
        </div>
      </section>

      <!-- 来源分布 -->
      <section class="panel">
        <h2 class="section-title">来源分布</h2>
        <div v-if="data.authors.length" class="kv-list">
          <div v-for="a in data.authors" :key="a.name" class="kv">
            <span>{{ a.name }}</span><span>{{ a.n }} 条</span>
          </div>
        </div>
        <div v-else class="state">暂无来源数据</div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.pagehead {
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

.verdict {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--surface-panel);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-panel);
}
.vdot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--success);
}
.verdict[data-level='warn'] .vdot {
  background: var(--warning);
}
.verdict[data-level='loading'] .vdot {
  background: var(--content-muted);
}
.vtext {
  font-size: 16px;
  font-weight: 600;
}
.vsub {
  font-size: 12px;
  color: var(--content-secondary);
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

.type-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.type-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--surface-panel-2);
  border-radius: var(--radius-sm);
}
.tname {
  color: var(--content-secondary);
  font-size: 13px;
}
.tnum {
  margin-left: auto;
  font-size: 18px;
  font-weight: 600;
}

.kv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kv {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--content-secondary);
}
.kv span:last-child {
  color: var(--content-primary);
  font-weight: 500;
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
  .type-grid {
    grid-template-columns: 1fr;
  }
}
</style>

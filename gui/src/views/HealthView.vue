<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchHealth } from '@/api'
import type { HealthIssue } from '@/api/types'

const loading = ref(true)
const error = ref('')
const issues = ref<HealthIssue[]>([])

const flagLabels: Record<string, string> = {
  conflict: '冲突（已被取代）',
  stale: '过期',
  nosrc: '缺来源',
}

const flagColors: Record<string, string> = {
  conflict: 'var(--danger)',
  stale: 'var(--warning)',
  nosrc: 'var(--content-muted)',
}

onMounted(async () => {
  try {
    const res = await fetchHealth()
    issues.value = res.issues
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
        <h1>记忆体检</h1>
        <p class="sub">逐条记忆的完整诊断指标（业界 mem-gc 四维模型，当前只读）</p>
      </div>
      <span class="readonly">当前只读 · 写/编辑待开放</span>
    </header>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state error" role="alert">{{ error }}</div>
    <div v-else-if="!issues.length" class="state">无问题记忆，全部健康</div>
    <ul v-else class="diag-list" aria-label="问题记忆列表">
      <li v-for="iss in issues" :key="iss.id" class="diag">
        <div class="dhead">
          <span class="dname">{{ iss.name }}</span>
          <span class="dtype">{{ iss.type }}</span>
        </div>
        <div class="flags">
          <span
            v-for="f in iss.flags"
            :key="f"
            class="flag"
            :style="{ color: flagColors[f] ?? 'var(--content-secondary)', borderColor: flagColors[f] ?? 'var(--border-base)' }"
          >
            {{ flagLabels[f] ?? f }}
          </span>
        </div>
        <p v-if="iss.abstract" class="dabs">{{ iss.abstract }}</p>
        <div class="dmetrics">
          <span>访问 {{ iss.access_count }} 次</span>
          <span v-if="iss.stale_days != null">已存 {{ iss.stale_days }} 天</span>
          <span>{{ iss.has_provenance ? '有来源' : '缺来源' }}</span>
        </div>
      </li>
    </ul>
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

.diag-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.diag {
  background: var(--surface-panel);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  box-shadow: var(--shadow-panel);
}
.dhead {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.dname {
  font-weight: 500;
  font-size: 14px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dtype {
  font-size: 11px;
  color: var(--content-secondary);
  background: var(--surface-panel-2);
  padding: 2px 8px;
  border-radius: 6px;
  flex-shrink: 0;
}
.flags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.flag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--border-base);
}
.dabs {
  font-size: 13px;
  color: var(--content-secondary);
  margin-bottom: 6px;
}
.dmetrics {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--content-muted);
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

<script setup lang="ts">
import { ref } from 'vue'
import OverviewView from './views/OverviewView.vue'
import StatusView from './views/StatusView.vue'
import BrowseView from './views/BrowseView.vue'
import HealthView from './views/HealthView.vue'

type ViewKey = 'overview' | 'status' | 'browse' | 'health'

const nav = [
  { key: 'overview' as ViewKey, label: '总览', dot: 'var(--action-primary)' },
  { key: 'status' as ViewKey, label: '系统状态', dot: 'var(--type-procedural)' },
  { key: 'browse' as ViewKey, label: '记忆浏览', dot: 'var(--type-semantic)' },
  { key: 'health' as ViewKey, label: '记忆体检', dot: 'var(--type-episodic)' },
]

const active = ref<ViewKey>('overview')
</script>

<template>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        letme-remember
        <small>记忆控制台 · 当前只读</small>
      </div>
      <nav class="nav" aria-label="主导航">
        <a
          v-for="item in nav"
          :key="item.key"
          href="#"
          :class="{ active: active === item.key }"
          role="tab"
          :aria-selected="active === item.key"
          @click.prevent="active = item.key"
        >
          <span class="dot" :style="{ background: item.dot }"></span>{{ item.label }}
        </a>
      </nav>
      <div class="sidebar-foot">
        <span class="readonly">当前只读 · 写/编辑待开放</span>
      </div>
    </aside>

    <main class="main" role="main">
      <OverviewView v-if="active === 'overview'" />
      <StatusView v-else-if="active === 'status'" />
      <BrowseView v-else-if="active === 'browse'" />
      <HealthView v-else-if="active === 'health'" />
    </main>
  </div>
</template>

<style scoped>
.app {
  display: grid;
  /* minmax(0,1fr)：防止子内容（长文本/nowrap）把列撑出视口导致横向滚动 */
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 100vh;
}

.sidebar {
  background: var(--surface-panel);
  border-right: 1px solid var(--border-base);
  padding: 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0; /* 防 grid item 的 min-content 溢出列宽 */
}

.brand {
  font-size: 15px;
  font-weight: 600;
  padding: 0 10px 16px;
  letter-spacing: 0.3px;
  color: var(--content-primary);
}
.brand small {
  display: block;
  font-size: 11px;
  color: var(--content-muted);
  font-weight: 400;
  margin-top: 2px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nav a {
  color: var(--content-secondary);
  text-decoration: none;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.nav a:hover {
  background: var(--surface-hover);
  color: var(--content-primary);
}
.nav a.active {
  background: var(--surface-hover);
  color: var(--content-primary);
  font-weight: 500;
}
.nav .dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: 1px;
}

.sidebar-foot {
  margin-top: auto;
  padding: 16px 10px 0;
}
.readonly {
  font-size: 12px;
  color: var(--warning);
  border: 1px solid var(--border-base);
  padding: 5px 12px;
  border-radius: 20px;
  white-space: nowrap;
}

.main {
  padding: 26px 32px;
  max-width: 1200px;
  width: 100%;
  min-width: 0; /* 关键：允许内容区收缩，配合 grid minmax(0,1fr) 防横向滚动 */
}

/* —— 响应式：窄屏单列（320px 起） —— */
@media (max-width: 720px) {
  .app {
    grid-template-columns: minmax(0, 1fr);
  }
  .sidebar {
    flex-direction: column;
    align-items: stretch;
    flex-wrap: nowrap;
    gap: 10px;
    border-right: none;
    border-bottom: 1px solid var(--border-base);
    padding: 12px 16px;
  }
  .brand {
    padding: 0;
    margin-right: auto;
  }
  .nav {
    flex-direction: row;
    flex-wrap: wrap; /* 窄屏 tab 可换行，避免挤出视口 */
    gap: 4px;
  }
  .nav a {
    padding: 7px 10px;
    white-space: nowrap;
  }
  .sidebar-foot {
    margin-top: 0;
    padding: 0;
  }
  .main {
    padding: 16px;
  }
}
</style>

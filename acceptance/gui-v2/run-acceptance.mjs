#!/usr/bin/env node
/**
 * gui-v2 验收脚本 —— 对照 acceptance/gui-v2/contract.yaml 的 12 条验收逐条出证据。
 *
 * 复用 verify-suite 的 playwright（不重复安装浏览器/依赖）。
 * 前提：GUI 服务已启动（python mem.py gui --port 8787）。
 *
 * 用法：node acceptance/gui-v2/run-acceptance.mjs [--base http://127.0.0.1:8787]
 * 退出码：0 = 全部通过；1 = 存在失败项。
 */
import { createRequire } from 'node:module';
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

// 从 verify-suite 的 node_modules 解析 playwright（最新副本）
const VS = 'C:/Users/super/WorkBuddy/2026-10-18-19-39-24/verify-suite';
const require_ = createRequire(join(VS, 'package.json'));
const { chromium } = require_('playwright');

const BASE = (() => {
  const i = process.argv.indexOf('--base');
  return i >= 0 ? process.argv[i + 1] : 'http://127.0.0.1:8787';
})();
const REPO = 'C:/letme-remember';

const results = [];
function record(id, pass, evidence) {
  results.push({ id, pass, evidence });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${id}\n      ${evidence}`);
}

// 相对亮度对比度（WCAG）
function contrast(rgb1, rgb2) {
  const lum = ([r, g, b]) => {
    const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const [l1, l2] = [lum(rgb1), lum(rgb2)].sort((a, b) => b - a);
  return (l1 + 0.05) / (l2 + 0.05);
}
const parseRgb = (s) => (s.match(/\d+(\.\d+)?/g) || []).slice(0, 3).map(Number);

async function main() {
  // ---- 契约 1：工程化与技术栈-1（构建产物存在且可静态 serve）----
  {
    const dist = join(REPO, 'gui/dist');
    const idx = existsSync(join(dist, 'index.html'));
    const assets = idx ? readdirSync(join(dist, 'assets')) : [];
    record('工程化与技术栈-1', idx && assets.some(f => f.endsWith('.js')) && assets.some(f => f.endsWith('.css')),
      `dist/index.html=${idx}, assets=${assets.length} 个（含 js/css）`);
  }

  // ---- 契约 2：工程化与技术栈-2（后端 serve dist + 6 个 API 不变）----
  {
    const home = await fetch(`${BASE}/`);
    const html = await home.text();
    const apiStatus = {};
    for (const api of ['overview', 'status', 'health', 'memories', 'audit']) {
      const r = await fetch(`${BASE}/api/${api}`);
      apiStatus[api] = r.status;
    }
    // memory/{id} 用 memories 返回的第一条测
    const mems = await (await fetch(`${BASE}/api/memories?limit=1`)).json();
    const firstId = mems.items?.[0]?.id;
    if (firstId) apiStatus['memory/{id}'] = (await fetch(`${BASE}/api/memory/${encodeURIComponent(firstId)}`)).status;
    const allOk = home.status === 200 && html.includes('<div id="app">') &&
      Object.values(apiStatus).every(s => s === 200);
    record('工程化与技术栈-2', allOk,
      `首页 HTTP ${home.status}（Vue 挂载点存在=${html.includes('<div id="app">')}），API 状态：${JSON.stringify(apiStatus)}`);
  }

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const apiCalls = [];
    page.on('request', r => { if (r.url().includes('/api/')) apiCalls.push(r.url()); });
    await page.goto(BASE, { waitUntil: 'networkidle' });

    // ---- 契约 3：四个视图-1（总览：健康判定/类型分布/数据状态/来源分布 + /api/overview）----
    {
      const verdict = await page.locator('.verdict .vtext').textContent().catch(() => null);
      const sections = await page.locator('.section-title').allTextContents();
      const called = apiCalls.some(u => u.includes('/api/overview'));
      const need = ['记忆类型分布', '数据状态', '来源分布'];
      const ok = !!verdict && need.every(n => sections.some(s => s.includes(n))) && called;
      record('四个视图完整迁移-1', ok,
        `健康判定="${(verdict || '').trim().slice(0, 30)}"，sections=${JSON.stringify(sections)}，/api/overview 被调用=${called}`);
    }

    // ---- 契约 4：四个视图-2（系统状态视图 + /api/status）----
    {
      await page.click('nav a[role="tab"]:has-text("系统状态")');
      await page.waitForSelector('.status-item', { timeout: 5000 });
      const items = await page.locator('.status-item .k').allTextContents();
      const called = apiCalls.some(u => u.includes('/api/status'));
      const ok = items.length >= 2 && called;
      record('四个视图完整迁移-2', ok, `状态项=${JSON.stringify(items)}，/api/status 被调用=${called}`);
    }

    // ---- 契约 5：四个视图-3（记忆浏览：搜索/类型过滤/被取代过滤/分页 + /api/memories + 单调性不变量）----
    {
      await page.click('nav a[role="tab"]:has-text("记忆浏览")');
      await page.waitForSelector('.mem-list .mem', { timeout: 5000 });
      const hasSearch = await page.locator('input.search[aria-label="搜索记忆"]').count() > 0;
      const hasTypeFilter = await page.locator('select.select[aria-label="按类型过滤"]').count() > 0;
      const hasSupersededFilter = (await page.locator('.toolbar .check').textContent())?.includes('取代') ?? false;
      const hasPager = await page.locator('.pager').count() > 0;
      const called = apiCalls.some(u => u.includes('/api/memories'));
      // 不变量：limit 增大，返回条数不减少（API 层验证）
      const n1 = (await (await fetch(`${BASE}/api/memories?limit=5`)).json()).items?.length ?? 0;
      const n2 = (await (await fetch(`${BASE}/api/memories?limit=20`)).json()).items?.length ?? 0;
      const monotonic = n2 >= n1;
      const ok = hasSearch && hasTypeFilter && hasSupersededFilter && hasPager && called && monotonic;
      record('四个视图完整迁移-3', ok,
        `搜索=${hasSearch} 类型过滤=${hasTypeFilter} 被取代过滤=${hasSupersededFilter} 分页=${hasPager} /api/memories=${called}；不变量 limit5→${n1} 条, limit20→${n2} 条, 单调=${monotonic}`);
    }

    // ---- 契约 6：四个视图-4（记忆体检 + /api/health）----
    {
      await page.click('nav a[role="tab"]:has-text("记忆体检")');
      await page.waitForFunction(
        () => document.querySelector('.diag-list .diag') ||
              (document.querySelector('.state') && !document.querySelector('.state').textContent.includes('加载中')),
        null, { timeout: 10000 });
      const diags = await page.locator('.diag-list .diag').count();
      const emptyState = diags === 0 ? await page.locator('.state').textContent().catch(() => '') : '';
      const called = apiCalls.some(u => u.includes('/api/health'));
      record('四个视图完整迁移-4', called && (diags > 0 || emptyState.includes('健康')),
        `诊断条目=${diags}${diags === 0 ? `（空态文案="${emptyState.trim()}"）` : ''}，/api/health 被调用=${called}`);
    }

    // ---- 契约 7：主题一致性-1（浅色背景 + 深色文字）----
    await page.click('nav a[role="tab"]:has-text("总览")');
    await page.waitForSelector('.verdict', { timeout: 5000 });
    {
      const { bg, color } = await page.evaluate(() => {
        const cs = getComputedStyle(document.body);
        return { bg: cs.backgroundColor, color: cs.color };
      });
      const [bgr, txt] = [parseRgb(bg), parseRgb(color)];
      const isLight = (bgr[0] + bgr[1] + bgr[2]) / 3 > 128;
      const isDarkText = (txt[0] + txt[1] + txt[2]) / 3 < 128;
      record('主题一致性-1', isLight && isDarkText, `body 背景=${bg}（浅色=${isLight}），文字=${color}（深色=${isDarkText}）`);
    }

    // ---- 契约 8：无障碍-1（键盘 Tab 可聚焦 + 可见焦点 + 语义结构）----
    {
      await page.keyboard.press('Tab');
      const focused = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const cs = getComputedStyle(el);
        return { tag: el.tagName, role: el.getAttribute('role'), text: (el.textContent || '').trim().slice(0, 12), outline: cs.outlineStyle, outlineW: cs.outlineWidth };
      });
      const tabs = await page.locator('nav a[role="tab"][aria-selected]').count();
      const mainRole = await page.locator('main[role="main"]').count();
      const focusVisible = focused && focused.outline !== 'none' && parseFloat(focused.outlineW) > 0;
      record('无障碍-1', !!focusVisible && tabs === 4 && mainRole === 1,
        `Tab 首焦点=${JSON.stringify(focused)}（可见焦点=${!!focusVisible}），role=tab 导航项=${tabs}/4，main 语义=${mainRole}`);
    }

    // ---- 契约 9：无障碍-2（正文对比度 ≥4.5:1 + reduced-motion 降级）----
    {
      const { bg, color } = await page.evaluate(() => {
        const cs = getComputedStyle(document.body);
        return { bg: cs.backgroundColor, color: cs.color };
      });
      const ratio = contrast(parseRgb(color), parseRgb(bg));
      // reduced-motion：检查构建产物 CSS 是否含降级规则
      const cssFile = readdirSync(join(REPO, 'gui/dist/assets')).find(f => f.endsWith('.css'));
      const css = cssFile ? await import('node:fs').then(m => m.readFileSync(join(REPO, 'gui/dist/assets', cssFile), 'utf8')) : '';
      const hasRM = css.includes('prefers-reduced-motion');
      record('无障碍-2', ratio >= 4.5 && hasRM,
        `正文对比度=${ratio.toFixed(2)}:1（≥4.5 要求），prefers-reduced-motion 降级=${hasRM}`);
    }

    // ---- 契约 11：概念字段对齐-1（显示 boost，无 weight/importance 残留）----
    {
      await page.click('nav a[role="tab"]:has-text("记忆浏览")');
      await page.waitForSelector('.mem-list .mem', { timeout: 5000 });
      const metaTexts = await page.locator('.mem .mmeta').allTextContents();
      const hasBoost = metaTexts.some(t => /^boost\s+[\d.]+$/.test(t.trim()));
      const hasUndefined = metaTexts.some(t => /undefined|weight|importance/i.test(t));
      // 构建产物 JS 中不得有语义字段 weight/importance 引用（font-weight 是合法 CSS，排除）
      const jsFile = readdirSync(join(REPO, 'gui/dist/assets')).find(f => f.endsWith('.js'));
      const js = await import('node:fs').then(m => m.readFileSync(join(REPO, 'gui/dist/assets', jsFile), 'utf8'));
      const jsBad = /\bm\.weight\b|\bmeta\.weight\b|has_importance|"importance"/.test(js);
      record('概念字段对齐-1', hasBoost && !hasUndefined && !jsBad,
        `卡片显示 boost=${hasBoost}（样例="${(metaTexts[0] || '').trim()}"），undefined/weight/importance 残留=${hasUndefined}，构建 JS 语义残留=${jsBad}`);
    }

    // ---- 契约 12：写操作口子预留-1（文案「当前只读」，无终态表述）----
    {
      const bodyText = await page.evaluate(() => document.body.innerText);
      const hasCurrent = bodyText.includes('当前只读');
      const hasPending = bodyText.includes('写/编辑待开放') || bodyText.includes('写·编辑待开放');
      const hasBad = bodyText.includes('永久只读') || bodyText.includes('写操作未开放');
      record('写操作口子预留-1', hasCurrent && hasPending && !hasBad,
        `「当前只读」=${hasCurrent}，「写/编辑待开放」=${hasPending}，终态表述（永久只读/写操作未开放）=${hasBad}`);
    }

    // ---- 契约 10：响应式布局-1（320px 单列、无横向滚动、导航可触达）----
    {
      await page.setViewportSize({ width: 320, height: 640 });
      await page.waitForTimeout(300);
      const { scrollW, clientW, cols, navVisible, navCount } = await page.evaluate(() => {
        const app = document.querySelector('.app');
        const nav = document.querySelector('nav .nav, nav.nav');
        const r = nav ? nav.getBoundingClientRect() : null;
        return {
          scrollW: document.documentElement.scrollWidth,
          clientW: document.documentElement.clientWidth,
          cols: getComputedStyle(app).gridTemplateColumns,
          navVisible: r ? r.width > 0 && r.height > 0 : false,
          navCount: document.querySelectorAll('nav a[role="tab"]').length,
        };
      });
      const singleCol = !cols.includes(' ') || cols.split(' ').filter(c => parseFloat(c) > 40).length <= 1;
      const noHScroll = scrollW <= clientW + 1;
      record('响应式布局-1', singleCol && noHScroll && navVisible && navCount === 4,
        `320px：grid 列="${cols}"（单列=${singleCol}），横向滚动=${!noHScroll}（scrollW=${scrollW} clientW=${clientW}），导航可见=${navVisible} 项数=${navCount}`);
    }
  } finally {
    await browser.close();
  }

  const failed = results.filter(r => !r.pass);
  console.log(`\n===== 验收汇总：${results.length - failed.length}/${results.length} 通过 =====`);
  if (failed.length) {
    console.log('失败项：');
    failed.forEach(f => console.log(`  - ${f.id}: ${f.evidence}`));
    process.exit(1);
  }
  process.exit(0);
}

main().catch(e => { console.error('验收脚本执行错误：', e); process.exit(2); });

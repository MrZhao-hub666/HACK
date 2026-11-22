<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { api, ApiError, clock, errorMessage, safeLink, stamp, toast } from "../shared";
import type { BuyerRecommendation, BuyerRecommendations } from "../types";
import Icon from "./Icon.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";
import SourceMarkdown from "./SourceMarkdown.vue";
import { vDismissOnBackdrop } from "./dismissOnBackdrop";

const grades = { A: "优先核实", B: "值得跟进", C: "待补依据" };
const feed = ref<BuyerRecommendations | null>(null);
const loading = ref(false);
const error = ref("");
const direction = ref("");
const grade = ref("");
const filtersOpen = ref(false);
const showAll = ref(false);
const dialog = ref<HTMLDialogElement | null>(null);
const selected = ref<BuyerRecommendation | null>(null);
const previewCount = 3;
const filtered = computed(() =>
  (feed.value?.items ?? []).filter(
    (item) =>
      (!direction.value || item.direction === direction.value) &&
      (!grade.value || item.grade === grade.value),
  ),
);
const path = "/discovery/recommendations";

function sourceName(item: BuyerRecommendation) {
  const url = safeLink(item.url);
  return item.source === "实时网页搜索" && url
    ? new URL(url).hostname.replace(/^www\./, "")
    : item.source;
}

async function openDetail(item: BuyerRecommendation) {
  selected.value = item;
  await nextTick();
  dialog.value?.showModal();
}

async function load(manual = false) {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    if (!manual) feed.value = await api<BuyerRecommendations>(path);
    const current = feed.value;
    if (current?.configured && (manual || current.auto_due)) {
      feed.value = await api<BuyerRecommendations>(
        path + "/refresh" + (manual ? "" : "?automatic=true"),
        "POST",
      );
      if (manual) {
        if (feed.value.error) toast("推荐更新失败", "error");
        else if (feed.value.notice) toast("本轮网页推荐未更新", "info");
        else toast("推荐已更新");
      }
    }
  } catch (e) {
    if (manual && e instanceof ApiError && e.status === 409) {
      toast(e.message, "info");
      return;
    }
    error.value = errorMessage(e);
    if (manual) toast("推荐更新失败", "error");
  } finally {
    loading.value = false;
  }
}

watch([direction, grade], () => { showAll.value = false; });
onMounted(() => load());
watch(clock, () => { if (!document.hidden) load(); });
</script>

<template>
  <section class="panel recommendations" aria-labelledby="buyer-recommendations-title">
    <div class="panelhead">
      <div class="sect">
        <icon name="spark" class="heading-icon" />
        <h2 id="buyer-recommendations-title">潜在客户推荐</h2>
      </div>
      <div class="recommendation-actions">
        <button
          class="textbtn"
          type="button"
          :aria-expanded="filtersOpen"
          aria-controls="buyer-recommendation-filters"
          @click="filtersOpen = !filtersOpen"
        >{{ direction || grade ? "已筛选" : "筛选" }}</button>
        <button
          class="icon-btn"
          type="button"
          aria-label="更新推荐"
          :title="feed && !feed.configured ? '网页推荐需配置实时搜索' : '更新推荐'"
          :disabled="loading || (!!feed && !feed.configured)"
          @click="load(!!feed)"
        >
          <icon name="refresh" size="sm" />
        </button>
      </div>
    </div>
    <div
      v-show="filtersOpen"
      id="buyer-recommendation-filters"
      class="recommendation-toolbar"
    >
      <label>
        方向
        <select v-model="direction">
          <option value="">全部方向</option>
          <option v-for="value in feed?.directions" :key="value" :value="value">{{ value }}</option>
        </select>
      </label>
      <label>
        优先级
        <select v-model="grade">
          <option value="">全部等级</option>
          <option v-for="(label, value) in grades" :key="value" :value="value">
            {{ value }} · {{ label }}
          </option>
        </select>
      </label>
      <small v-if="feed?.updated">网页推荐更新于 {{ stamp(feed.updated) }}</small>
      <small v-else-if="feed && !feed.configured">网页推荐需配置实时搜索</small>
    </div>
    <div v-if="error || feed?.error || feed?.notice" class="notice" :role="error || feed?.error ? 'alert' : 'status'">
      {{ error || feed?.error || feed?.notice }}
      <span v-if="feed?.updated">网页卡片来自上次成功检索。</span>
    </div>
    <LoadingSkeleton
      v-if="loading && !filtered.length"
      layout="lines"
      label="正在读取潜在客户推荐"
    />
    <p v-else-if="!filtered.length && feed" class="empty">
      {{ feed.items.length ? "当前筛选没有推荐线索" : "暂无符合商用车业务的推荐线索" }}
    </p>
    <div v-else-if="filtered.length" class="recommendation-list">
      <button
        v-for="item in (showAll ? filtered : filtered.slice(0, previewCount))"
        :key="item.id"
        class="recommendation-row"
        type="button"
        aria-haspopup="dialog"
        @click="openDetail(item)"
      >
        <strong class="recommendation-title" :title="item.title">{{ item.title }}</strong>
        <span class="recommendation-meta">
          <span class="tag" :class="{ amber: item.grade === 'A', blue: item.grade === 'B' }">
            {{ item.grade }} 级
          </span>
          <span>{{ item.direction }}</span>
          <span class="recommendation-source">来源 · {{ sourceName(item) }}</span>
        </span>
        <icon name="chevron" size="sm" class="recommendation-chevron" />
      </button>
    </div>
    <div class="recommendation-footer">
      <button
        v-if="filtered.length > previewCount"
        class="textbtn"
        type="button"
        @click="showAll = !showAll"
      >
        {{ showAll ? "收起列表" : "全部 " + filtered.length + " 条推荐" }}
      </button>
      <a href="#discovery">买家发现 <icon name="chevron" size="sm" /></a>
    </div>
    <dialog
      ref="dialog"
      v-dismiss-on-backdrop
      class="dialogwrap"
      aria-labelledby="buyer-recommendation-detail-title"
    >
      <div v-if="selected" class="dialog recommendation-dialog">
        <div class="recommendation-dialog-header">
          <h2 id="buyer-recommendation-detail-title">{{ selected.title }}</h2>
          <button
            type="button"
            class="icon-btn"
            aria-label="关闭详情"
            autofocus
            @click="dialog?.close()"
          ><icon name="close" size="sm" /></button>
        </div>
        <div class="recommendation-detail">
          <div class="recommendation-meta">
            <span class="tag" :class="{ amber: selected.grade === 'A', blue: selected.grade === 'B' }">
              {{ selected.grade }} 级 · {{ grades[selected.grade] }}
            </span>
            <span>{{ selected.direction }}</span>
            <span v-if="selected.market">目标市场 {{ selected.market }}</span>
            <span v-if="selected.published">{{ stamp(selected.published) }}</span>
          </div>
          <p>{{ selected.reason }}</p>
          <SourceMarkdown :text="selected.evidence" :source-url="selected.url" />
        </div>
        <div class="recommendation-detail-source">
          <small>来源 · {{ sourceName(selected) }}</small>
          <a v-if="safeLink(selected.url)" :href="safeLink(selected.url)" target="_blank" rel="noopener noreferrer">
            查看原文 <icon name="external" size="sm" />
          </a>
        </div>
      </div>
    </dialog>
  </section>
</template>

<style scoped>
.recommendations .panelhead {
  min-height: 48px;
  padding-block: var(--space-8);
}
.recommendation-actions,
.recommendation-meta,
.recommendation-detail-source,
.recommendation-footer {
  display: flex;
  align-items: center;
  gap: var(--space-8);
}
.recommendation-actions .icon-btn {
  width: 30px;
  height: 30px;
}
.recommendation-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-8) var(--space-16);
  padding: var(--space-8) var(--space-20);
  border-bottom: 1px solid var(--divider);
}
.recommendation-toolbar label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-8);
  color: var(--ink-secondary);
}
.recommendation-toolbar small { color: var(--muted); }
.recommendations .empty {
  min-height: 0;
  padding: var(--space-12) var(--space-20);
}
.recommendation-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--space-12);
  width: 100%;
  min-height: 39px;
  border: 0;
  padding: var(--space-4) var(--space-20);
  background: transparent;
  color: var(--ink);
  text-align: left;
  cursor: pointer;
}
.recommendation-row + .recommendation-row { border-top: 1px solid var(--divider); }
.recommendation-row:hover { background: var(--surface-hover); }
.recommendation-row:focus-visible { outline-offset: -2px; }
.recommendation-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: var(--type-label-medium);
}
.recommendation-meta {
  flex-wrap: wrap;
  min-width: 0;
  font: var(--type-caption);
  color: var(--ink-secondary);
}
.recommendation-source {
  color: var(--muted);
  overflow-wrap: anywhere;
}
.recommendation-chevron { color: var(--muted); }
.recommendation-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: var(--space-12);
  max-height: calc(100dvh - 32px);
}
.recommendation-dialog-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-12);
  overflow-wrap: anywhere;
}
.recommendation-dialog-header button { flex: none; }
.recommendation-detail {
  overflow: auto;
  overflow-wrap: anywhere;
  font: var(--type-body);
  color: var(--ink-secondary);
}
.recommendation-detail p { margin: var(--space-8) 0; }
.recommendation-detail-source {
  justify-content: space-between;
  flex-wrap: wrap;
  border-top: 1px solid var(--divider);
  padding-top: var(--space-8);
  overflow-wrap: anywhere;
}
.recommendation-footer {
  border-top: 1px solid var(--divider);
  padding: var(--space-4) var(--space-20);
}
.recommendation-footer a,
.recommendation-detail-source a {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
  color: var(--blue);
  font: var(--type-label-medium);
}
.recommendation-footer a { margin-left: auto; }
@media (max-width: 650px) {
  .recommendation-toolbar,
  .recommendation-row,
  .recommendation-footer { padding-inline: var(--space-12); }
  .recommendation-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-4) var(--space-8);
    padding-block: var(--space-8);
  }
  .recommendation-meta { grid-column: 1 / -1; }
  .recommendation-chevron { grid-column: 2; grid-row: 1; }
}
</style>

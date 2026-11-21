<script setup lang="ts">
import LoadingSkeleton from "./LoadingSkeleton.vue";
import { computed, ref, watch } from "vue";
import { channels, age, api, errorMessage } from "../shared";
import { channelStyles, channelCounts } from "./workspace";
import Icon from "./Icon.vue";
import type { Company, InquiryRow, Metric, Page, Filter } from "../types";
import BuyerAnalytics from "./BuyerAnalytics.vue";

const props = defineProps<{
  rows: InquiryRow[];
  companies: Company[];
  queue: InquiryRow[];
  metrics: Metric[];
  actor: string;
  ready: boolean;
  loading: boolean;
}>();
const emit = defineEmits<{
  open: [id: number];
  navigate: [page: Page, filter?: Filter];
  brief: [];
}>();
const distribution = computed(() => channelCounts(props.rows));
type OutreachSummary = {
  fair_records: number;
  pending: number;
  linked_buyers: number;
  drafts: number;
};
const outreach = ref<OutreachSummary | null>(null),
  statsError = ref("");
const outreachMetrics = [
  { key: "fair_records", label: "已登记展会线索", unit: "条" },
  { key: "pending", label: "待核实来源记录", unit: "条" },
  { key: "linked_buyers", label: "核实并关联的企业", unit: "家" },
  { key: "drafts", label: "展位邀约草稿", unit: "封" },
] as const;
let requestId = 0;
async function refreshSummary() {
  const id = ++requestId;
  statsError.value = "";
  try {
    const summary = await api<OutreachSummary>("/outreach/summary");
    if (id === requestId) outreach.value = summary;
  } catch (e) {
    if (id === requestId) statsError.value = errorMessage(e);
  }
}
watch(
  () => [props.ready, props.companies] as const,
  () => {
    if (props.ready) refreshSummary();
  },
  { immediate: true },
);
const ring = computed(() => {
  let start = 0;
  const segments = distribution.value.map((entry) => {
    const end = start + (100 * entry.total) / props.rows.length;
    const gap =
      distribution.value.length > 1 ? Math.min(0.9, (end - start) / 3) : 0;
    const segment =
      entry.color +
      " " +
      start +
      "% " +
      (end - gap) +
      "%, var(--paper) " +
      (end - gap) +
      "% " +
      end +
      "%";
    start = end;
    return segment;
  });
  return segments.length
    ? "conic-gradient(" + segments.join(",") + ")"
    : "var(--neutral-pale)";
});
</script>

<template>
  <div class="overview">
    <section class="hero">
      <div class="hero-art" aria-hidden="true"></div>
      <div class="hero-copy">
        <div class="copilot-label">
          <icon name="spark" size="sm" /> SALES COPILOT
        </div>
        <h1>海外销售工作台</h1>
        <p v-if="ready">
          {{ actor }}，{{
            queue.length
              ? "当前有 " + queue.length + " 条业务询盘等待回复。"
              : "当前业务询盘已全部跟进。"
          }}
        </p>
        <p v-else>集中查看海外询盘、客户档案与跟进安排。</p>
        <button class="primary brief-button" @click="emit('brief')">
          <icon name="spark" size="sm" />查看跟进简报<icon
            name="arrow"
            size="sm"
          />
        </button>
      </div>
    </section>
    <BuyerAnalytics v-if="ready" :companies="companies" :rows="rows" />
    <LoadingSkeleton
      v-else-if="loading"
      layout="lines"
      label="正在加载客户经营统计"
    />
    <template v-if="loading || ready">
      <span v-if="loading" class="sr-only" role="status">正在加载业务概览</span>
      <div class="section-label">
        <h2>询盘跟进</h2>
        <small
          v-if="ready && rows.some((r) => r.origin.includes('模拟'))"
          class="meta"
          >含模拟来信</small
        >
      </div>
      <div class="metrics" :aria-busy="loading">
        <button
          v-for="m in metrics"
          :key="m.name"
          class="metric"
          @click="emit('navigate', m.page, m.filter)"
        >
          <span class="metric-head"
            ><span class="icon-tile" :class="m.tone"
              ><icon :name="m.icon" size="md" /></span
            >{{ m.name }}</span
          >
          <strong
            ><span
              v-if="loading"
              class="sk-shape sk-number"
              aria-hidden="true"
            ></span
            ><template v-else>{{ m.val }}</template></strong
          >
          <span class="metric-foot"
            >{{ m.desc }}<icon name="upRight" size="sm"
          /></span>
        </button>
      </div>
      <div class="overview-grid" :aria-busy="loading">
        <section class="panel priority-panel">
          <div class="panelhead">
            <div class="sect">
              <icon name="list" class="heading-icon" />
              <h2>优先跟进</h2>
            </div>
            <button
              class="textbtn more"
              @click="emit('navigate', 'inbox', '业务待回')"
            >
              查看全部<icon name="chevron" size="sm" />
            </button>
          </div>
          <div class="priority-head">
            <span>买家 / 来源</span><span>采购意图</span
            ><span class="priority-owner">负责人</span><span>最近来信</span>
          </div>
          <LoadingSkeleton v-if="loading" layout="rows" />
          <button
            v-for="r in queue.slice(0, 5)"
            :key="r.id"
            class="priority-row"
            @click="emit('open', r.id)"
          >
            <span class="buyer-cell"
              ><span
                class="channel-tile"
                :class="channelStyles[r.channel]?.tone"
                ><icon :name="channelStyles[r.channel]?.icon" size="md"
              /></span>
              <span class="buyer-label"
                ><strong>{{ r.buyer }}</strong
                ><small>{{ channels[r.channel] }} · {{ r.origin }}</small></span
              ></span
            >
            <span
              ><span
                class="tag"
                :class="{
                  navy: r.intent === '询型匹配',
                  blue: r.intent === '索取目录',
                  amber: r.intent === '采购询价',
                }"
                >{{ r.intent }}</span
              ></span
            >
            <span class="priority-owner">{{ r.owner || "待认领" }}</span
            ><span class="row-trailing"
              >{{ age(r.last_in) }}前<icon name="chevron" size="sm"
            /></span>
          </button>
          <div v-if="ready && !queue.length" class="empty">
            <icon name="inbox" />暂无待回复的业务询盘
          </div>
        </section>
        <section class="panel distribution">
          <div class="panelhead">
            <div class="sect">
              <icon name="chart" class="heading-icon" />
              <h2>渠道分布</h2>
            </div>
            <small>按最近来信</small>
          </div>
          <LoadingSkeleton v-if="loading" layout="chart" />
          <template v-else>
            <div
              class="channel-chart"
              role="img"
              :aria-label="'询盘总数 ' + rows.length"
            >
              <div class="donut" :style="{ background: ring }">
                <div>
                  <strong>{{ rows.length }}</strong
                  ><span>询盘总数</span>
                </div>
              </div>
            </div>
            <div class="legend">
              <div v-for="c in distribution" :key="c.id">
                <i :style="{ background: c.color }"></i><span>{{ c.name }}</span
                ><b>{{ c.total }}</b>
              </div>
            </div>
            <p class="empty" v-if="!rows.length">收到询盘后显示渠道占比</p>
          </template>
        </section>
      </div>
      <section v-if="ready" class="panel outreach-summary">
        <div class="panelhead">
          <div class="sect">
            <icon name="calendar" class="heading-icon" />
            <h2>展会拓客进展</h2>
          </div>
          <button class="textbtn" @click="emit('navigate', 'outreach')">
            查看拓客记录 <icon name="chevron" size="sm" />
          </button>
        </div>
        <div v-if="statsError" class="notice" role="alert">
          {{ statsError }} <span v-if="outreach">当前显示上次读取的统计。</span
          ><button class="textbtn" @click="refreshSummary">重试拓客统计</button>
        </div>
        <dl v-if="outreach" class="outreach-totals">
          <div v-for="m in outreachMetrics" :key="m.key">
            <dt>{{ m.label }}</dt>
            <dd>
              {{ outreach[m.key] }} <small>{{ m.unit }}</small>
            </dd>
          </div>
        </dl>
        <LoadingSkeleton
          v-else-if="!statsError"
          layout="lines"
          label="正在加载拓客统计"
        />
      </section>
    </template>
  </div>
</template>
<style scoped>
.outreach-summary {
  margin-top: var(--space-16);
}
.outreach-totals {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: var(--space-16) var(--space-20);
  margin: 0;
  gap: var(--space-16);
}
.outreach-totals dt,
.outreach-totals small {
  font: var(--type-caption);
  color: var(--muted);
}
.outreach-totals dd {
  font: var(--type-headline-medium);
  margin: var(--space-4) 0 0;
}
.section-label {
  display: flex;
  gap: 12px;
  align-items: baseline;
}
@media (max-width: 650px) {
  .outreach-totals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

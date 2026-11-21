<script setup lang="ts">
import { computed, ref } from "vue";
import type { Company, InquiryRow } from "../types";
import { clock } from "../shared";
import Icon from "./Icon.vue";
import { percent, portfolio, type BuyerGroup } from "./portfolio";

const props = defineProps<{ companies: Company[]; rows: InquiryRow[] }>();
const stats = computed(() =>
  portfolio(props.companies, props.rows, clock.value),
);
const total = computed(() => props.companies.length);
const colors = ["#287469", "#4678a9", "#d48a32", "#9daabb"];
const labels: Record<string, string> = {
  A: "明确采购目标品类",
  B: "经营相邻品类",
  C: "仅核实企业身份",
  待评级: "尚无有效评级",
};
const kpiStyles = [
  { icon: "building", tone: "navy", note: "已存入档案的企业" },
  { icon: "addUser", tone: "teal", note: "北京时间 · 今日入档" },
  { icon: "check", tone: "amber", note: "销售已确认成交" },
  { icon: "userClock", tone: "blue", note: "档案尚无负责人" },
  { icon: "chat", tone: "violet", note: "有关联询盘正在跟进" },
] as const;
const windowDays = ref<7 | 30>(7),
  allMarkets = ref(false),
  allSources = ref(false),
  showAges = ref(false);
const dimension = ref<"markets" | "kinds" | "procurement">("markets");
const dimensionGroups = computed(() => stats.value[dimension.value]);
const daily = computed(() => stats.value.days.slice(-windowDays.value));
const periodCount = computed(() =>
  daily.value.reduce((sum, g) => sum + g.buyers.length, 0),
);
const peak = computed(() =>
  Math.max(1, ...daily.value.map((g) => g.buyers.length)),
);
const ring = computed(() => {
  if (!total.value) return "var(--neutral-pale)";
  let n = 0;
  const stops = stats.value.grades.map((g, i) => {
    const start = n;
    n += g.buyers.length;
    return (
      colors[i] +
      " " +
      (100 * start) / total.value +
      "% " +
      (100 * n) / total.value +
      "%"
    );
  });
  return "conic-gradient(" + stops.join(",") + ")";
});
const dialog = ref<HTMLDialogElement | null>(null),
  selection = ref("");
const selected = computed(() =>
  [
    ...stats.value.kpis,
    ...dimensionGroups.value,
    ...stats.value.grades,
    ...stats.value.sources,
    ...stats.value.days,
    ...stats.value.ageBands,
  ].find((g) => g.key === selection.value),
);
function inspect(g: BuyerGroup) {
  selection.value = g.key;
  dialog.value?.showModal();
}
const selectedTitle = computed(() => {
  const group = selected.value;
  if (!group) return "客户明细";
  if (group.key.startsWith("grade:") && group.label !== "待评级")
    return group.label + " 级客户";
  if (group.key.startsWith("date:")) return group.label + " 入档客户";
  return group.label;
});
</script>
<template>
  <section class="buyer-analytics" aria-labelledby="portfolio-heading">
    <div class="analytics-heading">
      <h2 id="portfolio-heading">客户经营统计</h2>
      <a href="#companies">查看客户档案 <Icon name="chevron" size="sm" /></a>
    </div>
    <div class="customer-kpis">
      <button
        v-for="(g, i) in stats.kpis"
        :key="g.key"
        :class="['customer-kpi', kpiStyles[i].tone]"
        @click="inspect(g)"
        :aria-label="g.label + ' ' + g.buyers.length + ' 家，查看明细'"
      >
        <span class="kpi-label"
          ><Icon :name="kpiStyles[i].icon" size="md" />{{ g.label }}</span
        >
        <strong>{{ g.buyers.length.toLocaleString() }}</strong>
        <small>{{ kpiStyles[i].note }}</small>
      </button>
    </div>
    <div class="analytics-panels">
      <section class="panel">
        <div class="panelhead">
          <div class="sect">
            <Icon name="compass" class="heading-icon" />
            <h2>客户分布</h2>
          </div>
          <select
            v-model="dimension"
            class="dimension-select"
            aria-label="客户分布维度"
            @change="allMarkets = false"
          >
            <option value="markets">国家 / 地区</option>
            <option value="kinds">业务类型</option>
            <option value="procurement">采购能力</option>
          </select>
        </div>
        <div class="plot-body">
          <p v-if="!total" class="empty">客户入档后显示分布</p>
          <template v-else>
            <button
              v-for="g in allMarkets
                ? dimensionGroups
                : dimensionGroups.slice(0, 5)"
              :key="g.key"
              class="bar-item"
              @click="inspect(g)"
            >
              <span>{{ g.label }}</span
              ><span class="bar-track" aria-hidden="true"
                ><i :style="{ width: percent(g.buyers.length, total) }" /></span
              ><b>{{ g.buyers.length }} 家</b
              ><small>{{ percent(g.buyers.length, total) }}</small>
            </button>
            <button
              v-if="dimensionGroups.length > 5"
              class="textbtn plot-more"
              @click="allMarkets = !allMarkets"
            >
              {{
                allMarkets
                  ? "收起"
                  : "查看全部 " + dimensionGroups.length + " 项"
              }}
            </button>
          </template>
        </div>
      </section>
      <section class="panel">
        <div class="panelhead">
          <div class="sect">
            <Icon name="chart" class="heading-icon" />
            <h2>客户分级</h2>
          </div>
          <small>按产品匹配度</small>
        </div>
        <div class="grade-plot">
          <div
            class="grade-ring"
            :style="{ background: ring }"
            aria-hidden="true"
          >
            <span
              ><strong>{{ total }}</strong
              ><small>客户总数</small></span
            >
          </div>
          <div class="grade-legend">
            <button
              v-for="(g, i) in stats.grades"
              :key="g.key"
              @click="inspect(g)"
              :title="labels[g.label]"
            >
              <i :style="{ background: colors[i] }" /><span>{{
                g.label === "待评级" ? g.label : g.label + " 级"
              }}</span
              ><b>{{ g.buyers.length }} 家</b
              ><small>{{ percent(g.buyers.length, total) }}</small>
            </button>
          </div>
        </div>
      </section>
      <section class="panel">
        <div class="panelhead">
          <div class="sect">
            <Icon name="layers" class="heading-icon" />
            <h2>客户来源</h2>
          </div>
          <small>按首次入档来源</small>
        </div>
        <div class="plot-body origin-plot">
          <p v-if="!total" class="empty">客户入档后显示来源占比</p>
          <button
            v-for="g in allSources ? stats.sources : stats.sources.slice(0, 5)"
            :key="g.key"
            class="bar-item"
            @click="inspect(g)"
          >
            <span>{{ g.label }}</span
            ><span class="bar-track" aria-hidden="true"
              ><i :style="{ width: percent(g.buyers.length, total) }" /></span
            ><b>{{ g.buyers.length }} 家</b
            ><small>{{ percent(g.buyers.length, total) }}</small>
          </button>
          <button
            v-if="stats.sources.length > 5"
            class="textbtn plot-more"
            @click="allSources = !allSources"
          >
            {{
              allSources
                ? "收起"
                : "查看全部 " + stats.sources.length + " 种来源"
            }}
          </button>
        </div>
      </section>
      <section class="panel">
        <div class="panelhead">
          <div class="sect">
            <Icon name="calendar" class="heading-icon" />
            <h2>客户入档趋势</h2>
          </div>
          <div class="period-switch" aria-label="入档时间统计">
            <button
              v-for="n in [7, 30] as const"
              :key="n"
              :aria-pressed="!showAges && windowDays === n"
              @click="
                windowDays = n;
                showAges = false;
              "
            >
              近{{ n }}天</button
            ><button :aria-pressed="showAges" @click="showAges = true">
              档龄
            </button>
          </div>
        </div>
        <div v-if="showAges" class="plot-body origin-plot">
          <button
            v-for="g in stats.ageBands"
            :key="g.key"
            class="bar-item"
            @click="inspect(g)"
          >
            <span>{{ g.label }}</span
            ><span class="bar-track" aria-hidden="true"
              ><i :style="{ width: percent(g.buyers.length, total) }" /></span
            ><b>{{ g.buyers.length }} 家</b
            ><small>{{ percent(g.buyers.length, total) }}</small>
          </button>
        </div>
        <div v-else class="plot-body">
          <div class="trend-summary">
            <strong>{{ periodCount }}</strong
            ><span>家新增</span>
          </div>
          <div
            class="daily-plot"
            :style="{
              gridTemplateColumns: 'repeat(' + windowDays + ',minmax(0,1fr))',
            }"
            aria-label="每日入档客户"
          >
            <button
              v-for="g in daily"
              :key="g.key"
              @click="inspect(g)"
              :title="g.label + ' · ' + g.buyers.length + ' 家'"
              :aria-label="g.label + ' 入档 ' + g.buyers.length + ' 家'"
            >
              <i :style="{ height: (100 * g.buyers.length) / peak + '%' }" />
            </button>
          </div>
          <div class="trend-axis">
            <small>{{ daily[0].label.slice(5) }}</small
            ><small>{{ daily[daily.length - 1].label.slice(5) }}</small>
          </div>
          <button
            v-if="stats.undated.buyers.length"
            class="textbtn undated"
            @click="inspect(stats.undated)"
          >
            {{ stats.undated.buyers.length }} 家旧档案入档时间未知，未计入趋势
          </button>
        </div>
      </section>
    </div>
    <dialog
      ref="dialog"
      class="dialogwrap"
      aria-labelledby="analytics-detail-title"
    >
      <div class="dialog stats-detail">
        <div class="line">
          <h2 id="analytics-detail-title">{{ selectedTitle }}</h2>
          <button class="ghost" @click="dialog?.close()">关闭明细</button>
        </div>
        <p class="meta">{{ selected?.buyers.length || 0 }} 家客户</p>
        <a
          v-for="c in selected?.buyers"
          :key="c.id"
          :href="'#companies?id=' + c.id"
          @click="dialog?.close()"
          ><strong>{{ c.name }}</strong
          ><span
            >{{ c.country || "地区未登记" }} · {{ c.owner || "待分配" }}
            <Icon name="chevron" size="sm" /></span
        ></a>
        <p v-if="!selected?.buyers.length" class="empty">
          当前没有符合条件的客户。
        </p>
      </div>
    </dialog>
  </section>
</template>
<style scoped>
.buyer-analytics {
  margin: 20px 0 25px;
  min-width: 0;
}
.analytics-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.analytics-heading h2 {
  font: var(--type-title-large);
  margin: 0;
}
.analytics-heading a {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--blue);
  font: var(--type-label-medium);
}
.customer-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.customer-kpi {
  --accent: #29456d;
  --wash: #eef3fa;
  display: grid;
  align-content: start;
  gap: 7px;
  text-align: left;
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: linear-gradient(120deg, var(--wash), var(--paper));
  padding: 14px 16px;
  box-shadow: var(--elevation-card);
  cursor: pointer;
}
.customer-kpi.teal {
  --accent: #176e63;
  --wash: #e6f4ef;
}
.customer-kpi.amber {
  --accent: #965212;
  --wash: #fff1d9;
}
.customer-kpi.blue {
  --accent: #305f9e;
  --wash: #e7f0ff;
}
.customer-kpi.violet {
  --accent: #66528d;
  --wash: #f1ecfa;
}
.customer-kpi:hover {
  border-color: var(--accent);
}
.kpi-label {
  display: flex;
  gap: 8px;
  align-items: center;
  color: var(--accent);
  font: var(--type-label);
}
.customer-kpi strong,
.trend-summary strong {
  font: var(--type-headline-medium);
  font-variant-numeric: tabular-nums;
}
.customer-kpi small,
.grade-plot small,
.plot-body small,
.trend-summary span {
  font: var(--type-caption);
  color: var(--muted);
}
.analytics-panels {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.analytics-panels .panel {
  margin: 0;
  min-width: 0;
}
.plot-body {
  padding: 16px 20px;
}
.bar-item {
  display: grid;
  grid-template-columns: minmax(65px, 1fr) minmax(40px, 1.65fr) auto 49px;
  align-items: center;
  gap: 9px;
  width: 100%;
  text-align: left;
  min-height: 34px;
  border: 0;
  background: transparent;
  padding: 4px 0;
  color: var(--ink);
  font: var(--type-body);
  cursor: pointer;
}
.bar-item b,
.grade-legend b {
  font: var(--type-label-medium);
  white-space: nowrap;
}
.bar-item small,
.grade-legend small {
  text-align: right;
}
.bar-track {
  height: 8px;
  width: 100%;
  background: var(--surface-subtle);
  border-radius: 8px;
  overflow: hidden;
}
.bar-track i {
  display: block;
  height: 100%;
  background: #4b80ac;
  border-radius: 8px;
}
.origin-plot .bar-track i {
  background: #4b9187;
}
.plot-more,
.undated {
  margin-top: 10px;
}
.grade-plot {
  display: flex;
  align-items: center;
  justify-content: space-evenly;
  gap: 20px;
  padding: 18px 20px;
}
.grade-ring {
  width: 118px;
  aspect-ratio: 1;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex: none;
}
.grade-ring > span {
  width: 77%;
  aspect-ratio: 1;
  background: var(--paper);
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.grade-ring strong {
  font: var(--type-headline-medium);
}
.grade-legend {
  flex: 1;
  max-width: 290px;
}
.grade-legend button {
  display: grid;
  grid-template-columns: 8px minmax(41px, 1fr) auto 45px;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 0;
  border: 0;
  background: transparent;
  text-align: left;
  color: var(--ink);
  font: var(--type-body);
  cursor: pointer;
}
.grade-legend i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.bar-item:hover,
.grade-legend button:hover,
.stats-detail a:hover {
  background: var(--surface-hover);
}
.period-switch {
  display: flex;
  background: var(--surface-subtle);
  border-radius: 6px;
  padding: 2px;
}
.dimension-select {
  width: auto;
  min-height: 28px;
  padding: 2px 6px;
  font: var(--type-caption);
  color: var(--ink-secondary);
}
.period-switch button {
  font: var(--type-caption);
  background: transparent;
  border: 0;
  border-radius: 5px;
  padding: 5px 9px;
  color: var(--muted);
  cursor: pointer;
}
.period-switch button[aria-pressed="true"] {
  background: var(--navy);
  color: white;
}
.trend-summary {
  display: flex;
  gap: 7px;
  align-items: baseline;
}
.daily-plot {
  height: 64px;
  display: grid;
  align-items: end;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(
    to top,
    transparent 49%,
    var(--divider) 50%,
    transparent 51%
  );
}
.daily-plot button {
  height: 100%;
  padding: 0 10%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  cursor: pointer;
  border: none;
  background: transparent;
  min-width: 0;
}
.daily-plot button:hover,
.daily-plot button:focus-visible {
  background: var(--surface-selected);
}
.daily-plot i {
  width: 100%;
  max-width: 28px;
  background: #5187aa;
  border-radius: 3px 3px 0 0;
}
.trend-axis,
.stats-detail a {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.trend-axis {
  margin-top: 4px;
}
.stats-detail {
  min-width: min(460px, 80vw);
}
.stats-detail .line {
  justify-content: space-between;
}
.stats-detail a {
  padding: 10px 0;
  align-items: center;
  color: var(--ink);
  border-bottom: 1px solid var(--divider);
  text-decoration: none;
  overflow-wrap: anywhere;
}
.stats-detail a span {
  color: var(--muted);
  font: var(--type-caption);
}
@media (max-width: 1050px) {
  .customer-kpi {
    padding: 12px;
  }
  .grade-plot {
    gap: 10px;
  }
  .grade-ring {
    width: 94px;
  }
}
@media (max-width: 800px) {
  .customer-kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .analytics-panels {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 500px) {
  .customer-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .customer-kpi:last-child {
    grid-column: 1 / -1;
    grid-template-columns: auto 1fr;
    align-items: center;
    column-gap: 12px;
  }
  .customer-kpi:last-child strong {
    grid-column: 2;
    grid-row: 1 / 3;
    text-align: right;
  }
  .plot-body,
  .grade-plot {
    padding: 12px;
  }
  .grade-ring {
    width: 100px;
  }
  .analytics-heading h2 {
    font: var(--type-title-large);
  }
  .analytics-panels {
    gap: 12px;
  }
}
</style>

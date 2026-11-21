<script setup lang="ts">
import { computed } from "vue";
import { channels, age } from "../shared";
import { channelStyles, channelCounts } from "./workspace";
import Icon from "./Icon.vue";
import type { InquiryRow, Metric, Page, Filter } from "../types";

const props = defineProps<{
  rows: InquiryRow[];
  queue: InquiryRow[];
  metrics: Metric[];
  actor: string;
  ready: boolean;
}>();
const emit = defineEmits<{
  open: [id: number];
  navigate: [page: Page, filter?: Filter];
  brief: [];
}>();
const distribution = computed(() => channelCounts(props.rows));
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
      "%, white " +
      (end - gap) +
      "% " +
      end +
      "%";
    start = end;
    return segment;
  });
  return segments.length
    ? "conic-gradient(" + segments.join(",") + ")"
    : "#ececf5";
});
</script>

<template>
  <div class="overview">
    <section class="hero">
      <div class="hero-art" aria-hidden="true"></div>
      <div class="hero-copy">
        <div class="copilot-label">
          <icon name="spark" :size="14" /> SALES COPILOT
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
          <icon name="spark" :size="16" />查看跟进简报<icon
            name="arrow"
            :size="15"
          />
        </button>
      </div>
    </section>
    <div class="section-label"><h2>业务概览</h2></div>
    <div class="metrics">
      <button
        v-for="m in metrics"
        :key="m.name"
        class="metric"
        @click="emit('navigate', m.page, m.filter)"
      >
        <span class="metric-head"
          ><span class="icon-tile" :class="m.tone"
            ><icon :name="m.icon" :size="17" /></span
          >{{ m.name }}</span
        >
        <strong>{{ ready ? m.val : "—" }}</strong>
        <span class="metric-foot"
          >{{ m.desc }}<icon name="upRight" :size="14"
        /></span>
      </button>
    </div>
    <div class="overview-grid">
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
            查看全部<icon name="chevron" :size="14" />
          </button>
        </div>
        <div class="priority-head">
          <span>买家 / 来源</span><span>采购意图</span
          ><span class="priority-owner">负责人</span><span>最近来信</span>
        </div>
        <button
          v-for="r in queue.slice(0, 5)"
          :key="r.id"
          class="priority-row"
          @click="emit('open', r.id)"
        >
          <span class="buyer-cell"
            ><span class="channel-tile" :class="channelStyles[r.channel]?.tone"
              ><icon :name="channelStyles[r.channel]?.icon" :size="17"
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
            >{{ age(r.last_in) }}前<icon name="chevron" :size="13"
          /></span>
        </button>
        <div v-if="!queue.length" class="empty">
          <icon name="inbox" />{{
            ready ? "暂无待回复的业务询盘" : "等待读取询盘"
          }}
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
        <div
          class="channel-chart"
          role="img"
          :aria-label="'询盘总数 ' + (ready ? rows.length : '未知')"
        >
          <div class="donut" :style="{ background: ring }">
            <div>
              <strong>{{ ready ? rows.length : "—" }}</strong
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
        <p class="empty" v-if="ready && !rows.length">收到询盘后显示渠道占比</p>
      </section>
    </div>
  </div>
</template>

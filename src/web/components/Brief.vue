<script setup lang="ts">
import AlternativeCard from "./AlternativeCard.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";
import { ref, computed } from "vue";
import { stamp } from "../shared";
import Icon from "./Icon.vue";
import type { Alternative, Company, InquiryRow } from "../types";

const props = defineProps<{
  alternatives: Alternative[];
  live: boolean;
  queue: InquiryRow[];
  rows: InquiryRow[];
  companies: Company[];
  actor: string;
  ready: boolean;
  failed: string;
}>();
const emit = defineEmits<{
  open: [id: number];
  company: [id: number];
  reload: [];
}>();
const dialog = ref<HTMLDialogElement | null>(null),
  topic = ref("优先跟进");
const topics = ["优先跟进", "我的交接", "客户核实", "替代买家"];
const mine = computed(() =>
  props.rows.filter((r) => r.owner === props.actor && r.state !== "已结束"),
);
const pending = computed(() =>
  props.companies.filter((c) => c.procurement === "待核实"),
);
const cards = computed(() => {
  if (topic.value === "客户核实")
    return pending.value.map((c) => ({
      id: c.id,
      title: c.name,
      label: c.country || "地区待核实",
      detail: c.next_action || "核实企业能否直接采购制动片。",
      source: c.source,
    }));
  const priority = topic.value === "优先跟进";
  return (priority ? props.queue : mine.value).map((r) => ({
    id: r.id,
    title: r.buyer,
    label: priority && r.night_unanswered ? "夜间待回" : r.state,
    detail: r.next_action || "阅读客户原文并确认下一步。",
    source: "#" + r.id + " · " + r.intent + " · " + stamp(r.last_in),
  }));
});
const summary = computed(() => {
  if (topic.value === "客户核实")
    return "有 " + pending.value.length + " 家企业的采购能力待核实。";
  if (topic.value === "我的交接")
    return props.actor + "名下有 " + mine.value.length + " 条未结束的询盘。";
  return (
    "共 " +
    props.queue.length +
    " 条业务询盘待回。先处理夜间来信，同组内较早的来信排在前面。"
  );
});
function show(preferAlternatives = false) {
  topic.value = preferAlternatives ? "替代买家" : "优先跟进";
  dialog.value?.showModal();
}
function close() {
  dialog.value?.close();
}
defineExpose({ show });
</script>

<template>
  <dialog
    ref="dialog"
    class="brief-drawer"
    aria-labelledby="brief-title"
    @click="$event.target === dialog && close()"
  >
    <div class="drawer-inner">
      <div class="drawer-heading">
        <span class="assistant-symbol"><icon name="spark" size="lg" /></span>
        <div>
          <small>SALES COPILOT</small>
          <h2 id="brief-title">销售跟进简报</h2>
        </div>
        <button class="icon-btn close" aria-label="关闭简报" @click="close">
          <icon name="close" />
        </button>
      </div>
      <div class="brief-tabs">
        <button
          v-for="t in topics"
          :key="t"
          @click="topic = t"
          :aria-pressed="topic === t"
        >
          {{ t
          }}<span v-if="t === '替代买家' && alternatives.length">
            · {{ alternatives.length }}</span
          >
        </button>
      </div>
      <div v-if="failed" class="notice" role="alert">
        {{ failed }}
        <button class="textbtn" @click="emit('reload')">重试</button>
      </div>
      <div v-if="ready && topic === '替代买家'" class="brief-result">
        <AlternativeCard
          v-for="r in alternatives"
          :key="r.inquiry_id + '-' + r.id"
          :item="r"
          :actor="actor"
          :live="live"
          show-origin
          @changed="emit('reload')"
          @open="
            close();
            emit('open', $event);
          "
          @company="
            close();
            emit('company', $event);
          "
        />
        <div v-if="!alternatives.length" class="empty">
          <Icon name="compass" />暂无待处理推荐。可从询盘详情查找替代买家。
        </div>
      </div>
      <div v-else-if="ready" :key="topic" class="brief-result">
        <div class="brief-summary">
          <small><icon name="spark" size="sm" />本地工作台摘要</small>
          <p>{{ summary }}</p>
        </div>
        <button
          v-for="c in cards"
          :key="c.id"
          class="brief-card"
          @click="
            close();
            topic === '客户核实' ? emit('company', c.id) : emit('open', c.id);
          "
        >
          <span class="line"
            ><strong>{{ c.title }}</strong
            ><span class="tag blue">{{ c.label }}</span></span
          >
          <span>{{ c.detail }}</span
          ><small>{{ c.source }}<icon name="arrow" size="sm" /></small>
        </button>
        <div v-if="!cards.length" class="empty">
          <icon name="check" />当前没有此类待办
        </div>
      </div>
      <LoadingSkeleton
        v-else-if="!failed"
        layout="rows"
        label="正在加载跟进简报"
      />
    </div>
  </dialog>
</template>

<script setup lang="ts">
import LoadingSkeleton from "./components/LoadingSkeleton.vue";
import { ref, computed, onMounted, onUnmounted } from "vue";
import Inbox from "./components/Inbox.vue";
import Discovery from "./components/Discovery.vue";
import Outreach from "./components/Outreach.vue";
import Companies from "./components/Companies.vue";
import Simulator from "./components/Simulator.vue";
import Overview from "./components/Overview.vue";
import WorkspaceNav from "./components/WorkspaceNav.vue";
import Brief from "./components/Brief.vue";
import {
  filters,
  matchesFilter,
  navPages,
  prioritize,
} from "./components/workspace";
import { api, clock, notify as notice, toast, errorMessage } from "./shared";
import Icon from "./components/Icon.vue";
import type {
  Company,
  Config,
  Filter,
  InquiryRow,
  Alternative,
  Metric,
  User,
  Page,
} from "./types";

const props = defineProps<{ user: User }>();
const emit = defineEmits<{ account: [] }>();
const descriptions = {
  inbox: "阅读各渠道来信、分派负责人，接续每一次跟进。",
  discovery: "查找企业和社交渠道采购线索，核实来源与采购能力。",
  outreach: "检索展会买家与采购原帖，整理展位邀约名单。",
  companies: "维护企业资料，记录采购角色与下一步行动。",
  simulator: "模拟渠道来信，检查询盘接收、归并与去重。",
  manual: "将原渠道收到的消息补入询盘队列。",
};
function readRoute(): { page: Page; filter: Filter; id: number } {
  const [id, query] = location.hash.slice(1).split("?");
  const params = new URLSearchParams(query);
  return {
    page:
      navPages.find((n) => n.id === (id === "domestic" ? "discovery" : id))?.id ??
      "overview",
    filter: filters.find((f) => f === params.get("filter")) ?? "全部",
    id: Number(params.get("id")) || 0,
  };
}
const route = ref(readRoute()),
  rows = ref<InquiryRow[]>([]),
  alternatives = ref<Alternative[]>([]),
  companies = ref<Company[]>([]);
const config = ref<Config>({
  team: [],
  intents: [],
  demo: false,
  llm: false,
  live_search: false,
  receivers: [],
});
const actor = computed(() => props.user.display_name);
const failed = ref(""),
  ready = ref(false),
  refreshing = ref(false);
const brief = ref<InstanceType<typeof Brief> | null>(null),
  outreach = ref<InstanceType<typeof Outreach> | null>(null),
  mobileNav = ref<HTMLDialogElement | null>(null);
const page = computed(() => route.value.page);
const title = computed(() => navPages.find((n) => n.id === page.value)?.name);
const today = computed(() =>
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(clock.value),
);
const queue = computed(() => prioritize(rows.value));
const metrics = computed<Metric[]>(() => [
  {
    name: "待回复询盘",
    val: queue.value.length,
    icon: "inbox",
    tone: "orange",
    desc: "有效业务来信",
    page: "inbox",
    filter: "业务待回",
  },
  {
    name: "夜间待回",
    val: rows.value.filter((r) => matchesFilter(r, "夜间待回")).length,
    icon: "moon",
    tone: "blue",
    desc: "北京夜班 20:00 – 08:00",
    page: "inbox",
    filter: "夜间待回",
  },
  {
    name: "尚待认领",
    val: rows.value.filter((r) => matchesFilter(r, "待认领")).length,
    icon: "userClock",
    tone: "slate",
    desc: "等待分配负责人",
    page: "inbox",
    filter: "待认领",
  },
  {
    name: "已结束询盘",
    val: rows.value.filter((r) => matchesFilter(r, "已结束")).length,
    icon: "check",
    tone: "ice",
    desc: "已结束的跟进事项",
    page: "inbox",
    filter: "已结束",
  },
]);
let generation = 0;
async function reload(manual = false) {
  const seq = ++generation;
  refreshing.value = true;
  if (!ready.value) failed.value = "";
  try {
    const [r, c, conf, feed] = await Promise.all([
      api<InquiryRow[]>("/inquiries"),
      api<Company[]>("/companies"),
      api<Config>("/config"),
      api<Alternative[]>("/alternatives/mine"),
    ]);
    if (seq !== generation) return;
    rows.value = r;
    companies.value = c;
    config.value = conf;
    alternatives.value = feed;
    ready.value = true;
    failed.value = "";
    if (manual === true) {
      await outreach.value?.refresh();
      toast("数据已刷新");
    }
  } catch (e) {
    if (seq === generation) failed.value = errorMessage(e);
  } finally {
    if (seq === generation) refreshing.value = false;
  }
}
function go(id: Page, filter?: Filter | null, recordId?: number) {
  mobileNav.value?.close();
  const q = new URLSearchParams();
  if (filter && filter !== "全部") q.set("filter", filter);
  if (recordId) q.set("id", String(recordId));
  location.hash = id + (q.size ? "?" + q : "");
}
const inboxVisit = ref(0);
function showBrief(preferAlternatives = false) {
  mobileNav.value?.close();
  brief.value?.show(preferAlternatives);
}
async function focus(id: number) {
  if (!rows.value.some((r) => r.id === id)) await reload();
  if (page.value === "inbox" && route.value.id === id) inboxVisit.value++;
  go("inbox", null, id);
}
function hash() {
  route.value = readRoute();
  window.scrollTo(0, 0);
}
let timer: ReturnType<typeof setInterval>;
defineExpose({ reload });
onMounted(() => {
  reload();
  addEventListener("hashchange", hash);
  timer = setInterval(() => {
    clock.value = Date.now();
    if (!document.hidden) reload();
  }, 30000);
});
onUnmounted(() => {
  clearInterval(timer);
  removeEventListener("hashchange", hash);
});
</script>

<template>
  <div class="shell">
    <aside class="sidebar desktop-nav">
      <WorkspaceNav
        :page="page"
        :waiting="queue.length"
        :recommendations="alternatives.length"
        :user="user"
        @go="go"
        @account="
          mobileNav?.close();
          emit('account');
        "
        @brief="showBrief(alternatives.length > 0)"
      />
    </aside>
    <dialog
      ref="mobileNav"
      class="mobile-nav"
      aria-label="工作台导航"
      @click="$event.target === mobileNav && mobileNav?.close()"
    >
      <div class="sidebar">
        <button
          class="icon-btn menu-close"
          aria-label="关闭导航"
          @click="mobileNav?.close()"
        >
          <icon name="close" />
        </button>
        <WorkspaceNav
          :page="page"
          :waiting="queue.length"
          :recommendations="alternatives.length"
          :user="user"
          @go="go"
          @account="
            mobileNav?.close();
            emit('account');
          "
          @brief="showBrief(alternatives.length > 0)"
        />
      </div>
    </dialog>
    <main>
      <header class="topbar">
        <div class="crumb" :class="{ 'home-crumb': page === 'overview' }">
          <button
            class="icon-btn menu-btn"
            aria-label="打开导航"
            @click="mobileNav?.showModal()"
          >
            <icon name="menu" />
          </button>
          <img
            v-if="page === 'overview'"
            class="mobile-logo"
            src="/assets/kooying-logo.png"
            alt="KOOYING 冠英"
            width="119"
          />
          <icon class="crumb-home" name="layers" size="sm" /><span
            class="crumb-parent"
            >海外业务</span
          ><span class="crumb-sep">/</span><b>{{ title }}</b>
        </div>
        <div class="top-actions">
          <span class="date"
            ><icon name="calendar" size="sm" />{{ today }}</span
          >
          <button
            class="icon-btn refresh"
            aria-label="刷新数据"
            title="刷新数据"
            :disabled="refreshing"
            @click="reload(true)"
          >
            <icon name="refresh" size="sm" />
          </button>
          <button
            v-if="page !== 'manual'"
            class="primary compose"
            @click="go('manual')"
          >
            <icon name="plus" size="sm" />补录询盘
          </button>
        </div>
      </header>
      <div class="content" :key="page">
        <div v-if="failed" class="notice" role="alert">
          {{ ready ? "数据刷新失败，当前显示上次读取的结果。" : ""
          }}{{ failed }}
          <button class="textbtn" @click="reload(true)">重试</button>
        </div>
        <Overview
          v-if="page === 'overview'"
          :companies="companies"
          :rows="rows"
          :queue="queue"
          :metrics="metrics"
          :actor="actor"
          :ready="ready"
          :loading="!ready && !failed"
          @navigate="go"
          @open="focus"
          @brief="showBrief"
        />
        <template v-else>
          <div class="pageheading">
            <div>
              <h1>{{ title }}</h1>
              <p>{{ descriptions[page] }}</p>
            </div>
          </div>
          <template v-if="ready">
            <Inbox
              v-if="page === 'inbox'"
              :key="'inbox-' + route.id + '-' + route.filter + '-' + inboxVisit"
              :rows="rows"
              :companies="companies"
              :actor="actor"
              :config="config"
              :focus-id="route.id"
              :initial-filter="route.filter"
              @reload="reload"
              @compose="go('manual')"
              @company="go('companies', null, $event)"
            />
            <Discovery
              v-else-if="page === 'discovery'"
              :companies="companies"
              :config="config"
              @reload="reload"
              @open="focus"
              @company="go('companies', null, $event)"
            />
            <Companies
              v-else-if="page === 'companies'"
              :key="'companies-' + route.id"
              :team="config.team"
              :companies="companies"
              :focus-id="route.id"
              @reload="reload"
              @dismiss="route.id && go('companies')"
            />
            <Outreach v-else-if="page === 'outreach'" ref="outreach" :focus-id="route.id" @reload="reload" />
            <Simulator
              v-else
              :key="page"
              :config="config"
              :manual="page === 'manual'"
              @reload="reload"
              @open="focus"
            />
          </template>
          <div v-else-if="!failed" class="panel" aria-busy="true">
            <div class="panelhead" aria-hidden="true">
              <span class="sk-shape sk-short"></span>
            </div>
            <LoadingSkeleton
              :layout="
                page === 'inbox'
                  ? 'inbox'
                  : page === 'companies'
                    ? 'cards'
                    : 'form'
              "
              :label="'正在加载' + title"
            />
          </div>
        </template>
      </div>
    </main>
    <Brief
      ref="brief"
      :live="config.live_search"
      :alternatives="alternatives"
      :queue="queue"
      :rows="rows"
      :companies="companies"
      :actor="actor"
      :ready="ready"
      :failed="failed"
      @open="focus"
      @company="go('companies', null, $event)"
      @reload="reload"
    />
    <Transition name="toast"
      ><div class="toast" v-if="notice" role="status">
        {{ notice }}
      </div></Transition
    >
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import Inbox from "./components/Inbox.vue";
import Discovery from "./components/Discovery.vue";
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
  Metric,
  User,
  Page,
} from "./types";

const props = defineProps<{ user: User }>();
const emit = defineEmits<{ account: [] }>();
const descriptions = {
  inbox: "阅读海外来信、分派负责人，接续每一次跟进。",
  discovery: "按目标市场寻找买家，核查业务证据与采购能力。",
  companies: "维护企业资料，记录采购角色与下一步行动。",
  simulator: "模拟渠道来信，检查询盘接收、归并与去重。",
  manual: "将原渠道收到的消息补入询盘队列。",
};
function readRoute(): { page: Page; filter: Filter; id: number } {
  const [id, query] = location.hash.slice(1).split("?");
  const params = new URLSearchParams(query);
  return {
    page: navPages.find((n) => n.id === id)?.id ?? "overview",
    filter: filters.find((f) => f === params.get("filter")) ?? "全部",
    id: Number(params.get("id")) || 0,
  };
}
const route = ref(readRoute()),
  rows = ref<InquiryRow[]>([]),
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
    name: "客户档案",
    val: companies.value.length,
    icon: "building",
    tone: "ice",
    desc: "已存档的企业",
    page: "companies",
  },
]);
let generation = 0;
async function reload(manual = false) {
  const seq = ++generation;
  refreshing.value = true;
  try {
    const [r, c, conf] = await Promise.all([
      api<InquiryRow[]>("/inquiries"),
      api<Company[]>("/companies"),
      api<Config>("/config"),
    ]);
    if (seq !== generation) return;
    rows.value = r;
    companies.value = c;
    config.value = conf;
    ready.value = true;
    failed.value = "";
    if (manual === true) toast("数据已刷新");
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
function showBrief() {
  mobileNav.value?.close();
  brief.value?.show();
}
async function focus(id: number) {
  if (!rows.value.some((r) => r.id === id)) await reload();
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
        :user="user"
        @go="go"
        @account="
          mobileNav?.close();
          emit('account');
        "
        @brief="showBrief"
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
          :user="user"
          @go="go"
          @account="
            mobileNav?.close();
            emit('account');
          "
          @brief="showBrief"
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
          :rows="rows"
          :queue="queue"
          :metrics="metrics"
          :actor="actor"
          :ready="ready"
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
              :key="'inbox-' + route.id + '-' + route.filter"
              :rows="rows"
              :companies="companies"
              :actor="actor"
              :config="config"
              :focus-id="route.id"
              :initial-filter="route.filter"
              @reload="reload"
              @compose="go('manual')"
            />
            <Discovery
              v-else-if="page === 'discovery'"
              :companies="companies"
              :config="config"
              @reload="reload"
            />
            <Companies
              v-else-if="page === 'companies'"
              :key="'companies-' + route.id"
              :companies="companies"
              :focus-id="route.id"
              @reload="reload"
              @dismiss="route.id && go('companies')"
            />
            <Simulator
              v-else
              :key="page"
              :config="config"
              :manual="page === 'manual'"
              @reload="reload"
              @open="focus"
            />
          </template>
          <div v-else-if="!failed" class="panel empty">正在读取工作台…</div>
        </template>
      </div>
    </main>
    <Brief
      ref="brief"
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

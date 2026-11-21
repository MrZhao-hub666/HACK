import {
  createApp,
  ref,
  computed,
  onMounted,
  onUnmounted,
  watch,
} from "./vendor/vue.esm-browser.prod.js";
import Inbox from "./components/Inbox.js";
import Discovery from "./components/Discovery.js";
import Companies from "./components/Companies.js";
import Simulator from "./components/Simulator.js";
import {
  api,
  clock,
  overnight,
  relevant,
  notify,
  toast,
  Icon,
} from "./shared.js";
import template from "./app-template.js";

const nav = [
  { id: "inbox", name: "询盘收件箱", icon: "inbox" },
  { id: "discovery", name: "买家发现", icon: "compass" },
  { id: "companies", name: "客户档案", icon: "users" },
  { id: "simulator", name: "渠道模拟器", icon: "radio" },
];
const descriptions = {
  inbox: "查看海外来信、分派负责人，接续每一次跟进。",
  discovery: "按目标市场寻找企业，核查业务证据与直接采购能力。",
  companies: "维护已筛选的企业、采购角色与下一步行动。",
  simulator: "回放评论、私信与表单事件，验证询盘接收和去重。",
  manual: "将尚未接通的渠道消息记入销售队列。",
};
const pageFromHash = () => {
  const id = location.hash.slice(1);
  return [...nav.map((x) => x.id), "manual"].includes(id) ? id : "inbox";
};
const app = createApp({
  components: { Inbox, Discovery, Companies, Simulator },
  template,
  setup() {
    const page = ref(pageFromHash()),
      rows = ref([]),
      companies = ref([]),
      config = ref({ team: ["林悦"], intents: [], demo: true }),
      actor = ref(localStorage.getItem("gy-actor") || "林悦"),
      failed = ref(""),
      focusId = ref(0),
      refreshing = ref(false);
    const title = computed(
      () => nav.find((x) => x.id === page.value)?.name || "补录渠道消息",
    );
    const subtitle = computed(() => descriptions[page.value]);
    const today = computed(() =>
      new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "full",
        timeZone: "Asia/Shanghai",
      }).format(clock.value),
    );
    const open = computed(() => rows.value.filter((r) => r.state !== "已结束"));
    const waiting = computed(
      () => open.value.filter((r) => r.unanswered && relevant(r)).length,
    );
    const metrics = computed(() => [
      {
        name: "待回复询盘",
        val: waiting.value,
        icon: "inbox",
        desc: "已识别的业务咨询",
      },
      {
        name: "夜间待回",
        val: open.value.filter((r) => overnight(r) && relevant(r)).length,
        icon: "moon",
        desc: "最近夜班 · 北京时间 20–08 时",
      },
      {
        name: "尚待认领",
        val: open.value.filter((r) => !r.owner).length,
        icon: "clock",
        desc: "等待销售接手",
      },
      {
        name: "客户档案",
        val: companies.value.length,
        icon: "users",
        desc: "已加入跟进名单的企业",
      },
    ]);
    let generation = 0;
    async function reload(manual = false) {
      const seq = ++generation;
      refreshing.value = true;
      try {
        const [r, c, conf] = await Promise.all([
          api("/inquiries"),
          api("/companies"),
          api("/config"),
        ]);
        if (seq !== generation) return;
        rows.value = r;
        companies.value = c;
        config.value = conf;
        failed.value = "";
        if (manual === true) toast("数据已刷新");
      } catch (e) {
        if (seq === generation) failed.value = e.message;
      } finally {
        if (seq === generation) refreshing.value = false;
      }
    }
    function go(id) {
      page.value = id;
      location.hash = id;
    }
    async function focus(id) {
      await reload();
      focusId.value = id;
      go("inbox");
    }
    const hash = () => {
      page.value = pageFromHash();
    };
    let timer;
    watch(actor, (v) => localStorage.setItem("gy-actor", v));
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
    return {
      page,
      nav,
      rows,
      companies,
      config,
      actor,
      failed,
      focusId,
      refreshing,
      waiting,
      title,
      subtitle,
      today,
      metrics,
      notice: notify,
      reload,
      go,
      focus,
    };
  },
});
app.component("icon", Icon);
app.mount("#app");

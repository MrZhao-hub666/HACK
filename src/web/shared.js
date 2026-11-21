import { ref } from "./vendor/vue.esm-browser.prod.js";
export const channels = {
  messenger: "Messenger",
  facebook_comment: "Facebook 评论",
  facebook_form: "Facebook 表单",
  wechat_kf: "微信客服",
  wechat_comment: "视频号评论",
  manual: "线下 / 其他",
};
export const kinds = [
  "待识别",
  "车队",
  "维修厂",
  "维修及配件",
  "配件门店",
  "贸易商",
  "渠道伙伴",
];
export const states = ["待处理", "跟进中", "等客户补充", "已结束"];
export const purchases = ["待核实", "可直接采购", "委托采购", "仅转售"];
export const clock = ref(Date.now());
export const stamp = (s) =>
  s
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).format(new Date(s))
    : "—";
export function age(s) {
  const mins = Math.max(0, Math.floor((clock.value - Date.parse(s)) / 60000));
  return mins < 60 ? mins + " 分钟" : Math.floor(mins / 60) + " 小时";
}
export const overnight = (row) => Boolean(row.night_unanswered);
export function relevant(row) {
  return !["一般互动", "待判断"].includes(row.intent);
}
export async function api(path, method = "GET", data) {
  let res;
  try {
    res = await fetch("/api" + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
  } catch {
    throw Error("无法连接服务，请检查网络后重试");
  }
  const out = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw Error(
      typeof out.detail === "string"
        ? out.detail
        : "提交失败，请检查必填字段与数据格式",
    );
  }
  return out;
}
export const blankCompany = () => ({
  name: "",
  country: "",
  kind: "待识别",
  procurement: "待核实",
  website: "",
  social: "",
  contact: "",
  evidence: "",
  evidence_url: "",
  notes: "",
  next_action: "",
});
export const notify = ref("");
let notificationTimer;
export function toast(message) {
  notify.value = message;
  clearTimeout(notificationTimer);
  notificationTimer = setTimeout(() => (notify.value = ""), 4800);
}
export function safeLink(url) {
  try {
    const u = new URL(url);
    return ["http:", "https:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
export const Icon = {
  props: { name: String, size: { default: 18 } },
  template:
    '<svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.box"/></svg>',
  setup() {
    return {
      paths: {
        inbox: "M3 13l3-8h12l3 8v6H3z M3 13h5l2 3h4l2-3h5",
        compass:
          "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M16 8l-2.5 5.5L8 16l2.5-5.5z",
        users:
          "M15 20v-2a5 5 0 0 0-10 0v2 M10 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M16 5a3 3 0 0 1 0 6 M18 14a4 4 0 0 1 3 4v2",
        radio:
          "M7 7a7 7 0 0 0 0 10 M17 7a7 7 0 0 1 0 10 M4 4a11 11 0 0 0 0 16 M20 4a11 11 0 0 1 0 16 M14 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
        search: "M16 16l5 5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
        clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2",
        arrow: "M5 12h14 M13 6l6 6-6 6",
        external: "M14 4h6v6 M19 5l-9 9 M11 5H5v14h14v-6",
        plus: "M12 5v14 M5 12h14",
        globe:
          "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c-5 4-5 14 0 18 5-4 5-14 0-18",
        check: "M4 12l5 5L20 6",
        moon: "M20 14a8 8 0 0 1-10-11A9 9 0 1 0 21 14z",
        layers: "M12 3l9 5-9 5-9-5z M3 12l9 5 9-5 M3 16l9 5 9-5",
        box: "M4 4h16v16H4z",
        back: "M19 12H5 M10 7l-5 5 5 5",
        refresh:
          "M20 5v6h-6 M4 19v-6h6 M5 9a8 8 0 0 1 14-3l1 5 M4 13l1 5a8 8 0 0 0 14-3",
        list: "M8 6h13 M8 12h13 M8 18h13 M3 6h1 M3 12h1 M3 18h1",
      },
    };
  },
};

import { ref } from "vue";
import type { Channel, CompanyFields, InquiryRow } from "./types";
export const channels: Record<Channel, string> = {
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
export const stamp = (s?: string | null) =>
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
export function age(s: string) {
  const mins = Math.max(0, Math.floor((clock.value - Date.parse(s)) / 60000));
  if (mins < 60) return mins + " 分钟";
  if (mins < 1440) return Math.floor(mins / 60) + " 小时";
  return Math.floor(mins / 1440) + " 天";
}
export const overnight = (row: InquiryRow) => Boolean(row.night_unanswered);
export function relevant(row: InquiryRow) {
  return !["一般互动", "待判断"].includes(row.intent);
}
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
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
export const blankCompany = (): CompanyFields => ({
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
let notificationTimer: ReturnType<typeof setTimeout>;
export function toast(message: string) {
  notify.value = message;
  clearTimeout(notificationTimer);
  notificationTimer = setTimeout(() => (notify.value = ""), 4800);
}
export function safeLink(url: string) {
  try {
    const u = new URL(url);
    return ["http:", "https:"].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "操作失败，请重试";
}

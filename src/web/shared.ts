import { computed, ref } from "vue";
import type { Channel, CompanyFields, ContactProfile, InquiryRow } from "./types";
export const channels: Record<Channel, string> = {
  dy: "抖音评论",
  xhs: "小红书评论",
  messenger: "Messenger",
  facebook_comment: "Facebook 评论",
  facebook_form: "Facebook 表单",
  whatsapp: "WhatsApp 商业号码",
  instagram: "Instagram 私信",
  x_dm: "X 私信",
  x_post: "X 提及与回复",
  tiktok: "TikTok 企业私信",
  telegram: "Telegram 机器人",
  line: "LINE 官方账号",
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
  "批发进口商", "经销代理商", "车桥厂", "OEM采购商", "ODM采购商",
];
export const states = ["待处理", "跟进中", "等客户补充", "已结束"];
export const purchases = ["待核实", "可直接采购", "委托采购", "仅转售"];
export const contactGenders: Record<ContactProfile["contact_gender"], string> = {
  女: "女",
  男: "男",
  其他: "其他",
  不便透露: "不便透露",
  "": "未登记",
};
export const contactAgeBands: Record<ContactProfile["contact_age_band"], string> = {
  under25: "24 岁及以下",
  "25-34": "25–34 岁",
  "35-44": "35–44 岁",
  "45-54": "45–54 岁",
  "55-64": "55–64 岁",
  "65+": "65 岁及以上",
  "": "未登记",
};
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
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
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
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-Workspace-Request": "1",
      },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
  } catch {
    throw Error("无法连接服务，请检查网络后重试");
  }
  const out = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && !["/auth/login", "/auth/me"].includes(path))
      window.dispatchEvent(new Event("workspace-session-invalid"));
    throw new ApiError(
      res.status,
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
export type ToastTone = "success" | "info" | "warning" | "error";
const notification = ref<{ message: string; tone: ToastTone } | null>(null);
export const notify = computed(() => notification.value);
let notificationTimer: ReturnType<typeof setTimeout>;
export function clearToast() {
  clearTimeout(notificationTimer);
  notification.value = null;
}
export function toast(message: string, tone: ToastTone = "success") {
  clearTimeout(notificationTimer);
  notification.value = { message, tone };
  notificationTimer = setTimeout(clearToast, tone === "warning" || tone === "error" ? 7000 : 4800);
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

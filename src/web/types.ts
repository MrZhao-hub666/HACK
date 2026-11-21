import type { IconName } from "./icons";

export type Channel =
  | "messenger"
  | "facebook_comment"
  | "facebook_form"
  | "whatsapp"
  | "instagram"
  | "x_dm"
  | "x_post"
  | "tiktok"
  | "telegram"
  | "line"
  | "wechat_kf"
  | "wechat_comment"
  | "manual";
export type Page =
  | "overview"
  | "inbox"
  | "discovery"
  | "companies"
  | "simulator"
  | "manual";
export type Filter =
  | "全部"
  | "未回复"
  | "业务待回"
  | "夜间待回"
  | "待认领"
  | "我的"
  | "已结束";
export type State = "待处理" | "跟进中" | "等客户补充" | "已结束";
export type Intent =
  | "采购询价"
  | "询型匹配"
  | "索取目录"
  | "售后咨询"
  | "一般互动"
  | "待判断";

export interface Config {
  team: string[];
  intents: Intent[];
  demo: boolean;
  live_search: boolean;
  llm: boolean;
  receivers: {
    id: string;
    name: string;
    configured: boolean;
    sync: { last_success: string | null; error: string } | null;
  }[];
}
export interface CompanyFields {
  name: string;
  country: string;
  kind: string;
  procurement: string;
  website: string;
  social: string;
  contact: string;
  evidence: string;
  evidence_url: string;
  notes: string;
  next_action: string;
}
export interface Candidate extends Omit<CompanyFields, "contact"> {
  contact?: string;
  source: string;
  checked: string;
}
export interface Company extends CompanyFields {
  owner: string;
  id: number;
  source: string;
  checked: string;
}
export interface DiscoveryResult {
  mode: "samples" | "live";
  query: string;
  items: Candidate[];
}
export interface Receipt {
  inquiry_id: number;
  duplicate: boolean;
}
interface Inquiry {
  id: number;
  buyer: string;
  owner: string;
  company_id: number | null;
  state: State;
  intent: Intent;
  next_action: string;
  created: string;
  last_in: string;
}
export interface InquiryRow extends Inquiry {
  company: string | null;
  channel: Channel;
  all_channels: string;
  unanswered: number;
  night_unanswered: number;
  preview: string;
  origin: string;
}
interface Features {
  codes: string[];
  quantities: string[];
  role: string;
  translation: string;
  language: string;
  engine: string;
  intent: Intent;
}
export interface Message {
  id: number;
  account: string;
  thread_key: string;
  event_id: string;
  at: string;
  origin: string;
  channel: Channel;
  body: string;
  attachment: string;
  features: Features;
}
export interface InquiryDetail extends Inquiry {
  alternatives: AlternativeBatch | null;
  messages: Message[];
  history: {
    id: number;
    action: string;
    actor: string;
    at: string;
    detail: string;
  }[];
}
export interface Metric {
  name: string;
  val: number;
  icon: IconName;
  tone: string;
  desc: string;
  page: Page;
  filter?: Filter;
}

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "sales";
  active: boolean;
  must_change: boolean;
}
export interface Session {
  user: User;
  expires_at: number;
}

export interface Alternative {
  id: number;
  inquiry_id: number;
  source_name: string;
  source_url: string;
  owner: string;
  profile: Omit<Candidate, "notes">;
  decision: "pending" | "adopted";
  reason: string;
  archive_id: number | null;
  archive_owners: string[];
  proof: { url: string; note: string; actor: string; at: string } | null;
}
export interface AlternativeBatch {
  inquiry_id: number;
  source_company_id: number;
  generated_at: string;
  mode: "local" | "live";
  query: string;
  items: Alternative[];
}

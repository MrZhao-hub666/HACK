import type { Company } from "./types";

export const sources = [
  "上海法兰克福",
  "广交会",
  "社媒原帖",
  "企业采购资料",
] as const;
export type BuyerSource = (typeof sources)[number];
export interface Signal {
  source: BuyerSource;
  edition: string;
  title: string;
  market: string;
  url: string;
  snippet: string;
}
export interface Evidence extends Signal {
  id: number;
  company_id: number | null;
  verdict: string;
  author: string;
  published: string;
  quote: string;
  fit: string;
  intent: string;
  reason: string;
  reviewer: string;
  updated: string;
}
export interface Buyer
  extends Pick<
    Company,
    | "id"
    | "name"
    | "country"
    | "kind"
    | "procurement"
    | "contact"
    | "website"
    | "social"
    | "owner"
  > {
  grade: string;
}
export interface ContactInput {
  kind: string;
  holder: string;
  value: string;
  url: string;
}
export interface Contact extends ContactInput {
  id: number;
  company_id: number;
  reviewer: string;
  updated: string;
}
export interface Draft {
  id: number;
  company_id: number;
  event: string;
  booth: string;
  starts: string;
  ends: string;
  subject: string;
  body: string;
  recipient: string;
  updated: string;
}
export interface OutreachData {
  buyers: Buyer[];
  evidence: Evidence[];
  contacts: Contact[];
  drafts: Draft[];
}

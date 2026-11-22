import type { Company, InquiryRow } from "../types";
import { contactAgeBands, contactGenders } from "../shared";

export interface BuyerGroup {
  key: string;
  label: string;
  buyers: Company[];
}

const dayMs = 86400000;
const cst = 8 * 3600000;
const localDay = (time: number) => Math.floor((time + cst) / dayMs);
const countryNames = new Intl.DisplayNames(["zh-CN"], { type: "region" });
const englishNames = new Intl.DisplayNames(["en"], { type: "region" });
const markets = new Map(
  [
    "MY",
    "CN",
    "US",
    "GB",
    "AE",
    "DE",
    "CH",
    "JP",
    "BR",
    "MX",
    "PH",
    "TH",
    "ID",
    "SG",
    "AU",
    "VN",
    "IN",
    "CA",
    "EG",
    "NG",
    "NL",
    "IQ",
    "YE",
    "UG",
    "IE",
    "ES",
    "KR",
    "FR",
  ].map((code) => [
    englishNames.of(code)!.toLowerCase(),
    countryNames.of(code)!,
  ]),
);
function countryName(country: string) {
  const value = country.trim();
  if (!value) return "地区未登记";
  if (/^[a-z]{2}$/i.test(value))
    return countryNames.of(value.toUpperCase()) || value;
  return markets.get(value.toLowerCase()) || value;
}

function groupBy(
  buyers: Company[],
  prefix: string,
  classify: (c: Company) => string,
  labels: string[] = [],
) {
  const map = new Map<string, Company[]>(labels.map((label) => [label, []]));
  for (const buyer of buyers) {
    const label = classify(buyer);
    if (!map.has(label)) map.set(label, []);
    map.get(label)!.push(buyer);
  }
  const groups = [...map].map(([label, members]) => ({
    key: prefix + label,
    label,
    buyers: members,
  }));
  if (labels.length) return groups;
  return groups.sort(
    (a, b) =>
      b.buyers.length - a.buyers.length ||
      a.label.localeCompare(b.label, "zh-CN"),
  );
}

export function portfolio(
  buyers: Company[],
  inquiries: InquiryRow[],
  now: number,
) {
  const day = localDay(now);
  const active = new Set(
    inquiries
      .filter((r) => r.company_id && ["跟进中", "等客户补充"].includes(r.state))
      .map((r) => r.company_id),
  );
  const days: BuyerGroup[] = Array.from({ length: 30 }, (_, i) => {
    const label = new Date((day - 29 + i) * dayMs).toISOString().slice(0, 10);
    return { key: "date:" + label, label, buyers: [] };
  });
  const undated: BuyerGroup = {
    key: "undated",
    label: "入档时间未知",
    buyers: [],
  };
  const ageBands: BuyerGroup[] = [
    "今天",
    "1–6 天",
    "7–29 天",
    "30–179 天",
    "180–364 天",
    "365 天及以上",
  ].map((label, i) => ({ key: "age:" + i, label, buyers: [] }));
  for (const buyer of buyers) {
    const time = buyer.archived_at ? Date.parse(buyer.archived_at) : NaN;
    if (!Number.isFinite(time)) {
      undated.buyers.push(buyer);
      continue;
    }
    const index = localDay(time) - day + 29;
    if (index >= 0 && index < 30) days[index].buyers.push(buyer);
    const age = day - localDay(time);
    if (age >= 0)
      ageBands[
        [0, 6, 29, 179, 364, Infinity].findIndex((limit) => age <= limit)
      ].buyers.push(buyer);
  }
  const kpis: BuyerGroup[] = [
    { key: "all", label: "全部客户", buyers },
    { key: "today", label: "今日新增", buyers: days[29].buyers },
    { key: "won", label: "已确认成交", buyers: buyers.filter((b) => b.won_at) },
    {
      key: "unassigned",
      label: "待分配客户",
      buyers: buyers.filter((b) => !b.owner.trim()),
    },
    {
      key: "following",
      label: "跟进中客户",
      buyers: buyers.filter((b) => active.has(b.id)),
    },
  ];
  return {
    kpis,
    days,
    undated,
    ageBands: [...ageBands, undated],
    markets: groupBy(buyers, "market:", (c) => countryName(c.country)),
    kinds: groupBy(buyers, "kind:", (c) => c.kind || "待识别"),
    procurement: groupBy(
      buyers,
      "procurement:",
      (c) => c.procurement || "待核实",
    ),
    grades: groupBy(buyers, "grade:", (c) => c.outreach_grade || "待评级", [
      "A",
      "B",
      "C",
      "待评级",
    ]),
    sources: groupBy(buyers, "source:", (c) => c.source || "来源未登记"),
    genders: groupBy(
      buyers,
      "contact-gender:",
      (c) => contactGenders[c.contact_gender ?? ""],
      Object.values(contactGenders),
    ).filter((g) => g.buyers.length),
    contactAges: groupBy(
      buyers,
      "contact-age:",
      (c) => contactAgeBands[c.contact_age_band ?? ""],
      Object.values(contactAgeBands),
    ).filter((g) => g.buyers.length),
  };
}

export const percent = (count: number, total: number) =>
  (total
    ? new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(
        (100 * count) / total,
      )
    : "0") + "%";

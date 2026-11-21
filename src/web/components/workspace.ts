import { channels, overnight, relevant } from "../shared";

import type { Channel, Filter, InquiryRow, Page } from "../types";
export const navigation: {
  title: string;
  pages: { id: Page; name: string; icon: string }[];
}[] = [
  {
    title: "工作空间",
    pages: [
      { id: "overview", name: "工作台总览", icon: "dashboard" },
      { id: "inbox", name: "询盘收件箱", icon: "inbox" },
      { id: "discovery", name: "买家发现", icon: "compass" },
      { id: "companies", name: "客户档案", icon: "building" },
    ],
  },
  {
    title: "渠道管理",
    pages: [
      { id: "simulator", name: "渠道模拟器", icon: "radio" },
      { id: "manual", name: "消息补录", icon: "pen" },
    ],
  },
];
export const navPages = navigation.flatMap((group) => group.pages);
export const channelStyles = {
  messenger: { color: "#284778", icon: "bolt", tone: "navy" },
  facebook_comment: { color: "#558ed3", icon: "message", tone: "blue" },
  facebook_form: { color: "#9fc4ea", icon: "form", tone: "ice" },
  wechat_kf: { color: "#ed8b31", icon: "chat", tone: "orange" },
  wechat_comment: { color: "#ab6344", icon: "chat", tone: "orange" },
  manual: { color: "#8997b3", icon: "pen", tone: "slate" },
};
export const filters: Filter[] = [
  "全部",
  "未回复",
  "业务待回",
  "夜间待回",
  "待认领",
  "我的",
  "已结束",
];
export function matchesFilter(row: InquiryRow, filter: Filter, actor = "") {
  const active = row.state !== "已结束";
  switch (filter) {
    case "未回复":
      return active && row.unanswered;
    case "业务待回":
      return active && row.unanswered && relevant(row);
    case "夜间待回":
      return active && overnight(row) && relevant(row);
    case "待认领":
      return active && !row.owner;
    case "我的":
      return row.owner === actor;
    case "已结束":
      return !active;
    default:
      return true;
  }
}
export function prioritize(rows: InquiryRow[]) {
  return rows
    .filter((r) => matchesFilter(r, "业务待回"))
    .sort(
      (a, b) =>
        Number(overnight(b)) - Number(overnight(a)) ||
        a.last_in.localeCompare(b.last_in) ||
        a.id - b.id,
    );
}
export function channelCounts(rows: InquiryRow[]) {
  const totals = new Map<Channel, number>();
  for (const row of rows)
    totals.set(row.channel, (totals.get(row.channel) || 0) + 1);
  return (Object.keys(channels) as Channel[])
    .map((id) => ({
      id,
      name: channels[id],
      total: totals.get(id) || 0,
      ...channelStyles[id],
    }))
    .filter((entry) => entry.total > 0)
    .sort((a, b) => b.total - a.total);
}

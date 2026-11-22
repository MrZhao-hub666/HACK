<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { api, ApiError, errorMessage, stamp, toast } from "../shared";
import type { DomesticLiveJob, DomesticSearchResult, DomesticSignal } from "../types";
import Icon from "./Icon.vue";

const emit = defineEmits<{
  reload: [];
  open: [id: number];
  company: [id: number];
}>();
const labels = { dy: "抖音", xhs: "小红书" };
const sessionKey = "domestic-search-job";
const stages = {
  queued: "排队中",
  running: "正在采集",
  login: "请在本机浏览器扫码登录",
  complete: "采集完成",
  failed: "采集失败",
};
const emptyMessages: Record<DomesticSearchResult["index_state"], string> = {
  indexed: "未找到匹配线索，可调整关键词或筛选条件。",
  awaiting_sync: "后端尚未同步渠道数据，当前没有可检索的线索。",
  unconfigured: "后端尚未接入渠道数据，当前没有可检索的线索。",
};
const q = ref(""),
  filter = ref("求购"),
  platform = ref("");
const items = ref<DomesticSignal[]>([]),
  total = ref(0),
  offset = ref(0),
  size = 20;
const busy = ref(false),
  searching = ref(false),
  searchMessage = ref(""),
  error = ref(""),
  activeId = ref(0);
const companyName = ref(""),
  country = ref("");
const job = ref<DomesticLiveJob | null>(null);
const searchId = ref("");
const pending = ref(sessionStorage.getItem(sessionKey) || "");
let closed = false;
async function action(work: () => Promise<void>, failureMessage = "") {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await work();
  } catch (e) {
    error.value = errorMessage(e);
    if (failureMessage) toast(failureMessage, "error");
  } finally {
    busy.value = false;
  }
}
async function results(start: number) {
  const params = new URLSearchParams({
    q: q.value.trim(),
    offset: String(start),
    limit: String(size),
    real_only: "true",
  });
  if (platform.value) params.set("platform", platform.value);
  if (filter.value) params.set("signal", filter.value);
  if (searchId.value) params.set("search_id", searchId.value);
  const res = await api<DomesticSearchResult>("/domestic/signals?" + params);
  items.value = res.items;
  total.value = res.total;
  offset.value = start;
  activeId.value = 0;
  searchMessage.value = searchId.value
    ? res.total
      ? `本次找到 ${res.total} 条线索。`
      : "本次采集没有符合筛选条件的线索。"
    : res.total
      ? `已同步 ${res.total} 条线索。`
      : emptyMessages[res.index_state];
}
function clearPending() {
  pending.value = "";
  sessionStorage.removeItem(sessionKey);
}
async function searchLive() {
  searching.value = true;
  items.value = [];
  total.value = 0;
  searchId.value = "";
  searchMessage.value = "";
  job.value = null;
  try {
    if (!pending.value) {
      const started = await api<DomesticLiveJob>("/domestic/searches", "POST", {
        id: crypto.randomUUID(),
        q: q.value,
        platform: platform.value || null,
      });
      pending.value = started.id;
      sessionStorage.setItem(sessionKey, started.id);
    }
    const path = "/domestic/searches/" + pending.value;
    while (!closed) {
      const status = await api<DomesticLiveJob>(path);
      if (closed) break;
      job.value = status;
      q.value = status.q;
      platform.value =
        status.channels.length === 1 ? status.channels[0].platform : "";
      if (status.status === "complete") {
        if (status.channels.some((channel) => channel.status === "complete")) {
          try {
            await api(path + "/import", "POST");
          } catch (e) {
            // A batch rejected for size or format cannot be imported unchanged.
            if (e instanceof ApiError && (e.status === 413 || e.status === 422)) {
              clearPending();
            }
            throw e;
          }
          searchId.value = status.id;
          await results(0);
        } else {
          searchMessage.value = "本次采集失败。";
          toast("本次渠道采集失败", "error");
        }
        clearPending();
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) clearPending();
    throw e;
  } finally {
    searching.value = false;
  }
}
function startAdopt(item: DomesticSignal) {
  activeId.value = item.id;
  companyName.value = "";
  country.value = "";
}
function adopt(item: DomesticSignal) {
  return action(async () => {
    const res = await api<{ company_id: number }>(
      `/domestic/signals/${item.id}/adopt`,
      "POST",
      { name: companyName.value, country: country.value },
    );
    item.company_id = res.company_id;
    activeId.value = 0;
    emit("reload");
    toast("已关联客户档案");
  }, "客户档案关联失败");
}
function toInbox(item: DomesticSignal) {
  return action(async () => {
    const res = await api<{ inquiry_id: number }>(
      `/domestic/signals/${item.id}/inquiry`,
      "POST",
    );
    item.inquiry_id = res.inquiry_id;
    emit("open", res.inquiry_id);
    toast("线索已进入询盘收件箱");
  }, "线索登记失败");
}
onMounted(() => action(pending.value ? searchLive : () => results(0)));
onUnmounted(() => { closed = true; });
</script>

<template>
  <section class="panel">
    <form class="formpad" @submit.prevent="action(searchLive, '渠道搜索失败')">
      <div class="fields">
        <label
          >关键词<input
            v-model.trim="q"
            required
            :disabled="searching"
            maxlength="180"
            placeholder="刹车片、车队或 WVA 编码"
        /></label>
        <label
          >来源平台<select v-model="platform" :disabled="searching">
            <option value="">全部平台</option>
            <option value="dy">抖音</option>
            <option value="xhs">小红书</option>
          </select></label
        >
        <label
          >内容意图<select
            v-model="filter"
            :disabled="searching"
            @change="action(() => results(0))"
          >
            <option value="">全部意图</option>
            <option>求购</option>
            <option>待判断</option>
            <option>供应推广</option>
          </select></label
        >
      </div>
      <div class="actions">
        <button class="primary" :disabled="busy">
          {{ searching ? "实时搜索中…" : "搜索线索" }}
        </button>
        <span class="hint" role="status">
          {{ searching && !job ? "正在启动实时搜索…" : searchMessage }}
        </span>
      </div>
      <ul v-if="job" class="search-progress" aria-live="polite">
        <li v-for="channel in job.channels" :key="channel.platform">
          {{ labels[channel.platform] }} · {{ stages[channel.status] }}
          <span v-if="channel.count != null">（{{ channel.count }} 条）</span>
          <span v-if="channel.error">{{ channel.error }}</span>
        </li>
      </ul>
    </form>
  </section>
  <div class="notice" role="alert" v-if="error">{{ error }}</div>
  <section v-if="items.length" class="panel" :aria-busy="busy">
    <div class="panelhead">
      <div class="sect">
        <h2>{{ searchId ? "本次实时搜索" : "已同步线索" }}</h2>
        <span class="count">{{ total }}</span>
      </div>
    </div>
    <div class="cards discovery-cards">
      <article
        v-for="item in items"
        :key="item.id"
        class="companycard domestic-card"
      >
        <div class="line">
          <strong
            >{{ labels[item.platform] }} ·
            {{ item.kind === "post" ? "作品" : "评论" }}</strong
          ><small>{{
            item.published ? stamp(item.published) : "时间未提供"
          }}</small>
        </div>
        <div class="tags">
          <span class="tag blue">{{ item.signal }}</span
          ><span class="tag" v-if="item.demo">测试样例</span
          ><span class="tag" v-if="item.owned">自有作品</span
          ><span
            class="tag"
            v-for="t in [...item.codes, ...item.quantities]"
            :key="t"
            >{{ t }}</span
          >
        </div>
        <p class="original">{{ item.body }}</p>
        <div v-if="item.parent_text" class="next">
          <b>所属作品</b> {{ item.parent_text.slice(0, 200) }}
        </div>
        <p class="hint" v-if="item.keyword">来源检索词 · {{ item.keyword }}</p>
        <div class="actions">
          <a
            v-if="item.source_url"
            :href="item.source_url"
            target="_blank"
            rel="noopener noreferrer"
            >查看原作品 <Icon name="external" size="sm"
          /></a>
          <button
            v-if="item.company_id"
            class="ghost"
            @click="emit('company', item.company_id)"
          >
            查看档案
          </button>
          <button
            v-else-if="!item.demo && item.id !== activeId"
            class="ghost"
            :disabled="busy"
            @click="startAdopt(item)"
          >
            核实并建档
          </button>
          <button
            v-if="item.inquiry_id"
            class="ghost"
            @click="emit('open', item.inquiry_id)"
          >
            查看询盘
          </button>
          <button
            v-else-if="item.owned"
            class="ghost"
            :disabled="busy"
            @click="toInbox(item)"
          >
            确认是客户来信
          </button>
        </div>
        <form v-if="item.id === activeId" @submit.prevent="adopt(item)">
          <label
            >已核实的企业名称<input
              required
              maxlength="200"
              v-model.trim="companyName"
          /></label>
          <label
            >企业所在国家或地区<input maxlength="80" v-model.trim="country"
          /></label>
          <div class="actions">
            <button class="primary" :disabled="busy">保存客户档案</button
            ><button type="button" class="ghost" @click="activeId = 0">
              取消
            </button>
          </div>
        </form>
      </article>
    </div>
    <div v-if="total > size" class="actions formpad">
      <button
        class="ghost"
        :disabled="busy || offset === 0"
        @click="action(() => results(offset - size))"
      >
        上一页
      </button>
      <span>{{ offset + 1 }}–{{ offset + items.length }} / {{ total }}</span>
      <button
        class="ghost"
        :disabled="busy || offset + size >= total"
        @click="action(() => results(offset + size))"
      >
        下一页
      </button>
    </div>
  </section>
</template>
<style scoped>
.search-progress {
  padding-left: 1.25em;
  margin: 0.75rem 0 0;
}
.domestic-card,
.domestic-card form {
  min-width: 0;
}
.domestic-card p,
.domestic-card .next {
  overflow-wrap: anywhere;
  white-space: pre-line;
}
.domestic-card form {
  display: grid;
  gap: 0.65rem;
}
.domestic-card form label {
  display: grid;
  gap: 0.25rem;
}
.domestic-card .actions {
  flex-wrap: wrap;
}
</style>

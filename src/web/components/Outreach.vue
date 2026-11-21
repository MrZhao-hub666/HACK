<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { api, errorMessage, safeLink, toast } from "../shared";
import {
  sources,
  type BuyerSource,
  type Evidence,
  type OutreachData,
  type Signal,
} from "../outreach-types";
import BuyerReview from "./BuyerReview.vue";
import OutreachBuyer from "./OutreachBuyer.vue";

const props = defineProps<{ focusId: number }>();
const emit = defineEmits<{ reload: [] }>();
const tab = ref("检索来源"),
  source = ref<BuyerSource>("上海法兰克福");
const search = ref({ keywords: "", market: "", edition: "", mode: "local" });
const results = ref<{ query: string; mode: string; items: Signal[] } | null>(
  null,
);
const data = ref<OutreachData>({
  evidence: [],
  buyers: [],
  contacts: [],
  drafts: [],
});
const reviewId = ref(0),
  buyerId = ref(0),
  grade = ref("全部"),
  query = ref(""),
  status = ref("全部");
const error = ref(""),
  busy = ref(false),
  initialized = ref(false);
const capture = ref<Signal | null>(null),
  importEdition = ref(""),
  file = ref<File | null>(null);
const selectedReview = computed(() =>
  data.value.evidence.find((e) => e.id === reviewId.value),
);
const buyer = computed(() =>
  data.value.buyers.find((b) => b.id === buyerId.value),
);
const records = computed(() =>
  data.value.evidence.filter(
    (e) => status.value === "全部" || e.verdict === status.value,
  ),
);
const buyers = computed(() =>
  data.value.buyers.filter(
    (b) =>
      (grade.value === "全部" || (b.grade || "待评级") === grade.value) &&
      (b.name + b.country + b.kind)
        .toLowerCase()
        .includes(query.value.trim().toLowerCase()),
  ),
);
async function refresh() {
  data.value = await api<OutreachData>("/outreach");
  initialized.value = true;
}
async function act(fn: () => Promise<void>, failureMessage = "") {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = errorMessage(e);
    if (failureMessage) toast(failureMessage, "error");
  } finally {
    busy.value = false;
  }
}
async function lookup() {
  results.value = null;
  results.value = await api("/outreach/search", "POST", {
    ...search.value,
    source: source.value,
  });
}
watch(source, () => {
  results.value = null;
  capture.value = null;
  file.value = null;
  search.value.edition = "";
  if (search.value.mode === "bluesky") search.value.mode = "local";
});
function openBuyer(id: number) {
  if (!buyers.value.some((b) => b.id === id)) {
    grade.value = "全部";
    query.value = "";
  }
  buyerId.value = id;
  tab.value = "买家名单";
  nextTick(() =>
    document
      .getElementById("outreach-buyer")
      ?.scrollIntoView({ block: "start" }),
  );
}
function openReview(id: number) {
  reviewId.value = id;
  tab.value = "核实记录";
  nextTick(() =>
    document
      .getElementById("outreach-review")
      ?.scrollIntoView({ block: "start" }),
  );
}
async function afterReview(id: number | null) {
  await act(async () => {
    await refresh();
    emit("reload");
    if (id) openBuyer(id);
  });
}
function manual() {
  capture.value = {
    source: source.value,
    edition: search.value.edition,
    title: "",
    url: "",
    market: search.value.market,
    snippet: "",
  };
}
async function enter() {
  if (!capture.value) return;
  const item = await api<Evidence>("/outreach/evidence", "POST", capture.value);
  capture.value = null;
  toast("展会线索已登记");
  await refresh();
  openReview(item.id);
}
async function importFile() {
  if (!file.value) return;
  if (file.value.size > 1000000)
    throw Error("请选择小于 1 MB 的 UTF-8 CSV 文件");
  const csv_text = await file.value.text();
  const stats = await api<{ added: number; duplicates: number }>(
    "/outreach/import",
    "POST",
    { source: source.value, edition: importEdition.value, csv_text },
  );
  await refresh();
  tab.value = "核实记录";
  status.value = "全部";
  reviewId.value = 0;
  toast("新增 " + stats.added + " 条，重复 " + stats.duplicates + " 条");
}
function pickFile(ev: Event) {
  file.value = (ev.target as HTMLInputElement).files?.[0] || null;
}
watch(capture, (value) => {
  if (value)
    nextTick(() =>
      document
        .getElementById("outreach-capture")
        ?.scrollIntoView({ block: "start" }),
    );
});
defineExpose({ refresh });
onMounted(() =>
  act(async () => {
    await refresh();
    if (props.focusId) openBuyer(props.focusId);
    else await lookup();
  }),
);
watch(
  () => props.focusId,
  (id) => {
    if (id) openBuyer(id);
  },
);
</script>
<template>
  <div class="outreach">
    <nav class="out-tabs" aria-label="展会拓客流程">
      <button
        v-for="name in ['检索来源', '核实记录', '买家名单']"
        :key="name"
        class="ghost"
        :aria-pressed="tab === name"
        @click="
          tab = name;
          error = '';
        "
      >
        {{ name }}
      </button>
    </nav>
    <div v-if="error" class="notice" role="alert">
      {{ error }}
      <button v-if="!initialized" class="textbtn" @click="act(refresh)">
        重新加载
      </button>
    </div>
    <template v-if="tab === '检索来源'">
      <div class="panel formpad">
        <h2>查找展会买家与原帖</h2>
        <form @submit.prevent="act(lookup, '展会线索检索失败')">
          <fieldset :disabled="busy">
            <div class="fields">
              <label
                >来源<select aria-label="来源" v-model="source">
                  <option v-for="s in sources" :key="s">{{ s }}</option>
                </select></label
              >
              <label
                >检索范围<select v-model="search.mode" @change="results = null">
                  <option value="local">公开资料及已录入记录</option>
                  <option value="live">实时网页搜索</option>
                  <option v-if="source === '社媒原帖'" value="bluesky">
                    Bluesky 实时原帖
                  </option>
                </select></label
              >
              <label
                >市场<input
                  v-model.trim="search.market"
                  maxlength="80"
                  placeholder="全部市场"
              /></label>
              <label v-if="source === '上海法兰克福' || source === '广交会'"
                >届次<input
                  v-model.trim="search.edition"
                  maxlength="45"
                  placeholder="如 2025 或 第138届"
              /></label>
              <label
                >关键词<input
                  v-model.trim="search.keywords"
                  maxlength="150"
                  placeholder="企业名称、制动片、brake lining…"
              /></label>
            </div>
            <div class="actions">
              <button class="primary">
                {{ busy ? "处理中…" : "检索线索" }}</button
              ><button type="button" class="ghost" @click="manual">
                手动录入来源
              </button>
              <a
                v-if="source === '广交会'"
                href="https://activity.cantonfair.org.cn/cn/2024/VehiclesAccessories/sourcingRequest.html"
                target="_blank"
                rel="noopener noreferrer"
                >广交会官方采购需求 ↗</a
              >
            </div>
          </fieldset>
        </form>
        <details
          v-if="source === '上海法兰克福' || source === '广交会'"
          class="out-details"
        >
          <summary>导入本届买家 CSV</summary>
          <form @submit.prevent="act(importFile, '买家名单导入操作失败')">
            <p>
              使用有权导入的 UTF-8
              CSV。必填表头为「企业名称」「来源链接」，可选「市场」「来源说明」。每批最多
              500 条。
            </p>
            <div class="fields">
              <label
                >导入届次<input
                  required
                  maxlength="60"
                  v-model.trim="importEdition" /></label
              ><label
                >买家 CSV<input
                  required
                  type="file"
                  accept=".csv,text/csv"
                  @change="pickFile"
              /></label>
            </div>
            <button class="ghost" :disabled="busy || !file">
              导入待核实记录
            </button>
          </form>
        </details>
      </div>
      <form
        v-if="capture"
        id="outreach-capture"
        class="panel formpad"
        @submit.prevent="act(enter, '展会线索登记操作失败')"
      >
        <h2>登记待核实来源</h2>
        <div class="fields">
          <label
            >企业名或原帖标题<input
              v-model.trim="capture.title"
              required
              maxlength="200" /></label
          ><label
            >来源网址<input
              v-model.trim="capture.url"
              required
              type="url"
              maxlength="1400"
          /></label>
          <label
            >来源市场<input
              v-model.trim="capture.market"
              maxlength="80" /></label
          ><label
            v-if="
              capture.source === '上海法兰克福' || capture.source === '广交会'
            "
            >来源届次<input
              v-model.trim="capture.edition"
              required
              maxlength="60"
          /></label>
        </div>
        <label
          >来源说明<textarea
            v-model="capture.snippet"
            maxlength="1800"
            rows="2"
          />
        </label>
        <div class="actions">
          <button class="primary" :disabled="busy">保存并核实</button
          ><button type="button" class="ghost" @click="capture = null">
            取消
          </button>
        </div>
      </form>
      <div v-if="results" class="panel">
        <div class="panelhead">
          <h2>
            检索结果 <small>{{ results.items.length }}</small>
          </h2>
          <span class="tag">{{
            results.mode === "live"
              ? "实时网页线索"
              : results.mode === "bluesky"
                ? "Bluesky 实时原帖"
                : "本地资料"
          }}</span>
        </div>
        <p class="formpad out-note">{{ results.query }}</p>
        <div v-if="results.items.length" class="cards">
          <article
            class="companycard"
            v-for="r in results.items"
            :key="[r.url, r.edition, r.title].join('|')"
          >
            <small>{{
              [r.source, r.edition, r.market].filter(Boolean).join(" · ")
            }}</small>
            <h3>{{ r.title }}</h3>
            <p>{{ r.snippet || "请打开原页核对发布方与内容。" }}</p>
            <div class="actions">
              <a
                :href="safeLink(r.url)"
                target="_blank"
                rel="noopener noreferrer"
                >打开来源 ↗</a
              ><button
                class="ghost"
                :disabled="busy"
                @click="capture = { ...r }"
              >
                登记线索
              </button>
            </div>
          </article>
        </div>
        <p v-else class="empty">
          本次检索没有命中，可更改关键词或录入获授权的来源。
        </p>
      </div>
    </template>
    <template v-if="tab === '核实记录'">
      <div class="panel formpad">
        <div class="line">
          <h2>来源核实</h2>
          <select v-model="status" aria-label="核实状态">
            <option v-for="v in ['全部', '待核实', '已核实', '排除']" :key="v">
              {{ v }}
            </option>
          </select>
        </div>
        <button
          v-for="e in records"
          :key="e.id"
          class="out-row"
          :aria-pressed="reviewId === e.id"
          @click="openReview(e.id)"
        >
          <span
            ><strong>{{ e.title }}</strong
            ><small>{{ e.source }} {{ e.edition }}</small></span
          ><span class="tag">{{ e.verdict }}</span>
        </button>
        <p v-if="!records.length" class="empty">当前没有符合条件的核实记录。</p>
      </div>
      <BuyerReview
        id="outreach-review"
        v-if="selectedReview"
        :key="selectedReview.id + selectedReview.updated"
        :record="selectedReview"
        :buyers="data.buyers"
        @saved="afterReview"
        @conflict="act(refresh)"
      />
    </template>
    <template v-if="tab === '买家名单'">
      <div class="panel formpad">
        <div class="line">
          <h2>分级买家</h2>
          <a
            class="ghost"
            :href="
              '/api/outreach/export.xlsx?grade=' +
              encodeURIComponent(grade) +
              '&q=' +
              encodeURIComponent(query)
            "
            download="冠英买家分级.xlsx"
            >导出当前名单 Excel</a
          >
        </div>
        <div class="fields">
          <label
            >搜索买家<input
              v-model="query"
              maxlength="150"
              placeholder="名称、市场或业务角色" /></label
          ><label
            >产品匹配度<select aria-label="产品匹配度" v-model="grade">
              <option v-for="g in ['全部', 'A', 'B', 'C', '待评级']" :key="g">
                {{ g }}
              </option>
            </select></label
          >
        </div>
        <button
          v-for="b in buyers"
          :key="b.id"
          class="out-row"
          :aria-pressed="buyerId === b.id"
          @click="openBuyer(b.id)"
        >
          <span
            ><strong>{{ b.name }}</strong
            ><small>{{ b.country }} · {{ b.kind }}</small></span
          ><span class="tag">{{ b.grade || "待评级" }}</span>
        </button>
        <p v-if="!buyers.length" class="empty">没有符合条件的买家。</p>
      </div>
      <OutreachBuyer
        id="outreach-buyer"
        v-if="buyer && buyers.some((b) => b.id === buyerId)"
        :key="buyer.id"
        :buyer="buyer"
        :data="data"
        @refresh="act(refresh)"
        @review="openReview"
      />
    </template>
  </div>
</template>
<style>
.outreach {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.outreach .formpad {
  display: grid;
  gap: 14px;
}
.outreach :is(h2, h3, p, fieldset) {
  margin: 0;
}
.outreach fieldset {
  padding: 0;
  border: 0;
  min-width: 0;
}
.outreach form {
  min-width: 0;
}
.outreach .fields {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr));
}
.outreach label {
  display: grid;
  gap: 6px;
  min-width: 0;
  font-weight: 600;
}
.outreach :is(input, select, textarea) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}
.outreach form .actions,
.outreach details form > button {
  margin-top: 12px;
}
.out-tabs,
.outreach .actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.outreach .line {
  flex-wrap: wrap;
  gap: 8px;
}
.out-tabs button[aria-pressed="true"] {
  background: var(--ink, #20242b);
  color: white;
}
.out-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
  text-align: left;
  background: transparent;
  color: inherit;
  border: 0;
  border-bottom: 1px solid #e0e4e8;
  padding: 10px 8px;
  cursor: pointer;
}
.out-row[aria-pressed="true"] {
  background: #eef3f9;
}
.out-row small {
  display: block;
  margin-top: 3px;
  color: #596474;
}
.outreach :is(.out-row, .companycard, p, a, small, pre) {
  overflow-wrap: anywhere;
}
.out-details summary {
  cursor: pointer;
  font-weight: 650;
}
.out-details {
  border-top: 1px solid #e0e4e8;
  padding-top: 12px;
}
.out-details p,
.out-note {
  color: #53606a;
}
.out-details[open] > form,
.out-details[open] > div {
  margin-top: 12px;
}
.outreach .out-draft {
  white-space: pre-wrap;
  font: inherit;
  background: #f5f7f9;
  padding: 14px;
}
</style>

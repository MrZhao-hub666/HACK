<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, errorMessage, stamp } from "../shared";
import Icon from "./Icon.vue";

defineProps<{ demo: boolean }>();
const emit = defineEmits<{
  reload: [];
  open: [id: number];
  company: [id: number];
}>();
type Platform = "dy" | "xhs";
interface Signal {
  id: number;
  platform: Platform;
  kind: string;
  external_id: string;
  body: string;
  parent_text: string;
  published: string;
  keyword: string;
  signal: string;
  source_url: string;
  quantities: string[];
  codes: string[];
  owned: boolean;
  demo: number;
  company_id: number | null;
  inquiry_id: number | null;
}
interface SourceFile {
  platform: Platform;
  path: string;
  count: number | null;
}
interface Counts {
  inserted: number;
  updated: number;
  unchanged: number;
  skipped: number;
}
const labels = { dy: "抖音", xhs: "小红书" };
const q = ref(""),
  filter = ref("求购"),
  platform = ref(""),
  upstream = ref(false);
const items = ref<Signal[]>([]),
  total = ref(0),
  offset = ref(0),
  size = 20;
const files = ref<SourceFile[]>([]),
  fileListLoaded = ref(false),
  selected = ref("");
const inputPlatform = ref<Platform>("dy"),
  localFile = ref<File | null>(null);
const busy = ref(false),
  error = ref(""),
  message = ref(""),
  activeId = ref(0);
const companyName = ref(""),
  country = ref("");
async function action(work: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await work();
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    busy.value = false;
  }
}
async function results(start: number) {
  const params = new URLSearchParams({
    q: q.value.trim(),
    offset: String(start),
    limit: String(size),
  });
  if (platform.value) params.set("platform", platform.value);
  if (filter.value) params.set("signal", filter.value);
  const res = await api<{ items: Signal[]; total: number; upstream: boolean }>(
    "/domestic/signals?" + params,
  );
  items.value = res.items;
  total.value = res.total;
  upstream.value = res.upstream;
  offset.value = start;
  activeId.value = 0;
}
async function listFiles() {
  await action(async () => {
    files.value = await api<SourceFile[]>("/domestic/files");
    fileListLoaded.value = true;
    selected.value = files.value[0]?.path ?? "";
  });
}
function process(source: "examples" | "import" | "sync") {
  return action(async () => {
    let payload: unknown;
    if (source === "import") {
      if (!localFile.value) throw Error("请选择 JSON 文件。");
      if (localFile.value.size > 4 * 1024 * 1024)
        throw Error("请选择 4 MiB 以内的文件。");
      payload = {
        platform: inputPlatform.value,
        document: await localFile.value.text(),
      };
    }
    if (source === "sync") payload = { path: selected.value };
    const c = await api<Counts>("/domestic/" + source, "POST", payload);
    message.value = `新增 ${c.inserted} 条，更新 ${c.updated} 条，重复 ${c.unchanged} 条，跳过 ${c.skipped} 条。`;
    await results(0);
  });
}
function chooseFile(event: Event) {
  localFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}
function startAdopt(item: Signal) {
  activeId.value = item.id;
  companyName.value = "";
  country.value = "";
}
function adopt(item: Signal) {
  return action(async () => {
    const res = await api<{ company_id: number }>(
      `/domestic/signals/${item.id}/adopt`,
      "POST",
      { name: companyName.value, country: country.value },
    );
    item.company_id = res.company_id;
    activeId.value = 0;
    emit("reload");
    message.value = "已关联客户档案。";
  });
}
function toInbox(item: Signal) {
  return action(async () => {
    const res = await api<{ inquiry_id: number }>(
      `/domestic/signals/${item.id}/inquiry`,
      "POST",
    );
    item.inquiry_id = res.inquiry_id;
    emit("open", res.inquiry_id);
  });
}
onMounted(() => action(() => results(0)));
</script>

<template>
  <section class="panel">
    <div class="panelhead">
      <div class="sect">
        <Icon name="search" />
        <h2>检索已导入内容</h2>
      </div>
    </div>
    <form class="formpad" @submit.prevent="action(() => results(0))">
      <div class="fields">
        <label
          >关键词<input
            v-model="q"
            maxlength="180"
            placeholder="刹车片、车队或 WVA 编码"
        /></label>
        <label
          >来源平台<select v-model="platform">
            <option value="">全部平台</option>
            <option value="dy">抖音</option>
            <option value="xhs">小红书</option>
          </select></label
        >
        <label
          >内容意图<select v-model="filter">
            <option value="">全部意图</option>
            <option>求购</option>
            <option>待判断</option>
            <option>供应推广</option>
          </select></label
        >
      </div>
      <div class="actions">
        <button class="primary" :disabled="busy">搜索线索</button>
        <template v-if="q.trim()">
          <a
            v-if="platform !== 'xhs'"
            :href="
              'https://www.douyin.com/search/' + encodeURIComponent(q.trim())
            "
            target="_blank"
            rel="noopener noreferrer"
            >去抖音搜索 <Icon name="external" size="sm"
          /></a>
          <a
            v-if="platform !== 'dy'"
            :href="
              'https://www.xiaohongshu.com/search_result?keyword=' +
              encodeURIComponent(q.trim())
            "
            target="_blank"
            rel="noopener noreferrer"
            >去小红书搜索 <Icon name="external" size="sm"
          /></a>
        </template>
      </div>
    </form>
  </section>
  <details class="panel domestic-source" :open="total === 0 || undefined">
    <summary><Icon name="layers" /> 接入 MediaCrawler 数据</summary>
    <div class="formpad">
      <div class="fields">
        <label
          >导入平台<select v-model="inputPlatform">
            <option value="dy">抖音</option>
            <option value="xhs">小红书</option>
          </select></label
        >
        <label
          >本地 JSON 导出<input
            type="file"
            accept=".json,application/json"
            @change="chooseFile"
        /></label>
      </div>
      <div class="actions">
        <button
          class="ghost"
          :disabled="busy || !localFile"
          @click="process('import')"
        >
          导入文件
        </button>
        <button
          v-if="demo"
          class="ghost"
          :disabled="busy"
          @click="process('examples')"
        >
          载入测试样例
        </button>
      </div>
      <template v-if="upstream">
        <div class="actions">
          <button class="ghost" :disabled="busy" @click="listFiles">
            读取 WebUI 文件列表
          </button>
        </div>
        <div class="actions" v-if="files.length">
          <label class="stretch"
            >WebUI 导出文件<select v-model="selected">
              <option v-for="file in files" :key="file.path" :value="file.path">
                {{ file.path
                }}{{ file.count == null ? "" : " · " + file.count + " 条" }}
              </option>
            </select></label
          ><button
            class="primary"
            :disabled="busy || !selected"
            @click="process('sync')"
          >
            同步所选文件
          </button>
        </div>
        <p class="hint" v-else-if="fileListLoaded">
          WebUI 中没有抖音或小红书的内容、评论 JSON 文件。
        </p>
      </template>
      <p v-else class="hint">
        连接独立 WebUI 后可直接同步导出文件；当前可从本地导入。
      </p>
    </div>
  </details>
  <div class="notice" role="alert" v-if="error">{{ error }}</div>
  <p class="hint" role="status" v-if="message">{{ message }}</p>
  <section class="panel" :aria-busy="busy">
    <div class="panelhead">
      <div class="sect">
        <h2>线索结果</h2>
        <span class="count">{{ total }}</span>
      </div>
    </div>
    <p v-if="!items.length" class="empty">
      {{
        busy ? "读取中…" : "没有匹配的记录。可调整筛选条件或导入一份渠道数据。"
      }}
    </p>
    <div v-else class="cards discovery-cards">
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
.domestic-source summary {
  cursor: pointer;
  padding: 1rem 1.25rem;
  font-weight: 650;
}
.domestic-source summary svg {
  vertical-align: middle;
}
.domestic-source .fields label,
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
.domestic-source .actions,
.domestic-card .actions {
  flex-wrap: wrap;
}
.domestic-source input,
.domestic-source select {
  max-width: 100%;
  min-width: 0;
}
</style>

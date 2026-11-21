<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, errorMessage, stamp } from "../shared";
import type { DomesticSignal } from "../types";
import Icon from "./Icon.vue";

const emit = defineEmits<{
  reload: [];
  open: [id: number];
  company: [id: number];
}>();
const labels = { dy: "抖音", xhs: "小红书" };
const q = ref(""),
  filter = ref("求购"),
  platform = ref("");
const items = ref<DomesticSignal[]>([]),
  total = ref(0),
  offset = ref(0),
  size = 20;
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
  const res = await api<{ items: DomesticSignal[]; total: number }>(
    "/domestic/signals?" + params,
  );
  items.value = res.items;
  total.value = res.total;
  offset.value = start;
  activeId.value = 0;
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
    message.value = "已关联客户档案。";
  });
}
function toInbox(item: DomesticSignal) {
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
      </div>
    </form>
  </section>
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
        busy ? "读取中…" : "没有匹配的社交线索。可调整关键词或筛选条件。"
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

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api, errorMessage, kinds, toast, safeLink } from "../shared";
import Icon from "./Icon.vue";
import type { Candidate, DiscoveryResult, Company, Config } from "../types";

const props = defineProps<{ companies: Company[]; config: Config }>();
const emit = defineEmits<{ reload: [] }>();
const form = ref({
    market: "马来西亚",
    kind: "待识别",
    keywords: "",
    mode: "samples",
  }),
  result = ref<DiscoveryResult | null>(null),
  error = ref(""),
  busy = ref(false);
async function run() {
  busy.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await api<DiscoveryResult>(
      "/discovery/search",
      "POST",
      form.value,
    );
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    busy.value = false;
  }
}
function saved(c: Candidate) {
  return props.companies.some(
    (x) => x.name === c.name && x.country === c.country,
  );
}
async function adopt(c: Candidate) {
  busy.value = true;
  try {
    await api("/companies", "POST", c);
    emit("reload");
    toast("已加入客户档案");
  } catch (e) {
    toast(errorMessage(e));
  } finally {
    busy.value = false;
  }
}
onMounted(run);
</script>

<template>
  <div class="panel">
    <div class="panelhead">
      <div class="sect">
        <icon name="compass" />
        <h2>发现海外买家</h2>
      </div>
      <span class="tag">{{
        form.mode === "samples" ? "公开样例库" : "实时搜索"
      }}</span>
    </div>
    <form class="formpad" @submit.prevent="run">
      <div class="fields">
        <label
          >目标市场<input
            required
            maxlength="70"
            v-model.trim="form.market"
            list="markets"
          />
          <datalist id="markets">
            <option
              v-for="x in [
                '马来西亚',
                '泰国',
                '菲律宾',
                '巴西',
                '墨西哥',
                '阿联酋',
              ]"
            >
              {{ x }}
            </option>
          </datalist>
        </label>
        <label
          >业务类型<select v-model="form.kind">
            <option v-for="k in kinds" :value="k">
              {{ k === "待识别" ? "全部类型" : k }}
            </option>
          </select>
        </label>
        <label
          >数据来源<select v-model="form.mode">
            <option value="samples">已核验样例</option>
            <option value="live">实时网页搜索</option>
          </select>
        </label>
      </div>
      <div class="actions">
        <label class="search stretch">
          <icon name="search" />
          <input
            v-model.trim="form.keywords"
            placeholder="可选关键词，如维修、Labu、fleet"
            aria-label="发现关键词"
          />
        </label>
        <button class="primary" :disabled="busy">
          {{ busy ? "检索中…" : "搜索企业" }}<icon name="arrow" />
        </button>
      </div>
      <p class="hint">
        {{
          form.mode === "samples"
            ? "样例覆盖马来西亚的三家企业，可核对每条原始证据。"
            : config.live_search
              ? "实时查询公开网页，结果需由销售复核。"
              : "实时模式需在服务端配置 BRAVE_API_KEY。"
        }}
      </p>
    </form>
  </div>
  <div class="panel" v-if="result">
    <div class="panelhead">
      <div class="sect">
        <h2>候选企业</h2>
        <span class="count">{{ result.items.length }}</span>
      </div>
      <span class="meta">{{
        result.mode === "samples" ? "已核验样例" : "实时网页搜索"
      }}</span>
    </div>
    <div class="cards discovery-cards">
      <article
        class="companycard"
        v-for="c in result.items"
        :key="c.evidence_url"
      >
        <div class="line">
          <span class="business-mark"><icon name="building" :size="20" /></span>
          <small>{{ c.country }} · {{ c.checked.slice(0, 10) }}</small>
        </div>
        <h3>{{ c.name }}</h3>
        <div class="tags">
          <span class="tag blue">{{ c.kind }}</span>
        </div>
        <p>{{ c.evidence || "摘要未提供业务证据，请查阅来源。" }}</p>
        <div class="next"><b>建议核实</b> {{ c.next_action }}</div>
        <div class="line">
          <a
            :href="safeLink(c.evidence_url)"
            target="_blank"
            rel="noopener noreferrer"
            >查看依据 ↗</a
          >
          <button class="ghost" @click="adopt(c)" :disabled="busy || saved(c)">
            {{ saved(c) ? "已存入档案" : "加入客户档案" }}
          </button>
        </div>
      </article>
    </div>
    <div class="empty" v-if="!result.items.length">
      没有匹配的企业，可修改地区、类型或关键词。
    </div>
  </div>
  <div class="notice" role="alert" v-if="error">{{ error }}</div>
</template>

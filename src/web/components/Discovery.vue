<script setup lang="ts">
import Domestic from "./Domestic.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";
import { computed, ref, onMounted } from "vue";
import { api, errorMessage, kinds, toast, safeLink } from "../shared";
import Icon from "./Icon.vue";
import type { Candidate, DiscoveryResult, Company, Config } from "../types";

const props = defineProps<{ companies: Company[]; config: Config }>();
const emit = defineEmits<{
  reload: [];
  open: [id: number];
  company: [id: number];
}>();
const mode = ref<"samples" | "live" | "domestic">(
  location.hash === "#domestic" ? "domestic" : "samples",
);
const selectedMarket = ref("马来西亚");
const customMarket = ref("");
const form = ref({
    kind: "待识别",
    keywords: "",
  }),
  result = ref<DiscoveryResult | null>(null),
  error = ref(""),
  searching = ref(false),
  saving = ref(false);
const busy = computed(() => searching.value || saving.value);
async function run(manual = false) {
  if (busy.value || mode.value === "domestic") return;
  searching.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await api<DiscoveryResult>(
      "/discovery/search",
      "POST",
      {
        ...form.value,
        market: selectedMarket.value || customMarket.value,
        mode: mode.value,
      },
    );
  } catch (e) {
    error.value = errorMessage(e);
    if (manual) toast("买家搜索失败", "error");
  } finally {
    searching.value = false;
  }
}
function saved(c: Candidate) {
  return props.companies.some(
    (x) => x.name === c.name && x.country === c.country,
  );
}
async function adopt(c: Candidate) {
  if (busy.value) return;
  saving.value = true;
  try {
    await api("/companies", "POST", c);
    emit("reload");
    toast("已加入客户档案");
  } catch (e) {
    toast(errorMessage(e), "error");
  } finally {
    saving.value = false;
  }
}
onMounted(run);
</script>

<template>
  <div class="panel">
    <div class="panelhead">
      <div class="sect">
        <icon name="compass" />
        <h2>发现买家</h2>
      </div>
      <a href="#outreach">展会买家及采购原帖 ↗</a>
      <label class="inputlabel">
        数据来源
        <select v-model="mode" :disabled="busy">
          <option value="samples">已核验样例</option>
          <option value="live">实时网页搜索</option>
          <option value="domestic">抖音和小红书</option>
        </select>
      </label>
    </div>
    <form v-if="mode !== 'domestic'" class="formpad" @submit.prevent="run(true)">
      <div class="fields">
        <label>
          目标市场
          <select v-model="selectedMarket">
            <option value="">自定义市场…</option>
            <optgroup
              v-for="group in config.discovery_markets"
              :key="group.region"
              :label="group.region"
            >
              <option
                v-for="market in group.markets"
                :key="market"
                :value="market"
              >
                {{ market }}
              </option>
            </optgroup>
          </select>
        </label>
        <label v-if="!selectedMarket">
          自定义市场
          <input
            required
            maxlength="70"
            v-model.trim="customMarket"
            placeholder="输入国家、地区或城市"
          />
        </label>
        <label
          >业务类型<select v-model="form.kind">
            <option v-for="k in kinds" :value="k">
              {{ k === "待识别" ? "全部类型" : k }}
            </option>
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
          {{ searching ? "检索中…" : "搜索企业" }}<icon name="arrow" />
        </button>
      </div>
      <p class="hint">
        {{
          mode === "samples"
            ? "样例仅覆盖马来西亚。搜索其他市场，请切换到实时网页搜索。"
            : config.live_search
              ? "实时查询公开网页，结果需由销售复核。"
              : "实时模式需在服务端配置 Exa 或 Brave 搜索密钥。"
        }}
      </p>
    </form>
  </div>
  <Domestic
    v-if="mode === 'domestic'"
    @reload="emit('reload')"
    @open="emit('open', $event)"
    @company="emit('company', $event)"
  />
  <div class="panel" v-else-if="result || searching" :aria-busy="searching">
    <div class="panelhead">
      <div class="sect">
        <h2>候选企业</h2>
        <span v-if="result" class="count">{{ result.items.length }}</span>
      </div>
      <span class="meta" v-if="result">{{
        result.mode === "samples" ? "已核验样例" : "实时网页搜索"
      }}</span>
    </div>
    <LoadingSkeleton v-if="searching" layout="cards" label="正在查找候选企业" />
    <div v-else-if="result" class="cards discovery-cards">
      <article
        class="companycard"
        v-for="c in result.items"
        :key="c.evidence_url"
      >
        <div class="line">
          <span class="business-mark"><icon name="building" size="md" /></span>
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
            >查看依据 <icon name="external" size="sm"
          /></a>
          <button class="ghost" @click="adopt(c)" :disabled="busy || saved(c)">
            {{ saved(c) ? "已存入档案" : "加入客户档案" }}
          </button>
        </div>
      </article>
    </div>
    <div class="empty" v-if="result && !result.items.length">
      没有匹配的企业，可修改地区、类型或关键词。
    </div>
  </div>
  <div class="notice" role="alert" v-if="error && mode !== 'domestic'">{{ error }}</div>
</template>

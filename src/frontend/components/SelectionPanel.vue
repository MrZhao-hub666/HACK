<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { InquiryDetail } from "../types";
import { api, errorMessage } from "../shared";

interface Candidate {
  spec_id: string; name: string; code?: string; market: string; kind: string;
  width?: string; thickness?: string; size_raw?: string; wva?: string; fmsi?: string;
  sale_unit?: string; matched: string[]; conflict: string[]; images: {url:string; label:string}[];
  sources: {crop:string; page:string; label:string}[];
}
interface Result { count:number; question:string; items:Candidate[]; routing:{prefix:string|null} }
interface Quote { id:number; spec_id:string; quantity:number; unit:string; status:string; total:string|null; currency:string|null; missing:string[] }
const props = defineProps<{inquiry: InquiryDetail}>();
const words = ref(""), result = ref<Result>(), selected = ref(""), qty = ref<number>(), unit = ref("");
const busy = ref(false), error = ref(""), draft = ref<Quote>(), requestKey = ref("");
const history = ref<Quote[]>();
const candidate = computed(() => result.value?.items.find(p => p.spec_id === selected.value));
const inquiryPath = computed(() => "/inquiries/" + props.inquiry.id + "/selection");
let revision = 0;
watch(() => [words.value, props.inquiry.id, props.inquiry.messages.map(m => m.id).join(","),
  props.inquiry.history.filter(h => h.action === "登记人工回复").map(h => h.id).join(",")].join("|"), () => {
  revision++; result.value = undefined; selected.value = ""; draft.value = undefined; error.value = ""; busy.value = false;
});
watch(selected, () => { unit.value = candidate.value?.sale_unit || ""; qty.value = undefined; });
watch([selected, qty, unit], () => { requestKey.value = ""; draft.value = undefined; });
async function match() {
  const rev = ++revision;
  busy.value = true; error.value = ""; result.value = undefined; selected.value = ""; draft.value = undefined;
  try {
    const data = await api<Result>(inquiryPath.value, "POST", {customer_words:words.value.trim()});
    if (rev !== revision) return;
    result.value = data;
    selected.value = data.items[0]?.spec_id || "";
  } catch (e) { if (rev === revision) error.value = errorMessage(e); }
  finally { if (rev === revision) busy.value = false; }
}
function media(path?: string) {
  if (path?.match(/^\/api\/(photo|page|observation|domestic-picture|evidence)\//))
    return "/api/selection/media/" + path.slice(5);
}
async function quote() {
  if (!candidate.value || !qty.value || !unit.value.trim()) return;
  const rev = revision;
  busy.value = true; error.value = "";
  requestKey.value ||= crypto.randomUUID();
  try {
    const data = await api<Quote>(inquiryPath.value + "/quotes", "POST", {
      spec_id:selected.value, quantity:qty.value, unit:unit.value.trim(), request_key:requestKey.value
    });
    if (rev === revision) {
      draft.value = data;
      if (history.value) history.value = [data, ...history.value.filter(q => q.id !== data.id)].slice(0,25);
    }
  } catch (e) { if (rev === revision) error.value = errorMessage(e); }
  finally { if (rev === revision) busy.value = false; }
}
async function loadHistory() {
  busy.value = true; error.value = "";
  try { history.value = await api<Quote[]>(inquiryPath.value + "/quotes"); }
  catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
}
</script>
<template>
  <section class="selection fields" aria-label="询盘选型">
    <label>客户补充原话<textarea v-model="words" maxlength="3000" :disabled="busy"
      placeholder="已有来信会自动带入。可补充旧件编码、车桥或尺寸。" /></label>
    <button type="button" class="primary" :disabled="busy" @click="match">根据询盘匹配型号</button>
    <p v-if="busy" role="status">正在处理…</p>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <template v-if="result">
      <p><strong>建议询问客户</strong><br>{{ result.question }}</p>
      <label v-if="result.count">候选规格（{{ result.count }}）<select v-model="selected" :disabled="busy">
        <option v-for="p in result.items" :key="p.spec_id" :value="p.spec_id">{{ p.spec_id }} · {{ p.name || p.code }}</option>
      </select></label>
      <p v-else>当前信息尚未匹配到目录规格。</p>
    </template>
    <article v-if="candidate">
      <h3>{{ candidate.spec_id }} · {{ candidate.name || candidate.code }}</h3>
      <p>{{ [candidate.market, candidate.kind, candidate.code, candidate.wva && 'WVA ' + candidate.wva,
        candidate.fmsi && 'FMSI ' + candidate.fmsi].filter(Boolean).join(' · ') }}</p>
      <p v-if="candidate.size_raw">目录尺寸　{{ candidate.size_raw }}</p>
      <p v-else-if="candidate.width || candidate.thickness">宽度 C　{{ candidate.width || '—' }}　厚度 D　{{ candidate.thickness || '—' }}</p>
      <p>匹配依据　{{ candidate.matched.join('、') }}</p>
      <p v-if="candidate.conflict.length" class="notice">编号与客户描述有冲突，请核实后再报价。</p>
      <div class="photos">
        <a v-for="im in candidate.images" :key="im.url" :href="media(im.url)" target="_blank" rel="noopener"><img :src="media(im.url)" :alt="im.label" loading="lazy"></a>
        <a v-for="s in candidate.sources" :key="s.crop" :href="media(s.page)" target="_blank" rel="noopener"><img :src="media(s.crop)" :alt="s.label" loading="lazy">{{ s.label }}</a>
      </div>
      <form class="fields" @submit.prevent="quote">
        <label>采购数量<input v-model.number="qty" type="number" min="1" max="100000000" step="1" required :disabled="busy"></label>
        <label>计价单位<input v-model.trim="unit" maxlength="20" required placeholder="例如：套" :disabled="busy"></label>
        <button :disabled="busy || !!draft || !!candidate.conflict.length">生成报价草稿</button>
      </form>
      <p v-if="draft" role="status"><b>{{ draft.status }} #{{ draft.id }}</b>
        <span v-if="draft.total"> · {{ draft.total }} {{ draft.currency }}</span>
        <span v-if="draft.missing.length"> · 待核实：{{ draft.missing.join('、') }}</span></p>
    </article>
    <button class="textbtn" type="button" :disabled="busy" @click="loadHistory">查看本询盘最近报价草稿</button>
    <ul v-if="history?.length"><li v-for="q in history" :key="q.id">
      #{{ q.id }} · {{ q.spec_id }} · {{ q.quantity }} {{ q.unit }} · {{ q.status }}
      <span v-if="q.total"> · {{ q.total }} {{ q.currency }}</span>
    </li></ul>
    <p v-else-if="history">本询盘暂无报价草稿。</p>
  </section>
</template>
<style scoped>
.selection {display:grid;grid-template-columns:minmax(0,1fr);gap:.7rem;margin:1rem 0}
.selection p {overflow-wrap:anywhere;margin:.5rem 0}
.selection textarea,.selection select,.selection input {width:100%;max-width:100%}
.photos {display:flex;gap:.5rem;flex-wrap:wrap;margin:.75rem 0}
.photos a {display:grid;gap:.25rem}.photos img {width:7rem;height:4rem;object-fit:contain}
</style>

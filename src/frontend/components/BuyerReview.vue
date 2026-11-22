<script setup lang="ts">
import { ref } from "vue";
import { api, errorMessage, kinds, safeLink, toast } from "../shared";
import type { Buyer, Evidence } from "../outreach-types";
const props = defineProps<{ record: Evidence; buyers: Buyer[] }>();
const emit = defineEmits<{ saved: [id: number | null]; conflict: [] }>();
const e = props.record;
const isPost = e.source === "社媒原帖";
const form = ref({
  version: e.updated,
  verdict: e.verdict === "待核实" ? "已核实" : e.verdict,
  company_id: e.company_id,
  name: isPost ? "" : e.title,
  market: e.market,
  kind: "待识别",
  author: e.author,
  published: e.published,
  quote: e.quote,
  fit: e.fit,
  intent: e.intent,
  reason: e.reason,
});
const attach = ref(e.company_id ? "existing" : isPost ? "none" : "new");
const busy = ref(false),
  error = ref(""),
  hint = ref("");
async function save() {
  busy.value = true;
  error.value = "";
  try {
    const v = form.value;
    const result = await api<Evidence>("/outreach/evidence/" + e.id, "PUT", {
      ...v,
      company_id: attach.value === "existing" ? v.company_id : null,
      name: attach.value === "new" ? v.name : "",
      published: v.published || null,
    });
    toast("核实记录已保存");
    emit("saved", result.company_id);
  } catch (ex) {
    error.value = errorMessage(ex);
  } finally {
    busy.value = false;
  }
}
async function analyze() {
  busy.value = true;
  error.value = "";
  try {
    const original = form.value.quote;
    const r = await api<{
      intent: string;
      engine: string;
      fit: string;
      reason: string;
    }>("/outreach/assess", "POST", { text: form.value.quote });
    if (form.value.quote !== original) return;
    form.value.intent = r.intent;
    form.value.fit = r.fit;
    if (!form.value.reason) form.value.reason = r.reason;
    hint.value =
      r.engine + " · 建议 " + r.fit + " 级。" + r.reason + " 保存前可修正。";
  } catch (ex) {
    error.value = errorMessage(ex);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <form class="panel formpad" @submit.prevent="save">
    <div class="line">
      <h2>核实 · {{ e.title }}</h2>
      <a :href="safeLink(e.url)" target="_blank" rel="noopener noreferrer"
        >查看原文 ↗</a
      >
    </div>
    <p v-if="e.snippet" class="out-note">来源说明 · {{ e.snippet }}</p>
    <p v-if="e.reviewer" class="meta">
      上次由 {{ e.reviewer }} 核实 · {{ e.updated.slice(0, 10) }}
    </p>
    <div class="fields">
      <label
        >处理结论<select v-model="form.verdict">
          <option>已核实</option>
          <option>排除</option>
          <option>待核实</option>
        </select></label
      >
      <label
        >发布方<input
          v-model.trim="form.author"
          maxlength="160"
          :required="isPost && form.verdict === '已核实'"
      /></label>
      <label>原文发布日期<input type="date" v-model="form.published" /></label>
    </div>
    <label
      >原文摘录<textarea
        rows="3"
        v-model.trim="form.quote"
        maxlength="2000"
        :required="form.verdict === '已核实'"
        placeholder="打开原页，保留买卖方向、型号、数量和单位。"
      />
    </label>
    <div class="fields">
      <label
        >来源意图<select v-model="form.intent">
          <option
            v-for="i in [
              '待判断',
              '企业参会',
              '采购询价',
              '寻找货源',
              '供应商准入',
              '安装咨询',
              '卖方推广',
              '其他',
            ]"
            :key="i"
          >
            {{ i }}
          </option>
        </select></label
      >
      <div class="actions">
        <button
          type="button"
          class="ghost"
          :disabled="busy || !form.quote"
          @click="analyze"
        >
          {{ isPost ? "辅助判断原帖意图" : "辅助判断产品匹配" }}
        </button>
      </div>
    </div>
    <small class="meta">{{
      hint || "启用外部模型时，辅助判断可能将这段摘录提交给已配置的服务。"
    }}</small>
    <template v-if="form.verdict === '已核实'">
      <div class="fields">
        <label
          >归属方式<select v-model="attach">
            <option value="existing">关联已有企业</option>
            <option value="new">按已核实名称入档</option>
            <option v-if="isPost" value="none">尚未核实企业</option>
          </select></label
        >
        <label v-if="attach === 'existing'"
          >已有企业<select v-model="form.company_id" required>
            <option :value="null" disabled>请选择</option>
            <option v-for="b in buyers" :key="b.id" :value="b.id">
              {{ b.name }} · {{ b.country }}
            </option>
          </select></label
        >
        <template v-if="attach === 'new'"
          ><label
            >核实企业名称<input
              required
              v-model.trim="form.name"
              maxlength="200" /></label
          ><label
            >核实市场<input
              required
              v-model.trim="form.market"
              maxlength="80" /></label
          ><label
            >业务角色<select v-model="form.kind">
              <option v-for="k in kinds" :key="k">{{ k }}</option>
            </select></label
          ></template
        >
      </div>
      <label v-if="attach !== 'none'"
        >产品匹配依据<select v-model="form.fit">
          <option value="A">A · 明确采购商用车制动片或衬片</option>
          <option value="B">B · 经营相邻品类</option>
          <option value="C">C · 仅确认企业或参会身份</option>
        </select></label
      >
    </template>
    <label
      >核实理由<textarea
        rows="2"
        required
        maxlength="600"
        v-model.trim="form.reason"
        placeholder="这段材料能证明什么？"
      />
    </label>
    <div v-if="error" class="notice" role="alert">
      {{ error }}
      <button type="button" class="textbtn" @click="emit('conflict')">
        重新读取
      </button>
    </div>
    <div class="actions">
      <button class="primary" :disabled="busy">保存核实结果</button>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref } from "vue";
import Icon from "./Icon.vue";
import { api, errorMessage, safeLink, stamp } from "../shared";
import type { Alternative, AlternativeBatch } from "../types";

const props = defineProps<{
  item: Alternative;
  actor: string;
  showOrigin?: boolean;
  live: boolean;
}>();
const emit = defineEmits<{
  changed: [batch: AlternativeBatch];
  company: [id: number];
  open: [id: number];
}>();
const editing = ref(false),
  busy = ref(false),
  error = ref(""),
  url = ref(""),
  note = ref("");
type PublicSource = { title: string; url: string; description: string };
const sources = ref<PublicSource[] | null>(null);
const looking = ref(false);
async function findSources() {
  if (looking.value) return;
  looking.value = true;
  error.value = "";
  sources.value = null;
  try {
    const response = await api<{ items: PublicSource[] }>(
      "/inquiries/" +
        props.item.inquiry_id +
        "/alternatives/" +
        props.item.id +
        "/sources",
      "POST",
    );
    sources.value = response.items;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    looking.value = false;
  }
}
function editProof() {
  sources.value = null;
  url.value = props.item.proof?.url || "";
  note.value = props.item.proof?.note || "";
  error.value = "";
  editing.value = true;
}
async function update(action: "adopted" | "dismissed" | "proof" | "withdraw") {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  const evidence = action === "proof" || action === "withdraw";
  try {
    const batch = await api<AlternativeBatch>(
      "/inquiries/" +
        props.item.inquiry_id +
        "/alternatives/" +
        props.item.id +
        (evidence ? "/proof" : "/feedback"),
      action === "withdraw" ? "DELETE" : "POST",
      action === "withdraw"
        ? undefined
        : evidence
          ? { url: url.value, note: note.value }
          : { decision: action },
    );
    editing.value = false;
    emit("changed", batch);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <article class="alternative-card">
    <button
      v-if="showOrigin"
      class="textbtn alt-origin"
      @click="emit('open', item.inquiry_id)"
    >
      来自 #{{ item.inquiry_id }} · {{ item.source_name }}
      <Icon name="chevron" size="sm" />
    </button>
    <div class="alt-title">
      <h3>{{ item.profile.name }}</h3>
      <span class="tag" :class="item.proof ? 'amber' : 'blue'">{{
        item.proof ? "竞争关系已人工核实" : "同市场潜客"
      }}</span>
    </div>
    <div class="tags">
      <span class="tag">{{ item.profile.country }}</span
      ><span class="tag">{{ item.profile.kind }}</span
      ><span class="tag">采购能力 · {{ item.profile.procurement }}</span>
    </div>
    <p>{{ item.profile.evidence }}</p>
    <p class="alt-reason">{{ item.reason }}</p>
    <p class="alt-reason" v-if="item.profile.next_action">
      建议核实 · {{ item.profile.next_action }}
    </p>
    <div class="alt-links">
      <a
        :href="safeLink(item.profile.evidence_url)"
        target="_blank"
        rel="noopener noreferrer"
        >业务依据 <Icon name="external" size="sm"
      /></a>
      <a
        v-if="item.source_url"
        :href="safeLink(item.source_url)"
        target="_blank"
        rel="noopener noreferrer"
        >原企业依据 <Icon name="external" size="sm"
      /></a>
      <small
        >{{ item.profile.source }} ·
        {{ item.profile.checked || "日期待核实" }}</small
      >
    </div>
    <div v-if="item.proof" class="analysis-box">
      <b>双方竞争依据</b>
      <p>{{ item.proof.note }}</p>
      <div class="alt-links">
        <a
          :href="safeLink(item.proof.url)"
          target="_blank"
          rel="noopener noreferrer"
          >查看原文 <Icon name="external" size="sm" /></a
        ><small>{{ item.proof.actor }} · {{ stamp(item.proof.at) }}</small>
      </div>
    </div>
    <div class="alt-contact">
      <span>公开业务联系</span>
      <strong v-if="item.profile.contact">{{ item.profile.contact }}</strong>
      <a
        v-if="item.profile.website"
        :href="safeLink(item.profile.website)"
        target="_blank"
        rel="noopener noreferrer"
        >企业官网 <Icon name="external" size="sm"
      /></a>
      <a
        v-if="item.profile.social"
        :href="safeLink(item.profile.social)"
        target="_blank"
        rel="noopener noreferrer"
        >社交主页 <Icon name="external" size="sm"
      /></a>
      <small
        v-if="
          !item.profile.contact && !item.profile.website && !item.profile.social
        "
        >待从公开来源核实</small
      >
    </div>
    <div v-if="item.archive_id" class="alt-existing">
      <button class="textbtn" @click="emit('company', item.archive_id)">
        已有客户档案 <Icon name="chevron" size="sm" />
      </button>
      <small>负责人 · {{ item.archive_owners.join("、") || "尚未分派" }}</small>
    </div>
    <div class="alt-actions" v-if="actor === item.owner">
      <template v-if="item.decision === 'pending'">
        <button class="primary" :disabled="busy" @click="update('adopted')">
          {{ item.archive_id ? "关联已有档案" : "加入客户档案" }}
        </button>
        <button class="ghost" :disabled="busy" @click="update('dismissed')">
          不相关
        </button> </template
      ><span v-else class="tag blue">已采纳</span>
      <button
        v-if="!editing"
        class="textbtn"
        :disabled="busy"
        @click="editProof"
      >
        {{ item.proof ? "编辑竞争依据" : "补充竞争依据" }}
      </button>
    </div>
    <form
      v-if="editing && actor === item.owner"
      class="alt-proof"
      @submit.prevent="update('proof')"
    >
      <div v-if="live" class="alt-source-search">
        <small
          >检索双方企业名称及公开竞争关键词：{{ item.source_name }}、{{
            item.profile.name
          }}</small
        >
        <button
          type="button"
          class="ghost"
          :disabled="looking"
          @click="findSources"
        >
          {{ looking ? "正在查找…" : "查找公开竞争线索" }}
        </button>
        <p v-if="sources && !sources.length" class="hint">
          未找到同时提及双方的竞争线索，可手动填写已核实的公开原文。
        </p>
        <div v-for="hit in sources || []" :key="hit.url" class="alt-source-hit">
          <a :href="safeLink(hit.url)" target="_blank" rel="noopener noreferrer"
            >{{ hit.title || hit.url }} <Icon name="external" size="sm"
          /></a>
          <p class="hint">{{ hit.description }}</p>
          <button type="button" class="textbtn" @click="url = hit.url">
            使用此链接
          </button>
        </div>
      </div>
      <label class="inputlabel"
        >公开证据链接<input
          v-model.trim="url"
          type="url"
          required
          maxlength="1400"
          placeholder="https://"
      /></label>
      <label class="inputlabel"
        >双方竞争事实<textarea
          v-model.trim="note"
          required
          minlength="1"
          maxlength="1000"
          rows="2"
          placeholder="例如，原文中双方参与的同一投标项目及范围"
        ></textarea>
      </label>
      <div class="alt-actions">
        <button class="primary" :disabled="busy">确认依据</button
        ><button
          class="ghost"
          type="button"
          :disabled="busy"
          @click="editing = false"
        >
          取消
        </button>
        <button
          v-if="item.proof"
          type="button"
          class="textbtn"
          :disabled="busy"
          @click="update('withdraw')"
        >
          撤回竞争判断
        </button>
      </div>
    </form>
    <div class="notice" role="alert" v-if="error">{{ error }}</div>
  </article>
</template>

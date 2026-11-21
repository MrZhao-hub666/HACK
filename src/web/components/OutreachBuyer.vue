<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, errorMessage, safeLink, toast } from "../shared";
import type {
  Buyer,
  ContactInput,
  Draft,
  OutreachData,
} from "../outreach-types";
const props = defineProps<{ buyer: Buyer; data: OutreachData }>();
const emit = defineEmits<{ refresh: []; review: [id: number] }>();
const contacts = computed(() =>
  props.data.contacts.filter((c) => c.company_id === props.buyer.id),
);
const emails = computed(() =>
  contacts.value.filter((c) => ["采购邮箱", "企业邮箱"].includes(c.kind)),
);
const evidence = computed(() =>
  props.data.evidence.filter((e) => e.company_id === props.buyer.id),
);
const drafts = computed(() =>
  props.data.drafts.filter((d) => d.company_id === props.buyer.id),
);
const base = "/outreach/buyers/" + props.buyer.id;
const fresh = (): ContactInput => ({
  kind: "采购邮箱",
  holder: "",
  value: "",
  url: "",
});
const form = ref(fresh()),
  error = ref(""),
  busy = ref(false);
const sources = ref<{
  items: ContactInput[];
  pages: { title: string; url: string; description: string }[];
}>({ items: [], pages: [] });
const searched = ref(false);
const invite = ref({
  event: "",
  starts: "",
  ends: "",
  booth: "",
  contact_id: null as number | null,
});
const draft = ref<Draft | null>(null);
const editEmail = ref<number | null>(null);
function setDraft(value?: Draft) {
  draft.value = value ? { ...value } : null;
  editEmail.value =
    emails.value.find((c) => c.value === value?.recipient)?.id ?? null;
}
setDraft(drafts.value[0]);
async function run(fn: () => Promise<void>, showFeedback = true) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (ex) {
    error.value = errorMessage(ex);
    if (showFeedback) toast("采购联系或邀约操作失败", "error");
  } finally {
    busy.value = false;
  }
}
async function lookup(live: boolean) {
  const r = await api<typeof sources.value>(
    base + "/contact-sources?live=" + live,
  );
  if (live) {
    sources.value.pages = r.pages;
    searched.value = true;
  } else sources.value.items = r.items;
}
onMounted(() => run(() => lookup(false), false));
async function contact() {
  await api(base + "/contacts", "POST", form.value);
  form.value = fresh();
  emit("refresh");
  toast("联系方式已保存");
}
async function generate() {
  setDraft(await api<Draft>(base + "/draft", "POST", invite.value));
  emit("refresh");
  toast("展位邀约草稿已就绪");
}
async function saveDraft() {
  if (!draft.value) return;
  setDraft(
    await api<Draft>("/outreach/drafts/" + draft.value.id, "PUT", {
      version: draft.value.updated,
      contact_id: editEmail.value,
      subject: draft.value.subject,
      body: draft.value.body,
    }),
  );
  emit("refresh");
  toast("草稿修改已保存");
}
async function copy() {
  if (!draft.value) return;
  await navigator.clipboard.writeText(
    draft.value.subject + "\n\n" + draft.value.body,
  );
  toast("已复制草稿");
}
</script>
<template>
  <section class="panel formpad">
    <div class="line">
      <h2>{{ buyer.name }}</h2>
      <a :href="'#companies?id=' + buyer.id">打开客户档案</a>
    </div>
    <p>
      {{ buyer.country }} · {{ buyer.kind }} · 采购能力：{{
        buyer.procurement
      }}
      · 产品匹配：{{ buyer.grade || "待评级" }}
    </p>
    <div v-if="error" class="notice" role="alert">{{ error }}</div>
    <details class="out-details" :open="evidence.length > 0">
      <summary>核实依据（{{ evidence.length }}）</summary>
      <button
        v-for="e in evidence"
        class="out-row"
        :key="e.id"
        @click="emit('review', e.id)"
      >
        <span
          ><strong>{{ e.source }} {{ e.edition }} · {{ e.intent }}</strong
          ><small>{{ e.quote }}</small
          ><small>{{ e.reason }} · {{ e.reviewer }}</small></span
        ><span class="tag">{{ e.fit }}</span>
      </button>
    </details>
    <h3>采购联系方式</h3>
    <p v-if="buyer.contact" class="out-note">
      档案原有联系方式 · {{ buyer.contact }}
    </p>
    <div v-for="c in contacts" :key="c.id" class="out-row">
      <span
        ><strong>{{ c.kind }} · {{ c.value }}</strong
        ><small>{{ c.holder }} · {{ c.reviewer }}</small></span
      ><span
        ><a :href="safeLink(c.url)" target="_blank" rel="noopener noreferrer"
          >依据 ↗</a
        >
        <button
          type="button"
          class="textbtn"
          :disabled="busy"
          @click="
            run(async () => {
              await api(base + '/contacts/' + c.id, 'DELETE');
              emit('refresh');
              toast('联系方式已移除');
            })
          "
        >
          移除
        </button></span
      >
    </div>
    <div v-for="s in sources.items" :key="s.value" class="out-row">
      <span
        ><strong>{{ s.holder }}</strong
        ><small>{{ s.value }} · 公开资料候选</small></span
      >
      <button class="ghost" @click="form = { ...s }">填入待核实字段</button>
    </div>
    <button class="ghost" :disabled="busy" @click="run(() => lookup(true))">
      实时查找采购联系页
    </button>
    <p v-if="searched && !sources.pages.length">本次未查到联系页。</p>
    <a
      v-for="p in sources.pages"
      :key="p.url"
      :href="safeLink(p.url)"
      target="_blank"
      rel="noopener noreferrer"
      >{{ p.title }} ↗</a
    >
    <form @submit.prevent="run(contact)">
      <div class="fields">
        <label
          >联系类型<select v-model="form.kind">
            <option
              v-for="k in [
                '采购邮箱',
                '企业邮箱',
                '电话',
                'WhatsApp',
                'Facebook',
                '微信',
                '地址',
                '供应商入口',
              ]"
              :key="k"
            >
              {{ k }}
            </option>
          </select></label
        >
        <label
          >人员或部门<input required v-model.trim="form.holder" maxlength="180"
        /></label>
        <label
          >联系方式<input required v-model.trim="form.value" maxlength="700"
        /></label>
        <label
          >联系依据网址<input
            required
            type="url"
            v-model.trim="form.url"
            maxlength="1400"
        /></label>
      </div>
      <div class="actions">
        <a
          v-if="safeLink(form.url)"
          :href="safeLink(form.url)"
          target="_blank"
          rel="noopener noreferrer"
          >核对联系来源 ↗</a
        ><button class="ghost" :disabled="busy">保存核实联系方式</button>
      </div>
    </form>
    <details class="out-details" open>
      <summary>展位邀约邮件草稿</summary>
      <form @submit.prevent="run(generate)">
        <div class="fields">
          <label
            >展会名称（邮件用）<input
              required
              v-model.trim="invite.event"
              placeholder="Automechanika Shanghai"
              maxlength="150"
          /></label>
          <label
            >展馆及展位<input
              required
              v-model.trim="invite.booth"
              maxlength="80"
              placeholder="Hall / Booth"
          /></label>
          <label
            >开始日期<input
              required
              type="date"
              v-model="invite.starts" /></label
          ><label
            >结束日期<input
              required
              type="date"
              v-model="invite.ends"
              :min="invite.starts"
          /></label>
          <label
            >收件邮箱<select aria-label="收件邮箱" v-model="invite.contact_id">
              <option :value="null">待确认收件人</option>
              <option v-for="c in emails" :key="c.id" :value="c.id">
                {{ c.value }} · {{ c.holder }}
              </option>
            </select></label
          >
        </div>
        <button class="primary" :disabled="busy">生成英文邀约草稿</button>
      </form>
      <div v-if="drafts.length > 1">
        <label
          >已存草稿<select
            :value="draft?.id"
            @change="
              setDraft(
                drafts.find(
                  (d) =>
                    d.id === Number(($event.target as HTMLSelectElement).value),
                ),
              )
            "
          >
            <option v-for="d in drafts" :key="d.id" :value="d.id">
              {{ d.event }} · {{ d.starts }} · {{ d.booth }}
            </option>
          </select></label
        >
      </div>
      <form
        v-if="draft"
        class="formpad out-draft"
        @submit.prevent="run(saveDraft)"
      >
        <label
          >草稿收件人<select v-model="editEmail">
            <option :value="null">待确认</option>
            <option v-for="c in emails" :key="c.id" :value="c.id">
              {{ c.value }}
            </option>
          </select></label
        >
        <label
          >邮件主题<input
            required
            maxlength="350"
            v-model="draft.subject" /></label
        ><label
          >邮件正文<textarea
            required
            maxlength="8000"
            rows="10"
            v-model="draft.body"
          />
        </label>
        <div class="actions">
          <button class="ghost" :disabled="busy">保存草稿修改</button
          ><button type="button" class="ghost" @click="run(copy)">
            复制主题和正文
          </button>
        </div>
      </form>
    </details>
  </section>
</template>

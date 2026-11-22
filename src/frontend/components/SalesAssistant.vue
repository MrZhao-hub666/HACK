<script setup lang="ts">
import { nextTick, onActivated, ref, shallowRef } from "vue";
import { api, catalogTitle, errorMessage } from "../shared";
import type { AssistantAnswer, CatalogPart } from "../types";
import Icon from "./Icon.vue";
import ProductDetail from "./ProductDetail.vue";

type Message = { role: "customer"; text: string } | { role: "sales"; answer: AssistantAnswer };
const thread = ref<Message[]>([]);
const draft = ref("");
const pending = ref("");
const error = ref("");
const copyStatus = ref<{ index: number; text: string }>();
const log = ref<HTMLElement | null>(null);
const input = ref<HTMLTextAreaElement | null>(null);
const selection = shallowRef<{ part: CatalogPart; fields: AssistantAnswer["fields"]; button: HTMLButtonElement }>();
const detail = ref<HTMLElement | null>(null);
const formatAmount = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

async function scrollToLatest() {
  await nextTick();
  if (log.value) log.value.scrollTop = log.value.scrollHeight;
}
onActivated(scrollToLatest);

async function send() {
  const text = draft.value.trim();
  if (!text || pending.value) return;
  const turns = thread.value.flatMap<{ role: Message["role"]; text: string }>((message) =>
    message.role === "customer" ? [{ role: message.role, text: message.text }]
      : [{ role: message.role, text: message.answer.reply }],
  );
  if (turns.length >= 30) {
    error.value = "本次对话已达到长度上限，请新建对话继续。";
    return;
  }
  turns.push({ role: "customer", text });
  pending.value = text;
  error.value = "";
  scrollToLatest();
  try {
    const answer = await api<AssistantAnswer>("/sales-assistant", "POST", { turns });
    thread.value.push({ role: "customer", text }, { role: "sales", answer });
    draft.value = "";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    pending.value = "";
    scrollToLatest();
  }
}

function enter(event: KeyboardEvent) {
  if (event.isComposing) return;
  event.preventDefault();
  send();
}

function reset() {
  thread.value = [];
  draft.value = "";
  error.value = "";
  copyStatus.value = undefined;
  selection.value = undefined;
  input.value?.focus();
}

async function showProduct(part: CatalogPart, fields: AssistantAnswer["fields"], event: MouseEvent) {
  selection.value = { part, fields, button: event.currentTarget as HTMLButtonElement };
  await nextTick();
  if (matchMedia("(max-width: 1050px)").matches) detail.value?.focus();
}

async function closeProduct() {
  const button = selection.value?.button;
  selection.value = undefined;
  await nextTick();
  button?.focus();
}

async function copyReply(index: number, reply: string) {
  try {
    await navigator.clipboard.writeText(reply);
    copyStatus.value = { index, text: "已复制" };
  } catch {
    copyStatus.value = { index, text: "请选中回复并手动复制" };
  }
}
</script>

<template>
  <div class="assistant-layout" :class="{ 'with-detail': selection }">
  <section class="panel assistant-chat" aria-label="销售对话">
    <header class="chat-header">
      <span class="sect"><Icon name="chat" />客户需求</span>
      <button class="ghost" type="button" :disabled="!!pending || !thread.length && !draft" @click="reset">
        <Icon name="plus" size="sm" />新建对话
      </button>
    </header>
    <div ref="log" class="chat-log" role="log" aria-label="对话记录">
      <div class="chat-reply">
        <span class="assistant-symbol"><Icon name="spark" size="sm" /></span>
        <p class="chat-bubble">把客户的需求告诉我。旧件编号、车型或车桥，知道哪项就先说哪项。</p>
      </div>
      <template v-for="(message, index) in thread" :key="index">
        <div v-if="message.role === 'customer'" class="chat-sent">
          <p class="chat-bubble">{{ message.text }}</p>
        </div>
        <div v-else class="chat-reply">
          <span class="assistant-symbol"><Icon name="spark" size="sm" /></span>
          <div class="chat-response">
            <p class="chat-bubble" data-customer-reply>{{ message.answer.reply }}</p>
            <div class="reply-actions">
              <button class="textbtn" type="button" @click="copyReply(index, message.answer.reply)">复制对客答复</button>
              <span v-if="copyStatus?.index === index" role="status">{{ copyStatus.text }}</span>
              <span v-if="message.answer.mode">{{ message.answer.mode }}</span>
            </div>
            <p v-if="message.answer.count > message.answer.items.length" class="candidate-count">
              找到 {{ message.answer.count }} 个候选，先显示 {{ message.answer.items.length }} 个。
            </p>
            <article v-for="part in message.answer.items" :key="part.spec_id" class="product-answer">
              <button class="open-product" type="button" :aria-label="'查看 ' + catalogTitle(part) + ' 详情'"
                :aria-pressed="selection?.part.spec_id === part.spec_id"
                @click="showProduct(part, message.answer.fields, $event)"></button>
              <div class="answer-head">
                <h3>{{ catalogTitle(part) }}</h3>
                <span class="tag" :class="message.answer.confirmed ? 'blue' : 'amber'">
                  {{ message.answer.confirmed ? "目录对应" : "候选待核对" }}
                </span>
              </div>
              <p class="part-meta">{{ [part.spec_id, part.market, part.catalog_country, part.kind].filter(Boolean).join(" · ") }}</p>
              <p v-if="part.oe_ref || part.wva || part.fmsi || part.bfmc" class="part-meta">
                {{ [part.oe_ref && "OEM " + part.oe_ref, part.wva && "WVA " + part.wva,
                  part.fmsi && "FMSI " + part.fmsi, part.bfmc && "BFMC " + part.bfmc].filter(Boolean).join(" · ") }}
              </p>
              <span class="product-action" aria-hidden="true">查看详情 <Icon name="chevron" size="sm" /></span>
              <div v-if="message.answer.quote" class="answer-quote">
                <div>
                  <small>
                    {{ [message.answer.quote.basis, message.answer.quote.material,
                      message.answer.quote.unit_only ? "单片价" : message.answer.quote.quantity + " " + message.answer.quote.unit].filter(Boolean).join(" · ") }}
                  </small>
                  <strong>{{ message.answer.quote.currency }} {{ formatAmount.format(Number(message.answer.quote.unit_only ? message.answer.quote.unit_price : message.answer.quote.total)) }}</strong>
                </div>
                <span v-if="!message.answer.quote.unit_only">{{ formatAmount.format(Number(message.answer.quote.unit_price)) }} / {{ message.answer.quote.unit }}</span>
              </div>
            </article>
            <p v-if="message.answer.question && !message.answer.reply.includes(message.answer.question)"
              class="part-meta">{{ message.answer.question }}</p>
          </div>
        </div>
      </template>
      <template v-if="pending">
        <div class="chat-sent"><p class="chat-bubble">{{ pending }}</p></div>
        <p class="chat-progress" role="status">正在理解需求、查阅目录并核对报价…</p>
      </template>
    </div>
    <form class="composer" @submit.prevent="send">
      <p v-if="error" class="notice composer-error" role="alert">{{ error }}</p>
      <textarea
        ref="input"
        v-model="draft"
        aria-label="客户需求"
        :placeholder="thread.length ? '补充客户确认的信息…' : '简述客户要什么…'"
        maxlength="3000"
        rows="2"
        enterkeyhint="send"
        :disabled="!!pending"
        @keydown.enter.exact="enter"
      ></textarea>
      <button class="primary" :disabled="!!pending || !draft.trim()">发送 <Icon name="arrow" size="sm" /></button>
    </form>
  </section>
  <aside v-if="selection" ref="detail" class="assistant-detail" aria-label="已选产品" tabindex="-1"
    @keydown.esc.stop="closeProduct">
    <ProductDetail :part="selection.part" :labels="selection.fields">
      <template #actions>
        <button class="ghost detail-close" type="button" @click="closeProduct">
          <Icon name="close" size="sm" />关闭详情
        </button>
      </template>
    </ProductDetail>
  </aside>
  </div>
</template>

<style scoped>
.assistant-layout {
  --assistant-height: clamp(440px, calc(100dvh - 208px), 790px);
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: var(--space-12);
}
.assistant-chat {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  max-width: 980px;
  height: var(--assistant-height);
  overflow: hidden;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  padding: var(--space-12) var(--space-20);
  color: var(--navy);
  font-weight: var(--weight-semibold);
  border-bottom: 1px solid var(--line);
}
.chat-log {
  padding: var(--space-20);
  display: flex;
  flex-direction: column;
  gap: var(--space-16);
  overflow: auto;
  scrollbar-color: var(--line) var(--paper);
}
.chat-reply {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: var(--space-8);
  width: min(100%, 650px);
}
.chat-reply .assistant-symbol { margin-top: var(--space-2); }
.chat-bubble {
  width: fit-content;
  padding: var(--space-8) var(--space-12);
  background: var(--surface-selected);
  border-radius: var(--radius-card);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.chat-sent { align-self: end; max-width: min(84%, 600px); }
.chat-sent .chat-bubble { background: var(--orange-pale); }
.chat-response { display: grid; gap: var(--space-8); }
.candidate-count, .part-meta, .chat-progress { font: var(--type-caption); color: var(--ink-secondary); }
.reply-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-4) var(--space-12);
  font: var(--type-caption);
  color: var(--ink-secondary);
}
.product-answer {
  position: relative;
  padding: var(--space-12);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
}
.product-answer:has(.open-product:hover) { background: var(--surface-hover); }
.product-answer:has(.open-product[aria-pressed="true"]) {
  background: var(--surface-selected);
  border-color: var(--blue);
}
.open-product { position: absolute; inset: 0; width: 100%; border-radius: inherit; }
.product-action {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-top: var(--space-8);
  color: var(--navy);
  font: var(--type-caption);
}
.assistant-detail { min-width: 0; scroll-margin-top: var(--space-12); }
.detail-close { flex: none; }
.answer-head, .answer-quote {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  flex-wrap: wrap;
}
.answer-head h3, .part-meta, .answer-quote strong { overflow-wrap: anywhere; }
.part-meta { margin-top: var(--space-4); }
.answer-quote {
  margin-top: var(--space-8);
  padding-top: var(--space-8);
  border-top: 1px solid var(--line);
  color: var(--navy);
}
.answer-quote strong {
  display: block;
  font: var(--type-title-large);
  font-variant-numeric: tabular-nums;
}
.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--space-8);
  border-top: 1px solid var(--line);
  padding: var(--space-12) var(--space-20);
}
.composer-error { grid-column: 1 / -1; margin: 0; }
.composer textarea {
  width: 100%;
  min-width: 0;
  padding: var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  color: var(--ink);
  background: var(--paper);
  resize: vertical;
  max-height: 28dvh;
}
.composer textarea::placeholder { color: var(--muted); }
@media (max-width: 680px) {
  .assistant-layout { --assistant-height: clamp(440px, calc(100dvh - 178px), 790px); }
  .chat-header, .chat-log, .composer { padding-inline: var(--space-12); }
  .composer textarea { font-size: 16px; }
}
@media (min-width: 1051px) {
  .assistant-layout.with-detail {
    grid-template-columns: minmax(0, 1fr) minmax(300px, 0.68fr);
  }
  .assistant-detail { max-height: var(--assistant-height); overflow: auto; }
}
</style>

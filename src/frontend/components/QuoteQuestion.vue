<script setup lang="ts">
import { ref } from "vue";
import { api, errorMessage } from "../shared";
import type { QuoteAnswer } from "../types";

const example = "外弧 200，宽度 100，厚度 18/22，半金属，100 片多少钱？";
const question = ref("");
const answer = ref<QuoteAnswer>();
const busy = ref(false);
const error = ref("");

function clearAnswer() {
  answer.value = undefined;
  error.value = "";
}

async function ask() {
  if (!question.value.trim() || busy.value) return;
  clearAnswer();
  busy.value = true;
  try {
    answer.value = await api<QuoteAnswer>("/copilot/quote", "POST", {
      question: question.value.trim(),
    });
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="quote-form" @submit.prevent="ask">
    <label for="quote-question">报价问题</label>
    <p id="quote-help">填写材料名称和毫米尺寸，附上片数可计算总价。</p>
    <textarea
      id="quote-question"
      v-model="question"
      aria-describedby="quote-help"
      rows="4"
      maxlength="3000"
      :placeholder="example"
      :readonly="busy"
      required
      @input="clearAnswer"
    />
    <div class="quote-actions">
      <button class="primary" :disabled="busy || !question.trim()">
        {{ busy ? "正在核算…" : "计算报价" }}
      </button>
      <button
        type="button"
        class="textbtn"
        :disabled="busy"
        @click="question = example; clearAnswer()"
      >
        填入示例
      </button>
    </div>
  </form>
  <p v-if="error" class="notice" role="alert">{{ error }}</p>
  <div v-if="answer" class="quote-answer" role="status">
    <template v-if="answer.quote">
      <div class="quote-amount">
        <span>单片试算</span>
        <strong>{{ answer.quote.unit_price }} 元</strong>
      </div>
      <p v-if="answer.quote.total !== null">
        {{ answer.quote.quantity }} 片合计
        <b>{{ answer.quote.total }} 元</b>
      </p>
      <p class="quote-basis">
        {{ answer.quote.material }} · {{ answer.quote.price_per_tonne }} 元/吨
      </p>
      <ul class="quote-dimensions" aria-label="核算尺寸">
        <li v-for="(value, label) in answer.quote.dimensions" :key="label">
          {{ label }} {{ value }} mm
        </li>
      </ul>
    </template>
    <template v-else>
      <p><b>请在原问题里补充{{ answer.missing.join("、") }}。</b></p>
      <p v-if="answer.missing.includes('材料名称')" class="quote-basis">
        预设材料有 {{ answer.materials.join("、") }}。
      </p>
    </template>
  </div>
</template>

<style scoped>
.quote-form {
  display: grid;
  gap: var(--space-8);
}
.quote-form label {
  font: var(--type-title-medium);
}
.quote-form p,
.quote-basis,
.quote-dimensions {
  color: var(--ink-secondary);
}
.quote-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-12);
}
.quote-answer {
  margin-top: var(--space-16);
  padding: var(--space-16);
  background: var(--surface-selected);
  border-radius: var(--radius-card);
  overflow-wrap: anywhere;
}
.quote-answer p {
  margin-top: var(--space-4);
}
.quote-amount {
  display: grid;
  color: var(--navy);
}
.quote-amount strong {
  font: var(--type-headline-medium);
}
.quote-dimensions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-12);
  list-style: none;
  padding: 0;
  margin: var(--space-8) 0 0;
  font: var(--type-caption);
}
</style>

<script setup lang="ts">
import { ref } from "vue";
import { api, errorMessage } from "../shared";
import type { Session } from "../types";

defineProps<{ username: string }>();
const emit = defineEmits<{ saved: [session: Session] }>();
const current = ref(""),
  password = ref(""),
  confirm = ref(""),
  error = ref(""),
  busy = ref(false);
async function save() {
  if (busy.value) return;
  error.value = "";
  if (password.value !== confirm.value) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  busy.value = true;
  try {
    const result = await api<Session>("/auth/password", "POST", {
      current_password: current.value,
      password: password.value,
    });
    current.value = password.value = confirm.value = "";
    emit("saved", result);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <form class="auth-form" @submit.prevent="save">
    <input
      type="text"
      :value="username"
      name="username"
      autocomplete="username"
      hidden
    />
    <label
      >当前密码<input
        v-model="current"
        required
        type="password"
        autocomplete="current-password"
        maxlength="256"
    /></label>
    <label
      >新密码<input
        v-model="password"
        required
        type="password"
        minlength="12"
        maxlength="256"
        autocomplete="new-password"
        placeholder="至少 12 个字符"
    /></label>
    <label
      >确认新密码<input
        v-model="confirm"
        required
        type="password"
        minlength="12"
        maxlength="256"
        autocomplete="new-password"
    /></label>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <button class="primary" :disabled="busy">
      {{ busy ? "正在保存…" : "保存新密码" }}
    </button>
  </form>
</template>

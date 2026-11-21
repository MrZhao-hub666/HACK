<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import App from "./App.vue";
import LoginView from "./components/LoginView.vue";
import AccountPanel from "./components/AccountPanel.vue";
import { api, ApiError, errorMessage, notify } from "./shared";
import type { Session } from "./types";

const session = ref<Session | null>(null);
const checking = ref(true);
const problem = ref("");
const workspace = ref<InstanceType<typeof App> | null>(null);
const account = ref<InstanceType<typeof AccountPanel> | null>(null);
let revision = 0;
let timer: ReturnType<typeof setTimeout>;
const changes =
  typeof BroadcastChannel === "function"
    ? new BroadcastChannel("kooying-account")
    : null;

function apply(value: Session | null) {
  ++revision;
  clearTimeout(timer);
  if (value?.user.id !== session.value?.user.id) notify.value = "";
  session.value = value;
  checking.value = false;
  problem.value = "";
  if (value)
    timer = setTimeout(
      restore,
      Math.max(100, value.expires_at * 1000 - Date.now() + 100),
    );
}
function updated(value: Session | null) {
  apply(value);
  changes?.postMessage("changed");
}
async function restore() {
  const seq = ++revision;
  try {
    const value = await api<Session>("/auth/me");
    if (seq === revision) apply(value);
  } catch (err) {
    if (seq !== revision) return;
    apply(null);
    if (!(err instanceof ApiError && err.status === 401))
      problem.value = errorMessage(err);
  }
}
function visible() {
  if (!document.hidden) restore();
}
onMounted(() => {
  restore();
  if (changes) changes.onmessage = restore;
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("workspace-session-invalid", restore);
});
onBeforeUnmount(() => {
  ++revision;
  clearTimeout(timer);
  changes?.close();
  document.removeEventListener("visibilitychange", visible);
  window.removeEventListener("workspace-session-invalid", restore);
});
</script>
<template>
  <div v-if="checking || problem" class="session-loading">
    <div class="panel">
      <img src="/assets/kooying-logo.png" alt="冠英" width="160" />
      <p :role="problem ? 'alert' : 'status'">
        {{ problem || "正在读取登录状态…" }}
      </p>
      <button v-if="problem" class="ghost" @click="restore">重新连接</button>
    </div>
  </div>
  <LoginView
    v-else-if="!session || session.user.must_change"
    :user="session?.user"
    @authenticated="updated"
    @signed-out="updated(null)"
  />
  <template v-else>
    <App
      ref="workspace"
      :key="session.user.id"
      :user="session.user"
      @account="account?.show()"
    />
    <AccountPanel
      @closed="workspace?.reload()"
      :key="session.user.username"
      ref="account"
      :user="session.user"
      @authenticated="updated"
      @signed-out="updated(null)"
    />
  </template>
</template>

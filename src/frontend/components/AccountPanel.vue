<script setup lang="ts">
import { ref } from "vue";
import Icon from "./Icon.vue";
import PasswordForm from "./PasswordForm.vue";
import Members from "./Members.vue";
import { api, errorMessage } from "../shared";
import type { Session, User } from "../types";

defineProps<{ user: User }>();
const emit = defineEmits<{
  authenticated: [session: Session];
  signedOut: [];
  closed: [];
}>();
const dialog = ref<HTMLDialogElement | null>(null);
const tab = ref<"profile" | "members">("profile"),
  editing = ref(false),
  message = ref(""),
  error = ref("");
function show() {
  tab.value = "profile";
  editing.value = false;
  message.value = "";
  error.value = "";
  dialog.value?.showModal();
}
function saved(session: Session) {
  editing.value = false;
  message.value = "密码已更新，其他设备需要重新登录。";
  emit("authenticated", session);
}
async function logout() {
  try {
    await api("/auth/logout", "POST");
    dialog.value?.close();
    emit("signedOut");
  } catch (err) {
    error.value = errorMessage(err);
  }
}
defineExpose({ show });
</script>
<template>
  <dialog
    @close="
      tab = 'profile';
      editing = false;
      emit('closed');
    "
    ref="dialog"
    class="dialogwrap account-dialog"
    aria-labelledby="account-title"
  >
    <div class="dialog">
      <div class="line">
        <h2 id="account-title">账号与团队</h2>
        <button
          class="icon-btn"
          aria-label="关闭账号面板"
          @click="dialog?.close()"
        >
          <Icon name="close" size="md" />
        </button>
      </div>
      <div class="brief-tabs">
        <button :aria-pressed="tab === 'profile'" @click="tab = 'profile'">
          我的账号</button
        ><button
          v-if="user.role === 'admin'"
          :aria-pressed="tab === 'members'"
          @click="tab = 'members'"
        >
          成员管理
        </button>
      </div>
      <section v-if="tab === 'profile'" class="account-section">
        <div class="account-identity">
          <span class="avatar">{{ user.display_name.slice(-1) }}</span>
          <div>
            <h3>{{ user.display_name }}</h3>
            <small
              >{{ user.username }} ·
              {{ user.role === "admin" ? "管理员" : "销售成员" }}</small
            >
          </div>
        </div>
        <p v-if="message" class="auth-help" role="status">{{ message }}</p>
        <button
          class="ghost"
          :aria-expanded="editing"
          @click="editing = !editing"
        >
          {{ editing ? "取消修改" : "修改密码" }}
        </button>
        <PasswordForm v-if="editing" :username="user.username" @saved="saved" />
        <div class="signout">
          <button class="textbtn" @click="logout">
            <Icon name="logout" size="sm" />退出登录
          </button>
        </div>
        <p v-if="error" class="notice" role="alert">{{ error }}</p>
      </section>
      <Members v-else-if="user.role === 'admin'" :current-id="user.id" />
    </div>
  </dialog>
</template>

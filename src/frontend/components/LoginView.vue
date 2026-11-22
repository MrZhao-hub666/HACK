<script setup lang="ts">
import { ref } from "vue";
import Icon from "./Icon.vue";
import PasswordForm from "./PasswordForm.vue";
import { api, errorMessage } from "../shared";
import type { Session, User } from "../types";

defineProps<{ user?: User }>();
const emit = defineEmits<{
  authenticated: [session: Session];
  signedOut: [];
}>();
const username = ref(""),
  password = ref(""),
  remember = ref(false),
  showPassword = ref(false);
const error = ref(""),
  busy = ref(false),
  help = ref(false);
async function login() {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await api<Session>("/auth/login", "POST", {
      username: username.value.trim(),
      password: password.value,
      remember: remember.value,
    });
    password.value = "";
    showPassword.value = false;
    emit("authenticated", result);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
async function logout() {
  try {
    await api("/auth/logout", "POST");
    error.value = "";
    emit("signedOut");
  } catch (err) {
    error.value = errorMessage(err);
  }
}
</script>
<template>
  <main class="login-page">
    <div class="login-frame">
      <div class="login-brand">
        <img src="/assets/kooying-logo.png" alt="KOOYING 冠英汽车零部件" />
      </div>
      <div class="login-card">
        <section class="login-visual" aria-labelledby="workspace-name">
          <div class="login-picture" aria-hidden="true"></div>
          <div class="login-intro">
            <h2 id="workspace-name">海外销售工作台</h2>
            <p>在一个工作区处理海外询盘、跟进买家和安排交接。</p>
          </div>
        </section>
        <section class="login-fields" :key="user?.id || 0">
          <span class="auth-mark"><Icon name="lock" size="lg" /></span>
          <h1>{{ user ? "设置新密码" : "登录工作台" }}</h1>
          <p class="auth-sub">
            {{
              user
                ? user.display_name +
                  "，首次使用临时密码登录，请设置自己的密码。"
                : "使用管理员为你开通的团队账号登录。"
            }}
          </p>
          <PasswordForm
            v-if="user"
            :username="user.username"
            @saved="emit('authenticated', $event)"
          />
          <form v-else class="auth-form" @submit.prevent="login">
            <label
              >账号<span class="auth-input"
                ><Icon name="user" size="md" /><input
                  required
                  v-model="username"
                  autocomplete="username"
                  name="username"
                  autocapitalize="none"
                  spellcheck="false"
                  maxlength="48"
                  placeholder="输入团队账号" /></span
            ></label>
            <label
              >密码<span class="auth-input"
                ><Icon name="lock" size="md" /><input
                  required
                  v-model="password"
                  :type="showPassword ? 'text' : 'password'"
                  name="password"
                  autocomplete="current-password"
                  maxlength="256"
                  placeholder="输入密码" />
                <button
                  type="button"
                  class="reveal-password"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  :aria-pressed="showPassword"
                  @click="showPassword = !showPassword"
                >
                  <Icon
                    :name="showPassword ? 'eyeOff' : 'eye'"
                  /></button></span
            ></label>
            <div class="auth-options">
              <label class="remember"
                ><input type="checkbox" v-model="remember" />保持登录 14
                天</label
              ><button
                type="button"
                class="textbtn"
                :aria-expanded="help"
                @click="help = !help"
              >
                忘记密码？
              </button>
            </div>
            <p class="auth-help" v-if="help">
              请联系团队管理员重置密码。使用新的临时密码登录后，即可设置自己的密码。
            </p>
            <p v-if="error" class="notice" role="alert">{{ error }}</p>
            <button class="primary login-submit" :disabled="busy">
              {{ busy ? "正在登录…" : "登录" }}<Icon name="arrow" size="md" />
            </button>
          </form>
          <template v-if="user"
            ><button class="textbtn" @click="logout">退出并切换账号</button>
            <p v-if="error" class="notice" role="alert">
              {{ error }}
            </p></template
          >
        </section>
      </div>
    </div>
  </main>
</template>

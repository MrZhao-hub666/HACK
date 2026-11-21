<script setup lang="ts">
import LoadingSkeleton from "./LoadingSkeleton.vue";
import { onMounted, ref } from "vue";
import Icon from "./Icon.vue";
import { api, errorMessage, toast } from "../shared";
import type { User } from "../types";

defineProps<{ currentId: number }>();
const users = ref<User[] | null>(null),
  action = ref<"list" | "create" | "reset">("list");
const target = ref<User | null>(null),
  username = ref(""),
  name = ref(""),
  password = ref("");
const role = ref<User["role"]>("sales"),
  busy = ref(false),
  error = ref(""),
  message = ref("");
async function load() {
  error.value = "";
  try {
    users.value = await api<User[]>("/auth/members");
  } catch (err) {
    error.value = errorMessage(err);
  }
}
function start(mode: typeof action.value, member: User | null = null) {
  action.value = mode;
  target.value = member;
  username.value = name.value = password.value = "";
  role.value = "sales";
  error.value = message.value = "";
}
async function save() {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    if (action.value === "create")
      await api("/auth/members", "POST", {
        username: username.value,
        display_name: name.value,
        role: role.value,
        password: password.value,
      });
    else
      await api("/auth/members/" + target.value!.id + "/password", "POST", {
        password: password.value,
      });
    const created = action.value === "create";
    start("list");
    message.value = created ? "新成员首次登录时须更换密码。" : "该成员原有登录会话已失效。";
    toast(created ? "成员已创建" : "临时密码已重置");
    await load();
  } catch (err) {
    error.value = errorMessage(err);
    toast("成员信息保存失败", "error");
  } finally {
    busy.value = false;
  }
}
async function toggle(member: User) {
  if (busy.value) return;
  busy.value = true;
  error.value = message.value = "";
  try {
    await api("/auth/members/" + member.id, "PATCH", {
      active: !member.active,
    });
    toast(
      member.display_name +
        (member.active ? "的账号已停用" : "的账号已启用"),
    );
    await load();
  } catch (err) {
    error.value = errorMessage(err);
    toast("账号状态更新失败", "error");
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="member-section">
    <div v-if="action === 'list'">
      <div class="line">
        <h3>
          团队成员<span v-if="users"> · {{ users.length }}</span>
        </h3>
        <button class="primary" @click="start('create')">
          <Icon name="addUser" size="sm" />添加成员
        </button>
      </div>
      <LoadingSkeleton
        v-if="!users && !error"
        layout="rows"
        label="正在加载团队成员"
      />
      <ul v-else-if="users" class="member-list">
        <li v-for="m in users" :key="m.id">
          <div>
            <strong>{{ m.display_name }}</strong>
            <span class="tag">{{
              m.active ? (m.must_change ? "待改密" : "已启用") : "已停用"
            }}</span>
            <small
              >{{ m.username }} ·
              {{ m.role === "admin" ? "管理员" : "销售成员" }}</small
            >
          </div>
          <div v-if="m.id !== currentId" class="actions">
            <button class="textbtn" :disabled="busy" @click="start('reset', m)">
              重置密码</button
            ><button class="ghost" :disabled="busy" @click="toggle(m)">
              {{ m.active ? "停用" : "启用" }}
            </button>
          </div>
        </li>
      </ul>
    </div>
    <form v-else class="auth-form" @submit.prevent="save">
      <h3>
        {{
          action === "create"
            ? "添加团队成员"
            : "重置 " + target?.display_name + " 的密码"
        }}
      </h3>
      <template v-if="action === 'create'">
        <label
          >登录账号<input
            v-model.trim="username"
            required
            minlength="3"
            maxlength="48"
            pattern="[a-z0-9][a-z0-9._\-]{2,47}"
            placeholder="如 chen.zhou"
            autocomplete="off"
        /></label>
        <label
          >成员姓名<input
            v-model.trim="name"
            required
            maxlength="40"
            placeholder="用于分派和跟进记录"
        /></label>
        <label
          >角色<select v-model="role">
            <option value="sales">销售成员</option>
            <option value="admin">管理员</option>
          </select></label
        >
      </template>
      <label
        >临时密码<input
          v-model="password"
          required
          type="password"
          minlength="12"
          maxlength="256"
          autocomplete="new-password"
          placeholder="至少 12 个字符"
      /></label>
      <p class="hint">将临时密码单独交给该成员，首次登录时会要求修改。</p>
      <div class="actions">
        <button class="primary" :disabled="busy">
          {{ action === "create" ? "创建成员" : "确认重置" }}</button
        ><button
          class="ghost"
          type="button"
          :disabled="busy"
          @click="start('list')"
        >
          取消
        </button>
      </div>
    </form>
    <p v-if="message" class="auth-help" role="status">{{ message }}</p>
    <p v-if="error" class="notice" role="alert">
      {{ error }}
      <button v-if="action === 'list'" class="textbtn" @click="load">
        刷新名单
      </button>
    </p>
  </section>
</template>

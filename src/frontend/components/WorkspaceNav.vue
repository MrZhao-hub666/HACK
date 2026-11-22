<script setup lang="ts">
import { navigation } from "./workspace";
import Icon from "./Icon.vue";
import type { Page, User } from "../types";

defineProps<{
  page: Page;
  waiting: number;
  recommendations: number;
  user: User;
}>();
const emit = defineEmits<{
  go: [id: Page];
  account: [];
  brief: [];
}>();
</script>

<template>
  <div class="brand">
    <img
      src="/assets/kooying-logo.png"
      alt="KOOYING 冠英汽车零部件"
      width="174"
      height="37"
    />
  </div>
  <nav aria-label="工作台导航">
    <section v-for="group in navigation" :key="group.title">
      <h2 class="nav-label">{{ group.title }}</h2>
      <button
        v-for="n in group.pages"
        :key="n.id"
        :aria-current="page === n.id ? 'page' : undefined"
        :class="{ selected: page === n.id }"
        @click="emit('go', n.id)"
      >
        <icon :name="n.icon" size="md" /><span>{{ n.name }}</span>
        <em
          v-if="n.id === 'inbox' && waiting"
          :aria-label="waiting + ' 条业务待回'"
          >{{ waiting }}</em
        >
      </button>
    </section>
  </nav>
  <div class="sidebar-foot">
    <button class="assistant-entry" @click="emit('brief')">
      <span class="assistant-symbol"><icon name="spark" size="md" /></span
      ><b>跟进简报</b
      ><span
        v-if="recommendations"
        class="assistant-count"
        :aria-label="recommendations + ' 个待处理推荐'"
        >{{ recommendations }}</span
      ><icon name="chevron" size="sm" />
    </button>
    <button
      class="profile account-entry"
      aria-label="我的账号与团队"
      @click="emit('account')"
    >
      <span class="avatar">{{ user.display_name.slice(-1) }}</span>
      <span class="profile-name"
        ><strong>{{ user.display_name }}</strong
        ><small>{{
          user.role === "admin" ? "工作台管理员" : "销售成员"
        }}</small></span
      >
      <icon name="chevron" size="sm" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { navigation } from "./workspace";
import Icon from "./Icon.vue";
import type { Page, Config } from "../types";

defineProps<{ page: Page; waiting: number; actor: string; config: Config }>();
const emit = defineEmits<{
  go: [id: Page];
  actor: [name: string];
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
      ><b>Copilot 助手</b><icon name="chevron" size="sm" />
    </button>
    <div class="profile">
      <span class="avatar">{{ actor.slice(-1) }}</span>
      <label
        ><small>当前销售</small
        ><select
          aria-label="当前销售"
          :value="actor"
          @change="
            emit(
              'actor',
              ($event.target as HTMLInputElement | HTMLSelectElement).value,
            )
          "
        >
          <option v-for="name in config.team" :key="name">{{ name }}</option>
        </select></label
      >
    </div>
  </div>
</template>

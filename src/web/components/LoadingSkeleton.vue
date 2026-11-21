<script setup lang="ts">
defineProps<{
  layout: "inbox" | "detail" | "rows" | "cards" | "form" | "chart" | "lines";
  label?: string;
}>();
</script>

<template>
  <div
    class="loading-skeleton"
    :data-layout="layout"
    :role="label ? 'status' : undefined"
  >
    <span v-if="label" class="sr-only">{{ label }}</span>
    <div aria-hidden="true" inert class="skeleton-paint">
      <div v-if="layout === 'inbox'" class="sk-toolbar">
        <span class="sk-shape sk-field"></span
        ><span class="sk-shape sk-short"></span>
      </div>
      <div :class="{ split: layout === 'inbox' }">
        <div
          v-if="layout === 'rows' || layout === 'inbox'"
          :class="{ ticketlist: layout === 'inbox' }"
        >
          <div v-for="n in 4" :key="n" class="sk-row">
            <span class="sk-shape sk-tile"></span>
            <div class="sk-stack">
              <span class="sk-shape sk-medium"></span
              ><span class="sk-shape sk-long"></span>
            </div>
          </div>
        </div>
        <div
          v-if="layout === 'detail' || layout === 'inbox'"
          class="sk-detail sk-stack"
        >
          <span class="sk-shape sk-short"></span>
          <span class="sk-shape sk-heading"></span>
          <span class="sk-shape sk-medium"></span>
          <div v-for="n in 2" :key="n" class="sk-box sk-stack">
            <span class="sk-shape sk-short"></span
            ><span class="sk-shape sk-long"></span
            ><span class="sk-shape sk-medium"></span>
          </div>
        </div>
        <div v-if="layout === 'cards'" class="cards">
          <div v-for="n in 3" :key="n" class="sk-card sk-stack">
            <span class="sk-shape sk-tile"></span
            ><span class="sk-shape sk-heading"></span>
            <span class="sk-shape sk-long"></span
            ><span class="sk-shape sk-medium"></span>
          </div>
        </div>
        <div v-if="layout === 'form'" class="formpad sk-stack">
          <div class="fields">
            <div v-for="n in 3" :key="n" class="sk-stack">
              <span class="sk-shape sk-short"></span
              ><span class="sk-shape sk-field"></span>
            </div>
          </div>
          <span class="sk-shape sk-field sk-long"></span
          ><span class="sk-shape sk-medium"></span>
        </div>
        <div v-if="layout === 'chart'" class="sk-chart">
          <div class="channel-chart"><span class="sk-ring"></span></div>
          <div class="legend">
            <span v-for="n in 4" :key="n" class="sk-shape sk-long"></span>
          </div>
        </div>
        <div v-if="layout === 'lines'" class="sk-stack sk-lines">
          <span class="sk-shape sk-long"></span
          ><span class="sk-shape sk-medium"></span>
        </div>
      </div>
    </div>
  </div>
</template>

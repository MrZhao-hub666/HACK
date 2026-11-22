<script setup lang="ts">
import { onMounted, onUnmounted, shallowRef, watch } from "vue";
import { notify, type ToastTone } from "../shared";
import type { IconName } from "../icons";
import Icon from "./Icon.vue";

const icons: Record<ToastTone, IconName> = {
  success: "check", info: "info", warning: "warning", error: "error",
};
const target = shallowRef<HTMLElement>(document.body);
function updateTarget() {
  // A modal is above the page and makes content outside it inert.
  target.value = document.querySelector<HTMLDialogElement>("dialog[open]") ?? document.body;
}
let observer: MutationObserver | undefined;
onMounted(() => {
  const root = document.getElementById("app");
  if (!root) return;
  observer = new MutationObserver(() => { if (notify.value) updateTarget(); });
  observer.observe(root, { childList: true, subtree: true, attributeFilter: ["open"] });
});
onUnmounted(() => observer?.disconnect());
watch(notify, updateTarget, { flush: "sync" });
</script>

<template>
  <Teleport :to="target">
    <span class="sr-only" aria-live="polite" aria-atomic="true">
      {{ notify?.tone !== 'error' ? notify?.message : '' }}
    </span>
    <span class="sr-only" aria-live="assertive" aria-atomic="true">
      {{ notify?.tone === 'error' ? notify.message : '' }}
    </span>
    <Transition name="toast">
      <div v-if="notify" class="toast" :class="`toast-${notify.tone}`" aria-hidden="true">
        <Icon :name="icons[notify.tone]" size="sm" />
        <span>{{ notify.message }}</span>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.toast {
  position: fixed;
  z-index: 12;
  inset-inline-end: var(--space-16);
  inset-block-end: calc(var(--space-16) + env(safe-area-inset-bottom, 0px));
  display: flex;
  align-items: flex-start;
  gap: var(--space-8);
  max-width: min(26rem, calc(100% - 2 * var(--space-16)));
  padding: var(--space-12) var(--space-16);
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  color: var(--ink);
  background: var(--paper);
  box-shadow: var(--elevation-overlay);
  font: var(--type-label);
  overflow-wrap: anywhere;
  pointer-events: none;
}
.toast svg { color: var(--toast-accent); margin-top: var(--space-2); }
.toast-success { --toast-accent: #287469; }
.toast-info { --toast-accent: var(--blue); }
.toast-warning { --toast-accent: var(--orange-ink); }
.toast-error { --toast-accent: #a82e33; }
</style>

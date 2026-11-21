<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 });
const paths: Record<string, string> = {
  dashboard: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  building: "M3 21h18 M5 21V4l10-1v18 M15 9h4v12 M8 8h3 M8 12h3 M8 16h3",
  pen: "M3 21l5-1 12-12-4-4L4 16z M14 6l4 4 M12 21h9",
  spark:
    "M11 3l1.8 5.7L18.5 11l-5.7 2.2L11 19l-2.2-5.8L3 11l5.8-2.3z M19.5 2v4 M17.5 4h4 M20 16v5 M17.5 18.5h5",
  chevron: "M9 5l7 7-7 7",
  close: "M6 6l12 12 M18 6L6 18",
  menu: "M3 6h18 M3 12h18 M3 18h18",
  calendar: "M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16",
  chart: "M11 3a9 9 0 1 0 10 10H11z M15 3.5V9h5.5A8 8 0 0 0 15 3.5z",
  upRight: "M6 18L18 6 M7 6h11v11",
  userClock:
    "M11 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M3 21v-2a6 6 0 0 1 9-5 M21 17a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M17 15v2l1 1",
  bolt: "M4 17l6-10 4 4 6-5-6 11-4-4z",
  message: "M20 4H4v13h5v4l5-4h6z M8 9h8 M8 12h5",
  form: "M5 3h10l4 4v14H5z M14 3v5h5 M8 12h8 M8 16h6",
  chat: "M3 5h14v10h-8l-4 3v-3H3z M18 10h3v9h-2v2l-4-2h-4v-2",
  inbox: "M3 13l3-8h12l3 8v6H3z M3 13h5l2 3h4l2-3h5",
  compass: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M16 8l-2.5 5.5L8 16l2.5-5.5z",
  users:
    "M15 20v-2a5 5 0 0 0-10 0v2 M10 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M16 5a3 3 0 0 1 0 6 M18 14a4 4 0 0 1 3 4v2",
  radio:
    "M7 7a7 7 0 0 0 0 10 M17 7a7 7 0 0 1 0 10 M4 4a11 11 0 0 0 0 16 M20 4a11 11 0 0 1 0 16 M14 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
  search: "M16 16l5 5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  external: "M14 4h6v6 M19 5l-9 9 M11 5H5v14h14v-6",
  plus: "M12 5v14 M5 12h14",
  globe:
    "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c-5 4-5 14 0 18 5-4 5-14 0-18",
  check: "M4 12l5 5L20 6",
  moon: "M20 14a8 8 0 0 1-10-11A9 9 0 1 0 21 14z",
  layers: "M12 3l9 5-9 5-9-5z M3 12l9 5 9-5 M3 16l9 5 9-5",
  box: "M4 4h16v16H4z",
  back: "M19 12H5 M10 7l-5 5 5 5",
  refresh:
    "M20 5v6h-6 M4 19v-6h6 M5 9a8 8 0 0 1 14-3l1 5 M4 13l1 5a8 8 0 0 0 14-3",
  list: "M8 6h13 M8 12h13 M8 18h13 M3 6h1 M3 12h1 M3 18h1",
};
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.box" />
  </svg>
</template>

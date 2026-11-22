<script setup lang="ts">
import { computed, ref, useId, watch } from "vue";
import { catalogMedia, catalogTitle } from "../shared";
import type { CatalogPart } from "../types";
import Icon from "./Icon.vue";

const props = defineProps<{ part: CatalogPart; labels: Record<string, string> }>();
const viewsOpen = ref(false);
const viewsId = useId();
watch(() => props.part.spec_id, () => { viewsOpen.value = false; });
const fields = computed(() => {
  const part = props.part;
  const repeated = ["spec_id", "code", "name", "source", "market", "kind"];
  return Object.entries(props.labels).flatMap(([key, label]) => {
    const value = part[key];
    return typeof value === "string" && value && !repeated.includes(key) ? [{ key, label, value }] : [];
  });
});
function validPhotos(images: CatalogPart["images"]) {
  return images.flatMap((image) => {
    const url = catalogMedia(image.url);
    return url ? [{ url, label: image.label }] : [];
  });
}
const photos = computed(() => {
  const part = props.part;
  const real = validPhotos(part.images);
  if (real.length) return real;
  const crop = catalogMedia(part.sources[0]?.crop ?? null);
  return crop ? [{ url: crop, label: "目录规格原图" }] : [];
});
const views = computed(() => validPhotos(props.part.photo_views ?? []));
</script>

<template>
  <article class="panel product-detail" aria-label="产品详情">
    <div class="detail-top">
      <div>
        <h2>{{ catalogTitle(part) }}</h2>
        <p>{{ [part.code && part.name !== part.code && part.name, part.spec_id, part.market, part.catalog_country, part.kind].filter(Boolean).join(" · ") }}</p>
      </div>
      <a v-if="catalogMedia(part.evidence)" :href="catalogMedia(part.evidence)"
        target="_blank" rel="noopener noreferrer">查看目录原页 <Icon name="external" size="sm" /></a>
      <slot name="actions" />
    </div>
    <div v-if="photos.length" class="catalogue-photos">
      <template v-for="(photo, index) in photos" :key="photo.url">
        <button v-if="index === 0 && views.length === 3" class="photo-disclosure" type="button"
          :aria-expanded="viewsOpen" :aria-controls="viewsId" @click="viewsOpen = !viewsOpen">
          <img :src="photo.url" :alt="photo.label" loading="lazy" />
          <span>{{ viewsOpen ? "收起实拍三视图" : "查看实拍三视图" }} <Icon name="chevron" size="sm" /></span>
        </button>
        <a v-else :href="photo.url" target="_blank" rel="noopener noreferrer">
          <img :src="photo.url" :alt="photo.label" loading="lazy" />
          <span>{{ photo.label }}</span>
        </a>
      </template>
    </div>
    <section v-if="photos.length && views.length === 3" v-show="viewsOpen" :id="viewsId" class="photo-views"
      aria-label="实拍三视图">
      <div class="photo-views-heading">
        <h3>实拍三视图</h3>
        <a :href="photos[0]!.url" target="_blank" rel="noopener noreferrer">打开主图原图</a>
      </div>
      <div class="catalogue-photos">
        <a v-for="photo in views" :key="photo.url" :href="photo.url" target="_blank" rel="noopener noreferrer">
          <img v-if="viewsOpen" :src="photo.url" :alt="photo.label" loading="lazy" />
          <span>{{ photo.label.replace("实拍三视图 · ", "") }}</span>
        </a>
      </div>
    </section>
    <section v-if="fields.length">
      <h3>详细规格</h3>
      <dl class="specifications">
        <div v-for="field in fields" :key="field.key">
          <dt>{{ field.label }}</dt><dd>{{ field.value }}</dd>
        </div>
      </dl>
    </section>
    <section v-if="part.source || part.sources.length" class="catalogue-sources">
      <h3>资料出处</h3>
      <p v-if="part.source">{{ part.source }}</p>
      <div v-for="source in part.sources" :key="source.crop" class="catalogue-source">
        <span>{{ source.label }}</span>
        <a v-if="catalogMedia(source.crop)" :href="catalogMedia(source.crop)"
          target="_blank" rel="noopener noreferrer">规格原图</a>
        <a v-if="catalogMedia(source.page)" :href="catalogMedia(source.page)"
          target="_blank" rel="noopener noreferrer">整页</a>
      </div>
    </section>
  </article>
</template>

<style scoped>
.product-detail { min-width: 0; padding: var(--space-20); display: grid; gap: var(--space-16); }
.detail-top { display: flex; justify-content: space-between; align-items: start; gap: var(--space-8); flex-wrap: wrap; }
.detail-top h2 { font: var(--type-title-large); overflow-wrap: anywhere; }
.detail-top p { color: var(--ink-secondary); margin-top: var(--space-4); }
.catalogue-photos { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: var(--space-8); }
.catalogue-photos a, .photo-disclosure { text-decoration: none; display: grid; align-content: start; gap: var(--space-4); }
.catalogue-photos img { display: block; width: 100%; height: 140px; object-fit: contain; border: 1px solid var(--line); border-radius: var(--radius-control); }
.catalogue-photos span { font: var(--type-caption); }
.photo-disclosure { text-align: left; color: var(--navy); border-radius: var(--radius-control); }
.photo-disclosure:hover img { border-color: var(--blue); }
.photo-disclosure span { display: flex; align-items: center; gap: var(--space-4); }
.photo-views-heading { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: var(--space-8); margin-bottom: var(--space-8); }
.photo-views .catalogue-photos { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.photo-views img { height: auto; aspect-ratio: 1; }
.specifications { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: var(--space-8) 0 0; gap: 0 var(--space-12); }
.specifications > div { border-top: 1px solid var(--line); padding: var(--space-8) 0; min-width: 0; }
.specifications dt { color: var(--muted); font: var(--type-caption); }
.specifications dd { margin: 0; overflow-wrap: anywhere; }
.catalogue-sources { display: grid; gap: var(--space-4); overflow-wrap: anywhere; }
.catalogue-source { display: flex; gap: var(--space-8); align-items: center; flex-wrap: wrap; }
@media (max-width: 820px) {
  .product-detail { padding: var(--space-12); scroll-margin-top: var(--space-12); }
}
</style>

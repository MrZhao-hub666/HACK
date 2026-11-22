<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { api, catalogTitle, errorMessage } from "../shared";
import type { CatalogCountry, CatalogMarket, ProductCatalog } from "../types";
import Icon from "./Icon.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";
import ProductDetail from "./ProductDetail.vue";

const countries: { code: CatalogCountry; label: string }[] = [
  { code: "E", label: "欧洲" },
  { code: "A", label: "美国" },
  { code: "J", label: "日本" },
  { code: "C", label: "中国" },
  { code: "K", label: "韩国" },
  { code: "N", label: "无国别" },
];
const markets: CatalogMarket[] = ["外贸", "国内"];
const market = ref<CatalogMarket>("外贸");
const country = ref<CatalogCountry | "">("");
const query = ref("");
const catalog = ref<ProductCatalog>();
const loading = ref(true);
const error = ref("");
const page = ref(1);
const selected = ref("");
const detail = ref<HTMLElement | null>(null);
const pageSize = 12;

const normalizeSearch = (text: string) => text.normalize("NFKC").toLowerCase().replace(/\s/g, "");
const filtered = computed(() => {
  const needle = normalizeSearch(query.value);
  return (catalog.value?.items ?? []).filter((part) =>
    part.market === market.value &&
    (market.value === "国内" || !country.value || part.country_code === country.value) &&
    (!needle || [
      part.code, part.name, part.spec_id, part.series, part.brand, part.vehicle,
      ...part.references.flatMap((reference) => [reference.number, reference.scheme + reference.number]),
    ].some((value) => typeof value === "string" && normalizeSearch(value).includes(needle))),
  );
});
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)));
const visible = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize));
const current = computed(() => visible.value.find((part) => part.spec_id === selected.value) ?? visible.value[0]);
watch([market, country, query], () => {
  page.value = 1;
  selected.value = "";
});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    catalog.value = await api<ProductCatalog>("/catalog");
    page.value = Math.min(page.value, pages.value);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function choose(spec: string) {
  selected.value = spec;
  if (matchMedia("(max-width: 820px)").matches) {
    await nextTick();
    detail.value?.scrollIntoView({ block: "start" });
  }
}

defineExpose({ refresh: load });
onMounted(load);
</script>

<template>
  <section class="catalogue" aria-label="产品目录">
    <div class="catalogue-tools">
      <div class="market-switch" aria-label="采购市场">
        <button v-for="item in markets" :key="item" class="ghost" :aria-pressed="market === item"
          @click="market = item">{{ item }}</button>
      </div>
      <label class="catalogue-search">
        <Icon name="search" size="sm" />
        <input v-model="query" type="search" aria-label="搜索产品" placeholder="搜索型号、规格号或旧件编码" />
      </label>
    </div>
    <div v-if="market === '外贸'" class="market-switch country-switch" aria-label="外贸车系">
      <button class="ghost" :aria-pressed="country === ''" @click="country = ''">全部车系</button>
      <button v-for="item in countries" :key="item.code" class="ghost"
        :aria-pressed="country === item.code" @click="country = item.code">{{ item.label }}</button>
    </div>
    <p v-if="error" class="notice" role="alert">
      {{ error }} <button class="textbtn" @click="load">重试</button>
    </p>
    <div v-if="loading && !catalog" class="panel catalog-loading" aria-busy="true">
      <LoadingSkeleton layout="cards" label="正在读取产品目录" />
    </div>
    <template v-else-if="catalog">
      <p v-if="catalog.sync" class="sync-status"><Icon name="refresh" size="sm" />{{ catalog.sync }}</p>
      <div v-if="filtered.length" class="catalogue-grid">
        <section class="panel results" aria-label="产品列表">
          <div class="results-header">
            <h2>目录规格</h2><span>{{ filtered.length }} 条</span>
          </div>
          <button v-for="part in visible" :key="part.spec_id" class="part-row"
            :aria-pressed="current?.spec_id === part.spec_id" @click="choose(part.spec_id)">
            <div>
              <strong>{{ catalogTitle(part) }}</strong>
              <small>{{ [part.spec_id, part.kind, part.catalog_country].filter(Boolean).join(" · ") }}</small>
            </div>
            <Icon name="chevron" size="sm" />
          </button>
          <nav v-if="pages > 1" class="pagination" aria-label="目录分页">
            <button class="ghost" :disabled="page === 1" @click="page--">上一页</button>
            <small>{{ page }} / {{ pages }}</small>
            <button class="ghost" :disabled="page === pages" @click="page++">下一页</button>
          </nav>
        </section>
        <div v-if="current" ref="detail" class="catalogue-detail">
          <ProductDetail :part="current" :labels="catalog.fields" />
        </div>
      </div>
      <div v-else class="panel catalogue-empty">
        <Icon name="package" size="lg" />
        <h2>没有符合条件的规格</h2>
        <button v-if="query" class="textbtn" @click="query = ''">清空搜索</button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.catalogue { display: grid; gap: var(--space-12); }
.catalogue-tools, .market-switch { display: flex; gap: var(--space-8); flex-wrap: wrap; }
.catalogue-tools { align-items: center; justify-content: space-between; }
.market-switch button[aria-pressed="true"] {
  background: var(--orange-pale); color: var(--orange-ink); border-color: var(--orange-pale);
}
.catalogue-search {
  display: flex; align-items: center; width: min(100%, 320px); min-width: 0;
  padding-left: var(--space-12); gap: var(--space-8);
  border: 1px solid var(--line); border-radius: var(--radius-control); background: var(--paper); color: var(--muted);
}
.catalogue-search input { width: 100%; min-width: 0; background: none; border: 0; padding: var(--space-8); color: var(--ink); }
.catalogue-search input::placeholder { color: var(--muted); }
.catalogue-search:focus-within { outline: 2px solid var(--blue); }
.catalogue-search input:focus-visible { outline: 0; }
.catalogue-grid { display: grid; grid-template-columns: minmax(225px, 0.75fr) minmax(0, 1.8fr); align-items: start; gap: var(--space-12); }
.catalogue-detail { min-width: 0; scroll-margin-top: var(--space-12); }
.results { overflow: hidden; }
.results-header, .pagination {
  display: flex; justify-content: space-between; align-items: center; gap: var(--space-8);
  padding: var(--space-12);
}
.results-header span, .sync-status { font: var(--type-caption); color: var(--ink-secondary); }
.sync-status { display: flex; gap: var(--space-8); align-items: center; }
.part-row {
  width: 100%; display: flex; justify-content: space-between; align-items: center; gap: var(--space-8);
  text-align: left; padding: var(--space-8) var(--space-12); border-top: 1px solid var(--line);
}
.part-row:hover { background: var(--surface-hover); }
.part-row[aria-pressed="true"] { background: var(--surface-selected); color: var(--navy); }
.part-row strong, .part-row small { display: block; overflow-wrap: anywhere; }
.pagination { border-top: 1px solid var(--line); }
.pagination .ghost { padding-inline: var(--space-8); }
.catalogue-empty, .catalog-loading { padding: var(--space-20); }
.catalogue-empty { display: grid; place-items: center; gap: var(--space-8); padding-block: var(--space-32); }
@media (max-width: 820px) {
  .catalogue-grid { grid-template-columns: minmax(0, 1fr); }
  .catalogue-search input { font-size: 16px; }
}
</style>

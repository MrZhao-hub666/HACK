<script setup lang="ts">
import { computed, ref } from "vue";
import Icon from "./Icon.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";
import AlternativeCard from "./AlternativeCard.vue";
import { api, errorMessage, stamp } from "../shared";
import type { AlternativeBatch, Company, InquiryDetail } from "../types";

const props = defineProps<{
  inquiry: InquiryDetail;
  source?: Company;
  live: boolean;
  actor: string;
}>();
const emit = defineEmits<{
  changed: [batch: AlternativeBatch];
  link: [];
  company: [id: number];
}>();
const mode = ref<"local" | "live">(props.inquiry.alternatives?.mode || "local");
const busy = ref(false),
  error = ref("");
const incomplete = computed(
  () =>
    !props.source?.country.trim() ||
    ["待识别", "渠道伙伴"].includes(props.source.kind),
);
async function search() {
  if (!props.source || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await api<AlternativeBatch>(
      "/inquiries/" + props.inquiry.id + "/alternatives",
      "POST",
      {
        source_company_id: props.source.id,
        mode: mode.value,
        claim: !props.inquiry.owner,
      },
    );
    emit("changed", result);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <details class="alternative-panel">
    <summary>
      <Icon name="compass" size="md" /><strong>寻找替代买家</strong
      ><span v-if="inquiry.alternatives" class="count">{{
        inquiry.alternatives.items.length
      }}</span
      ><Icon name="chevron" size="sm" />
    </summary>
    <div class="alt-body">
      <div v-if="!source" class="alt-help">
        <p>请先关联客户档案，再按该企业的市场和业务查找同行买家。</p>
        <button class="ghost" @click="emit('link')">去关联企业</button>
      </div>
      <div v-else-if="incomplete" class="alt-help">
        <p>
          请补全
          {{ source.name }} 的国家或地区，以及车队、维修或配件经销等业务类型。
        </p>
        <button class="ghost" @click="emit('company', source.id)">
          完善客户档案
        </button>
      </div>
      <template v-else>
        <h3>{{ source.name }}</h3>
        <p class="meta">
          {{ source.country }} · {{ source.kind }} · 推荐给{{
            inquiry.owner || actor
          }}
        </p>
        <div class="alt-controls">
          <label
            >检索来源<select v-model="mode" :disabled="busy">
              <option value="local">本地公开资料</option>
              <option value="live" :disabled="!live">
                实时网页搜索{{ live ? "" : "（未配置）" }}
              </option>
            </select></label
          >
          <button class="primary" :disabled="busy" @click="search">
            {{
              busy
                ? "正在查找…"
                : !inquiry.owner
                  ? "认领并查找"
                  : inquiry.alternatives
                    ? "重新查找"
                    : "查找并推荐"
            }}
          </button>
        </div>
        <p v-if="mode === 'live'" class="hint">
          外部检索仅使用公开市场和业务类型。搜索摘要需打开原页核实。
        </p>
      </template>
      <div v-if="error" class="notice" role="alert">{{ error }}</div>
      <LoadingSkeleton
        v-if="busy && !inquiry.alternatives"
        layout="rows"
        label="正在查找替代买家"
      />
      <template v-if="inquiry.alternatives">
        <div class="alt-batch">
          <strong>推荐结果</strong
          ><small
            >{{
              inquiry.alternatives.mode === "local"
                ? "本地公开资料"
                : "实时网页搜索"
            }}
            · {{ stamp(inquiry.alternatives.generated_at) }}</small
          >
        </div>
        <p class="meta">检索条件 · {{ inquiry.alternatives.query }}</p>
        <p v-if="!inquiry.alternatives.items.length" class="empty">
          当前没有符合条件的推荐。可以核对企业资料或更换检索来源。
        </p>
        <AlternativeCard
          v-for="r in inquiry.alternatives.items"
          :key="r.id"
          :item="r"
          :actor="actor"
          :live="live"
          @changed="emit('changed', $event)"
          @company="emit('company', $event)"
        />
      </template>
    </div>
  </details>
</template>

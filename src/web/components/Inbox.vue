<script setup lang="ts">
import AlternativePanel from "./AlternativePanel.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";
import { ref, computed, watch } from "vue";
import {
  api,
  errorMessage,
  channels,
  states,
  stamp,
  age,
  toast,
} from "../shared";
import { filters, matchesFilter, channelStyles } from "./workspace";
import Icon from "./Icon.vue";
import type {
  AlternativeBatch,
  InquiryRow,
  InquiryDetail,
  Company,
  Config,
  Filter,
} from "../types";

const props = defineProps<{
  rows: InquiryRow[];
  companies: Company[];
  config: Config;
  actor: string;
  focusId: number;
  initialFilter: Filter;
}>();
const emit = defineEmits<{ reload: []; compose: []; company: [id: number] }>();
const search = ref(""),
  filter = ref(props.initialFilter || "全部"),
  channel = ref(""),
  selected = ref(props.focusId || 0),
  item = ref<InquiryDetail | null>(null),
  note = ref(""),
  tab = ref("消息"),
  mergeId = ref(""),
  showMerge = ref(false),
  busy = ref(false),
  error = ref(""),
  loading = ref(false);
const visible = computed(() =>
  props.rows.filter(
    (r) =>
      (!channel.value ||
        (r.all_channels || r.channel).split(",").includes(channel.value)) &&
      (!search.value ||
        [r.buyer, r.company, r.preview, r.owner, r.id]
          .join(" ")
          .toLowerCase()
          .includes(search.value.toLowerCase())) &&
      matchesFilter(r, filter.value, props.actor),
  ),
);
const companySelect = ref<HTMLSelectElement | null>(null);
function linkCompany() {
  const field = companySelect.value;
  const section = field?.closest("details");
  if (section) section.open = true;
  field?.focus();
}
function alternativesChanged(batch: AlternativeBatch) {
  if (
    item.value?.id === batch.inquiry_id &&
    item.value.company_id === batch.source_company_id
  ) {
    item.value.alternatives = batch;
    if (!item.value.owner) item.value.owner = props.actor;
  }
  emit("reload");
}
const latest = computed(() => item.value?.messages.at(-1)?.features);
let seq = 0;
async function open(id: number, clear = true) {
  const token = ++seq;
  selected.value = id;
  error.value = "";
  if (clear) {
    item.value = null;
    note.value = "";
    tab.value = "消息";
    showMerge.value = false;
    mergeId.value = "";
  }
  if (!id) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const v = await api<InquiryDetail>("/inquiries/" + id);
    if (seq === token) item.value = v;
  } catch (e) {
    if (seq === token) error.value = errorMessage(e);
  } finally {
    if (seq === token) loading.value = false;
  }
}
watch(
  visible,
  (items) => {
    if (!items.some((r) => r.id === selected.value)) open(items[0]?.id || 0);
    else if (selected.value) open(selected.value, false);
  },
  { immediate: true },
);
async function mutate(
  suffix: string,
  method: "POST" | "PATCH",
  body: Record<string, unknown>,
  label: string,
) {
  if (!selected.value || busy.value) return;
  const id = selected.value;
  busy.value = true;
  try {
    const result = await api<InquiryDetail>(
      "/inquiries/" + id + suffix,
      method,
      {
        ...body,
      },
    );
    if (selected.value === id) {
      item.value = result;
      selected.value = result.id;
      showMerge.value = false;
      note.value = "";
    }
    toast(label);
    emit("reload");
  } catch (e) {
    toast(errorMessage(e));
    await open(selected.value, false);
  } finally {
    busy.value = false;
  }
}
function edit(
  key: "owner" | "state" | "company_id" | "intent" | "next_action",
  val: string | number | null,
) {
  mutate("", "PATCH", { [key]: val }, "已保存处理记录");
}
function record(type: "notes" | "reply") {
  if (!item.value) return;
  if (!note.value.trim()) return toast("请先填写回复内容或跟进备注");
  mutate(
    "/" + type,
    "POST",
    type === "reply"
      ? {
          text: note.value,
          through_message_id: Math.max(...item.value.messages.map((m) => m.id)),
        }
      : { text: note.value },
    type === "reply" ? "已登记人工回复" : "已保存备注",
  );
}
</script>

<template>
  <div class="panel inbox">
    <div class="panelhead">
      <div class="sect">
        <icon name="inbox" class="heading-icon" />
        <h2>询盘队列</h2>
        <span class="count">{{ visible.length }}</span>
      </div>
      <button class="ghost" @click="emit('compose')">
        <icon name="plus" /> 补录消息
      </button>
    </div>
    <div class="toolbar">
      <label class="search">
        <icon name="search" />
        <input
          v-model.trim="search"
          aria-label="搜索询盘"
          placeholder="搜索买家、消息或负责人"
        />
      </label>
      <select v-model="channel" aria-label="筛选来源">
        <option value="">全部渠道</option>
        <option v-for="(v, k) in channels" :value="k">{{ v }}</option>
      </select>
    </div>
    <div class="pills">
      <button
        v-for="f in filters"
        :class="{ on: filter === f }"
        :aria-pressed="filter === f"
        @click="filter = f"
      >
        {{ f }}
      </button>
    </div>
    <div class="split">
      <div class="ticketlist">
        <button
          class="ticket"
          v-for="r in visible"
          :key="r.id"
          :class="{ picked: selected === r.id }"
          :aria-pressed="selected === r.id"
          @click="selected !== r.id && open(r.id)"
        >
          <div class="line">
            <span class="channel"
              ><span
                class="channel-mini"
                :class="channelStyles[r.channel]?.tone"
                ><icon :name="channelStyles[r.channel]?.icon" size="sm" /></span
              >{{ channels[r.channel] }}</span
            >
            <small>#{{ String(r.id).padStart(4, "0") }}</small>
          </div>
          <strong>{{ r.buyer }}</strong>
          <p>{{ r.preview || "附件消息" }}</p>
          <div class="line">
            <span
              class="tag"
              :class="{ amber: r.unanswered && r.state !== '已结束' }"
              >{{
                r.state === "已结束"
                  ? "已结束"
                  : r.unanswered
                    ? "待回复"
                    : "已回复"
              }}</span
            >
            <small>{{ r.owner || "待认领" }} · {{ age(r.last_in) }}</small>
          </div>
        </button>
        <div class="empty" v-if="!visible.length">没有符合条件的询盘</div>
      </div>
      <article class="detail" v-if="item" :key="item.id">
        <div v-if="error" class="notice" role="alert">
          {{ error }}
          <button class="textbtn" @click="open(selected, false)">重试</button>
        </div>
        <div class="line">
          <span class="micro"
            >询盘 #{{ String(item.id).padStart(4, "0") }}</span
          >
          <span class="tag green">{{ item.state }}</span>
        </div>
        <h2>{{ item.buyer }}</h2>
        <div class="meta">首次来信 {{ stamp(item.created) }} · 北京时间</div>
        <div class="analysis-box" v-if="latest">
          <div class="line">
            <b><icon name="spark" size="sm" />最近来信摘要</b
            ><span class="tag blue">{{ latest.engine || "本地规则" }}</span>
          </div>
          <p>{{ latest.intent }} · {{ latest.language }}</p>
          <div
            class="tags"
            v-if="latest.codes.length || latest.quantities.length"
          >
            <span class="tag" v-for="code in latest.codes" :key="code">{{
              code
            }}</span>
            <span class="tag" v-for="q in latest.quantities">{{ q }}</span>
          </div>
        </div>
        <AlternativePanel
          :key="item.id + '-' + item.company_id"
          :inquiry="item"
          :actor="actor"
          :source="companies.find((c) => c.id === item?.company_id)"
          :live="config.live_search"
          @link="linkCompany"
          @company="emit('company', $event)"
          @changed="alternativesChanged"
        />
        <div class="tabs">
          <button
            v-for="t in ['消息', '处理记录']"
            @click="tab = t"
            :class="{ active: tab === t }"
            :aria-pressed="tab === t"
          >
            {{ t }}
            <small>{{
              t === "消息" ? item.messages.length : item.history.length
            }}</small>
          </button>
        </div>
        <div v-if="tab === '消息'" class="timeline">
          <div v-for="m in item.messages" :key="m.id" class="bubble">
            <div class="line">
              <b>{{ channels[m.channel] }}</b>
              <small>{{ stamp(m.at) }}</small>
            </div>
            <p v-if="m.body" class="original">{{ m.body }}</p>
            <p v-if="m.attachment">渠道说明 · {{ m.attachment }}</p>
            <p v-if="m.features.translation" class="translation">
              {{ m.features.translation }}
            </p>
            <div class="tags">
              <span class="tag">{{ m.origin }}</span>
              <span class="tag">{{ m.features.language }}</span>
              <span class="tag" v-if="m.features.role !== '待核实'"
                >{{ m.features.role }} · 自述</span
              >
              <span
                class="tag green"
                v-for="q in [...m.features.codes, ...m.features.quantities]"
                >{{ q }}</span
              >
            </div>
            <details class="message-source">
              <summary>查看来源编号</summary>
              <div>接收账号　{{ m.account }}</div>
              <div>会话编号　{{ m.thread_key }}</div>
              <div>消息编号　{{ m.event_id }}</div>
            </details>
          </div>
        </div>
        <div class="timeline" v-else>
          <div class="hist" v-for="h in item.history">
            <b>{{ h.action }}</b>
            <small>{{ h.actor }} · {{ stamp(h.at) }}</small>
            <p>{{ h.detail }}</p>
          </div>
        </div>
        <details class="assignment" open>
          <summary>分派与跟进</summary>
          <div class="fields compact">
            <label
              >负责人<select
                aria-label="负责人"
                :value="item.owner"
                :disabled="busy"
                @change="
                  edit(
                    'owner',
                    ($event.target as HTMLInputElement | HTMLSelectElement)
                      .value,
                  )
                "
              >
                <option value="">待认领</option>
                <option
                  v-if="item.owner && !config.team.includes(item.owner)"
                  :value="item.owner"
                  disabled
                >
                  {{ item.owner }}（历史负责人）
                </option>
                <option v-for="x in config.team" :key="x">{{ x }}</option>
              </select>
            </label>
            <label
              >处理状态<select
                aria-label="处理状态"
                :value="item.state"
                :disabled="busy"
                @change="
                  edit(
                    'state',
                    ($event.target as HTMLInputElement | HTMLSelectElement)
                      .value,
                  )
                "
              >
                <option v-for="x in states">{{ x }}</option>
              </select>
            </label>
          </div>
          <div class="fields compact">
            <label
              >关联企业<select
                ref="companySelect"
                aria-label="关联企业"
                :value="item.company_id || ''"
                :disabled="busy"
                @change="
                  edit(
                    'company_id',
                    Number(
                      ($event.target as HTMLInputElement | HTMLSelectElement)
                        .value,
                    ) || null,
                  )
                "
              >
                <option value="">尚未核实</option>
                <option v-for="c in companies" :value="c.id">
                  {{ c.name }}
                </option>
              </select>
            </label>
            <label
              >采购意图<select
                aria-label="采购意图"
                :value="item.intent"
                :disabled="busy"
                @change="
                  edit(
                    'intent',
                    ($event.target as HTMLInputElement | HTMLSelectElement)
                      .value,
                  )
                "
              >
                <option v-for="x in config.intents">{{ x }}</option>
              </select>
            </label>
          </div>
          <label class="inputlabel"
            >下一步<input
              :value="item.next_action"
              maxlength="500"
              :disabled="busy"
              @change="
                edit(
                  'next_action',
                  ($event.target as HTMLInputElement | HTMLSelectElement).value,
                )
              "
            />
          </label>
        </details>
        <label class="inputlabel"
          >跟进记录<textarea
            v-model="note"
            rows="2"
            placeholder="填写备注，或已在原渠道发给客户的回复"
          ></textarea>
        </label>
        <div class="actions">
          <button class="ghost" :disabled="busy" @click="record('notes')">
            保存备注
          </button>
          <button class="primary" :disabled="busy" @click="record('reply')">
            <icon name="check" />登记已回复
          </button>
        </div>
        <button class="textbtn" @click="showMerge = !showMerge">
          关联到已有询盘
        </button>
        <div class="merge" v-if="showMerge">
          <p>核对买家后将本单消息合入目标询盘，后续消息将跟随目标单。</p>
          <select v-model="mergeId">
            <option value="">选择目标询盘</option>
            <option
              v-for="r in rows.filter((x) => x.id !== selected)"
              :value="r.id"
            >
              #{{ r.id }} {{ r.buyer }}
            </option>
          </select>
          <button
            class="ghost"
            :disabled="!mergeId || busy"
            @click="
              mutate(
                '/merge',
                'POST',
                { target_id: Number(mergeId) },
                '会话已合并',
              )
            "
          >
            确认关联
          </button>
        </div>
      </article>
      <LoadingSkeleton
        v-else-if="loading"
        layout="detail"
        label="正在加载询盘详情"
      />
      <div v-else class="empty" :role="error ? 'alert' : undefined">
        {{ error || "选择询盘查看消息"
        }}<button v-if="error" class="ghost" @click="open(selected, false)">
          重试
        </button>
      </div>
    </div>
  </div>
</template>

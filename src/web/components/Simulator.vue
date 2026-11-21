<script setup lang="ts">
import { ref } from "vue";
import { api, errorMessage, channels, toast, stamp } from "../shared";
function newId() {
  return (
    globalThis.crypto?.randomUUID?.() ||
    Date.now().toString(36) + "-" + Math.random().toString(36).slice(2)
  );
}
function localNow() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
import Icon from "./Icon.vue";
import type { Receipt, Config } from "../types";

const props = defineProps<{ manual: boolean; config: Config }>();
const emit = defineEmits<{ reload: []; open: [id: number] }>();
const receiverHints: Record<string, string> = {
  meta: "公共主页私信、评论和获授权的线索表单。",
  wechat: "客户进入指定微信客服账号后发来的咨询。",
  whatsapp: "客户发给已注册商业号码的消息。",
  instagram: "客户发给专业账号的私信。",
  x: "公开提及、帖子回复和传统私信。加密聊天仅提示来信，正文请在 X 查看。",
  tiktok: "需获批企业消息权限。仅含接收方和时间的欧区通知需在原渠道核实。",
  telegram: "客户与指定机器人的一对一聊天。",
  line: "客户发给 LINE 官方账号的一对一消息。",
};
const form = ref({
    channel: "messenger",
    sender: "",
    body: "",
    attachment: "",
    event_id: newId(),
    thread_key: newId(),
  }),
  localTime = ref(localNow()),
  receipt = ref<Receipt | null>(null),
  busy = ref(false);
function newEvent() {
  form.value.event_id = newId();
  localTime.value = localNow();
  receipt.value = null;
}
function fresh() {
  form.value.thread_key = newId();
  form.value.sender = "";
  form.value.body = "";
  form.value.attachment = "";
  newEvent();
}
function example() {
  fresh();
  form.value.sender = "Nadia · Demo Workshop";
  form.value.body = "Can you quote 100 sets of WVA 29289 for our workshop?";
}
async function submit() {
  if (!form.value.body.trim() && !form.value.attachment.trim())
    return toast("请填写消息或附件说明");
  busy.value = true;
  try {
    receipt.value = await api<Receipt>(
      props.manual ? "/inquiries/manual" : "/demo/inquiries",
      "POST",
      {
        ...form.value,
        occurred_at: new Date(localTime.value).toISOString(),
      },
    );
    emit("reload");
    toast(receipt.value.duplicate ? "已识别重复消息" : "消息已进入收件箱");
  } catch (e) {
    toast(errorMessage(e));
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="panel">
    <div class="panelhead">
      <div class="sect">
        <icon name="radio" />
        <h2>{{ manual ? "补录渠道消息" : "渠道事件模拟" }}</h2>
      </div>
      <span class="tag amber">{{ manual ? "销售录入" : "模拟数据" }}</span>
    </div>
    <div
      class="notice inline-notice"
      role="status"
      v-if="!manual && !config.demo"
    >
      此部署已关闭模拟入口，可通过消息补录登记来信。
    </div>
    <form class="formpad" @submit.prevent="submit">
      <div class="line">
        <h3>消息内容</h3>
        <button v-if="!manual" type="button" class="textbtn" @click="example">
          填入询价样例
        </button>
      </div>
      <div class="fields">
        <label
          >消息来源<select v-model="form.channel">
            <option v-for="(v, k) in channels" :value="k">{{ v }}</option>
          </select>
        </label>
        <label
          >买家 / 显示名称<input
            required
            v-model.trim="form.sender"
            maxlength="160"
            placeholder="如 Nadia · 维修厂"
          />
        </label>
      </div>
      <label class="inputlabel"
        >原始消息<textarea
          v-model="form.body"
          rows="4"
          maxlength="8000"
          placeholder="Can you quote 100 sets of WVA 29289?"
        ></textarea>
      </label>
      <label class="inputlabel"
        >附件说明（可选）<input
          v-model="form.attachment"
          placeholder="如：旧件背面照片，在原渠道查看"
        />
      </label>
      <div class="fields">
        <label
          >会话编号<input
            required
            v-model.trim="form.thread_key"
            maxlength="240"
          />
        </label>
        <label
          >事件编号<input
            required
            v-model.trim="form.event_id"
            maxlength="220"
          />
        </label>
        <label
          >接收时间（本机时区）<input
            type="datetime-local"
            required
            v-model="localTime"
          />
        </label>
      </div>
      <p class="hint">
        同一渠道账号下，重复的事件编号只入库一次。同一会话的新消息会追加到原询盘。
      </p>
      <div class="actions">
        <button type="button" class="ghost" @click="fresh">新的会话</button>
        <button type="button" class="ghost" @click="newEvent">
          同会话新消息
        </button>
        <button class="primary" :disabled="busy || (!manual && !config.demo)">
          {{ busy ? "处理中…" : manual ? "保存补录" : "发送模拟事件"
          }}<icon name="arrow" />
        </button>
      </div>
    </form>
  </div>
  <div class="panel formpad" v-if="receipt">
    <div class="line">
      <div>
        <small class="micro">接收结果</small>
        <h3>
          {{ receipt.duplicate ? "重复事件已忽略" : "消息已入库" }} · #{{
            receipt.inquiry_id
          }}
        </h3>
      </div>
      <button class="primary" @click="emit('open', receipt.inquiry_id)">
        打开询盘
      </button>
    </div>
  </div>

  <div v-if="!manual" class="panel">
    <div class="panelhead"><h2>渠道接入状态</h2></div>
    <div class="cards">
      <article class="companycard" v-for="r in config.receivers" :key="r.id">
        <div class="line">
          <strong>{{ r.name }}</strong
          ><span class="tag">{{
            !r.configured
              ? "未配置"
              : r.sync?.error
                ? "接收异常"
                : r.sync?.last_success
                  ? "已接收回调"
                  : "等待回调"
          }}</span>
        </div>
        <p>{{ receiverHints[r.id] }}</p>
        <small>{{
          r.sync?.error || "最近成功接收：" + stamp(r.sync?.last_success)
        }}</small>
      </article>
    </div>
  </div>
</template>

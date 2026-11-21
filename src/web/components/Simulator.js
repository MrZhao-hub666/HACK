import { ref } from "../vendor/vue.esm-browser.prod.js";
import { api, channels, toast, stamp } from "../shared.js";
import template from "./simulator-template.js";
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
export default {
  props: ["manual", "config"],
  emits: ["reload", "open"],
  template,
  setup(p, { emit }) {
    const form = ref({
        channel: "messenger",
        sender: "",
        body: "",
        attachment: "",
        event_id: newId(),
        thread_key: newId(),
      }),
      localTime = ref(localNow()),
      receipt = ref(null),
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
        receipt.value = await api(
          p.manual ? "/inquiries/manual" : "/demo/inquiries",
          "POST",
          {
            ...form.value,
            occurred_at: new Date(localTime.value).toISOString(),
          },
        );
        emit("reload");
        toast(receipt.value.duplicate ? "已识别重复消息" : "消息已进入收件箱");
      } catch (e) {
        toast(e.message);
      } finally {
        busy.value = false;
      }
    }
    return {
      stamp,
      form,
      localTime,
      receipt,
      busy,
      channels,
      example,
      newEvent,
      fresh,
      submit,
    };
  },
};

import { ref, computed, watch } from "../vendor/vue.esm-browser.prod.js";
import template from "./inbox-template.js";
import {
  api,
  channels,
  states,
  stamp,
  age,
  overnight,
  relevant,
  toast,
} from "../shared.js";
export default {
  props: ["rows", "companies", "config", "actor", "focusId"],
  emits: ["reload", "compose", "focused"],
  setup(p, { emit }) {
    const search = ref(""),
      filter = ref("全部"),
      channel = ref(""),
      selected = ref(0),
      item = ref(null),
      note = ref(""),
      tab = ref("消息"),
      mergeId = ref(""),
      showMerge = ref(false),
      busy = ref(false),
      error = ref(""),
      loading = ref(false);
    const filters = ["全部", "未回复", "夜间待回", "待认领", "我的", "已结束"];
    const visible = computed(() =>
      p.rows.filter(
        (r) =>
          (!channel.value ||
            (r.all_channels || r.channel).split(",").includes(channel.value)) &&
          (!search.value ||
            [r.buyer, r.company, r.preview, r.owner, r.id]
              .join(" ")
              .toLowerCase()
              .includes(search.value.toLowerCase())) &&
          {
            全部: true,
            未回复: r.unanswered && r.state !== "已结束",
            夜间待回: overnight(r) && relevant(r) && r.state !== "已结束",
            待认领: !r.owner && r.state !== "已结束",
            我的: r.owner === p.actor,
            已结束: r.state === "已结束",
          }[filter.value],
      ),
    );
    let seq = 0;
    async function open(id, clear = true) {
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
        const v = await api("/inquiries/" + id);
        if (seq === token) item.value = v;
      } catch (e) {
        if (seq === token) error.value = e.message;
      } finally {
        if (seq === token) loading.value = false;
      }
    }
    watch(
      () => p.focusId,
      (id) => {
        if (id) {
          filter.value = "全部";
          channel.value = "";
          search.value = "";
          open(id);
          emit("focused");
        }
      },
      { immediate: true },
    );
    watch(
      visible,
      (items) => {
        if (!items.some((r) => r.id === selected.value))
          open(items[0]?.id || 0);
        else if (selected.value) open(selected.value, false);
      },
      { immediate: true },
    );
    async function mutate(suffix, method, body, label) {
      if (!selected.value || busy.value) return;
      const id = selected.value;
      busy.value = true;
      try {
        const result = await api("/inquiries/" + id + suffix, method, {
          ...body,
          actor: p.actor,
        });
        if (selected.value === id) {
          item.value = result;
          selected.value = result.id;
          showMerge.value = false;
          note.value = "";
        }
        toast(label);
        emit("reload");
      } catch (e) {
        toast(e.message);
        await open(selected.value, false);
      } finally {
        busy.value = false;
      }
    }
    function edit(key, val) {
      mutate("", "PATCH", { [key]: val }, "已保存处理记录");
    }
    function record(type) {
      if (!note.value.trim()) return toast("请先填写回复内容或跟进备注");
      mutate(
        "/" + type,
        "POST",
        type === "reply"
          ? {
              text: note.value,
              through_message_id: Math.max(
                ...item.value.messages.map((m) => m.id),
              ),
            }
          : { text: note.value },
        type === "reply" ? "已登记人工回复" : "已保存备注",
      );
    }
    return {
      search,
      filter,
      channel,
      selected,
      item,
      note,
      tab,
      mergeId,
      showMerge,
      busy,
      error,
      loading,
      filters,
      visible,
      open,
      edit,
      record,
      mutate,
      channels,
      states,
      stamp,
      age,
    };
  },
  template,
};

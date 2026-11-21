import { ref, onMounted } from "../vendor/vue.esm-browser.prod.js";
import { api, kinds, toast, safeLink } from "../shared.js";
import template from "./discovery-template.js";
export default {
  props: ["companies", "config"],
  emits: ["reload"],
  template,
  setup(p, { emit }) {
    const form = ref({
        market: "马来西亚",
        kind: "待识别",
        keywords: "",
        mode: "samples",
      }),
      result = ref(null),
      error = ref(""),
      busy = ref(false);
    async function run() {
      busy.value = true;
      error.value = "";
      result.value = null;
      try {
        result.value = await api("/discovery/search", "POST", form.value);
      } catch (e) {
        error.value = e.message;
      } finally {
        busy.value = false;
      }
    }
    function saved(c) {
      return p.companies.some(
        (x) => x.name === c.name && x.country === c.country,
      );
    }
    async function adopt(c) {
      busy.value = true;
      try {
        await api("/companies", "POST", c);
        emit("reload");
        toast("已加入客户档案");
      } catch (e) {
        toast(e.message);
      } finally {
        busy.value = false;
      }
    }
    onMounted(run);
    return { form, result, error, busy, kinds, run, adopt, saved, safeLink };
  },
};

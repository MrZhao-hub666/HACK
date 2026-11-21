import { ref, computed } from "../vendor/vue.esm-browser.prod.js";
import {
  api,
  kinds,
  purchases,
  blankCompany,
  toast,
  safeLink,
} from "../shared.js";
import template from "./company-template.js";
export default {
  props: ["companies"],
  emits: ["reload"],
  template,
  setup(p, { emit }) {
    const q = ref(""),
      role = ref(""),
      id = ref(0),
      editing = ref(false),
      form = ref(blankCompany()),
      busy = ref(false);
    const filtered = computed(() =>
      p.companies.filter(
        (c) =>
          (!role.value || c.procurement === role.value) &&
          [c.name, c.country, c.kind]
            .join(" ")
            .toLowerCase()
            .includes(q.value.toLowerCase()),
      ),
    );
    function start(c) {
      id.value = c?.id || 0;
      form.value = blankCompany();
      if (c)
        for (const key of Object.keys(form.value)) form.value[key] = c[key];
      editing.value = true;
    }
    async function save() {
      busy.value = true;
      try {
        await api(
          id.value ? "/companies/" + id.value : "/companies",
          id.value ? "PUT" : "POST",
          form.value,
        );
        editing.value = false;
        emit("reload");
        toast("客户档案已保存");
      } catch (e) {
        toast(e.message);
      } finally {
        busy.value = false;
      }
    }
    return {
      q,
      role,
      id,
      editing,
      form,
      busy,
      filtered,
      start,
      save,
      kinds,
      purchases,
      safeLink,
    };
  },
};

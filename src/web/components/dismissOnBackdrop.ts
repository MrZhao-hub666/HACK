import type { ObjectDirective } from "vue";

export const vDismissOnBackdrop: ObjectDirective<HTMLDialogElement> = {
  mounted(dialog) {
    dialog.setAttribute("closedby", "any");
    if (Reflect.has(dialog, "closedBy")) return;

    function onBackdrop(event: MouseEvent) {
      if (event.target !== dialog) return false;
      const { left, right, top, bottom } = dialog.getBoundingClientRect();
      const { clientX: x, clientY: y } = event;
      return x < left || x >= right || y < top || y >= bottom;
    }

    let pressedBackdrop = false;
    dialog.addEventListener("pointerdown", (event) => {
      pressedBackdrop = event.isPrimary && event.button === 0 && onBackdrop(event);
    });
    dialog.addEventListener("click", (event) => {
      if (pressedBackdrop && event.detail > 0 && onBackdrop(event)) dialog.close();
      pressedBackdrop = false;
    });
  },
};

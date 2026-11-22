<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, h, type VNode } from "vue";
import { safeLink } from "../shared";

const props = defineProps<{ text: string; sourceUrl: string }>();
const markdown = new MarkdownIt({ html: false, breaks: true });
type Token = ReturnType<typeof markdown.parse>[number];
type Child = VNode | string;

function sourceLink(href: string | number | null) {
  if (typeof href !== "string" || !href) return;
  const base = safeLink(props.sourceUrl);
  if (base && URL.canParse(href, base)) return safeLink(new URL(href, base).href);
  return safeLink(href);
}

function element(token: Token, children: Child[]) {
  switch (token.tag) {
    case "a": {
      const href = sourceLink(token.attrGet("href"));
      return href
        ? h("a", { href, target: "_blank", rel: "noopener noreferrer" }, children)
        : h("span", children);
    }
    case "h1":
    case "h2":
      return h("h3", children);
    case "ol":
      return h("ol", { start: token.attrGet("start") }, children);
    case "p":
    case "h3":
    case "h4":
    case "h5":
    case "h6":
    case "strong":
    case "em":
    case "s":
    case "blockquote":
    case "ul":
    case "li":
    case "table":
    case "thead":
    case "tbody":
    case "tr":
    case "th":
    case "td":
      return h(token.tag, children);
    default:
      return h("span", children);
  }
}

function renderTokens(tokens: Token[]): Child[] {
  const root: Child[] = [];
  const stack: { token: Token; children: Child[] }[] = [];
  for (let index = 0; index < tokens.length; index++) {
    const token = tokens[index];
    if (token.nesting === -1) {
      const section = stack.pop();
      if (section) {
        const parent = stack.at(-1)?.children ?? root;
        if (section.token.hidden) parent.push(...section.children);
        else parent.push(element(section.token, section.children));
      }
      continue;
    }
    const children = stack.at(-1)?.children ?? root;
    if (token.type === "paragraph_open") {
      // Some search excerpts contain single-column table rows without a header or divider.
      const rows: string[] = [];
      let end = index;
      while (tokens[end]?.type === "paragraph_open" && tokens[end + 2]?.type === "paragraph_close") {
        const row = /^\|([^|\n]+)\|$/.exec(tokens[end + 1].content.trim());
        if (!row) break;
        rows.push(row[1].trim());
        end += 3;
      }
      if (rows.length > 1) {
        children.push(h("table", [h("tbody", rows.map((row) =>
          h("tr", [h("td", renderTokens(markdown.parseInline(row, {})))])
        ))]));
        index = end - 1;
        continue;
      }
    }
    if (token.nesting === 1) {
      stack.push({ token, children: [] });
      continue;
    }
    switch (token.type) {
      case "inline":
        children.push(...renderTokens(token.children ?? []));
        break;
      case "text":
      case "image":
        children.push(token.content);
        break;
      case "code_inline":
        children.push(h("code", token.content));
        break;
      case "code_block":
      case "fence":
        children.push(h("pre", [h("code", token.content)]));
        break;
      case "hardbreak":
      case "softbreak":
        children.push(h("br"));
        break;
      case "hr":
        children.push(h("hr"));
        break;
    }
  }
  return root;
}

const nodes = computed(() => renderTokens(markdown.parse(props.text, {})));
const Content = () => nodes.value;
</script>

<template>
  <div v-if="text" class="source-markdown"><Content /></div>
</template>

<style scoped>
.source-markdown {
  border-left: 2px solid var(--divider);
  padding-left: var(--space-12);
  margin: var(--space-12) 0;
}
.source-markdown :deep(:is(h3, h4, h5, h6)) {
  color: var(--ink);
  font: var(--type-label-medium);
  font-weight: 700;
  margin: var(--space-16) 0 var(--space-4);
}
.source-markdown :deep(:is(p, ul, ol, pre, blockquote, table, hr)) {
  margin: var(--space-8) 0 var(--space-12);
}
.source-markdown :deep(:is(ul, ol)) { padding-inline-start: 1.4em; }
.source-markdown :deep(blockquote) {
  border-left: 2px solid var(--divider);
  padding-left: var(--space-12);
}
.source-markdown :deep(a) {
  color: var(--blue);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.source-markdown :deep(pre) {
  background: var(--surface-subtle);
  padding: var(--space-8);
  overflow-x: auto;
}
.source-markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
  font: var(--type-caption);
}
.source-markdown :deep(:is(th, td)) {
  border: 1px solid var(--divider);
  padding: var(--space-4) var(--space-8);
  text-align: start;
}
.source-markdown :deep(th) { background: var(--surface-subtle); }
</style>

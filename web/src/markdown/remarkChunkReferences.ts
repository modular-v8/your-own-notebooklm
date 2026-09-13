// Turns a well-formed inline `[chunk-id]` reference in answer prose into a
// link node carrying a private `raglab-chunk:` URL scheme, so Answer.tsx's
// `components.a` override can render it as a citation chip instead of a
// plain anchor. A remark plugin, not a string replace on the raw answer
// text, so it operates on parsed text nodes only -- a fenced code block or
// inline code span is never a `text` node's content, so chunk ids shown
// there are left untouched for free, and a genuine `[text](url)` link is
// already a `link` node before this plugin ever runs, never a `text` node
// containing literal brackets (specs/10-inline-citations/BRIEF.md).
//
// The id pattern mirrors `CHUNK_ID_RE` in src/raglab/evals/citations.py
// (`^[^\s,:]+:\d+$`), with `]` added to the excluded-character class since
// this match additionally has to stop at the closing bracket.
import type { Link, Parent, Root, Text } from "mdast";
import { visit } from "unist-util-visit";

export const CHUNK_REF_URL_SCHEME = "raglab-chunk:";

const INLINE_CHUNK_REF_RE = /\[([^\s\],:]+:\d+)\]/g;

export function remarkChunkReferences() {
  return (tree: Root) => {
    visit(tree, "text", (node: Text, index, parent: Parent | undefined) => {
      if (parent === undefined || index === undefined) return;

      INLINE_CHUNK_REF_RE.lastIndex = 0;
      if (!INLINE_CHUNK_REF_RE.test(node.value)) return;
      INLINE_CHUNK_REF_RE.lastIndex = 0;

      const replacement: (Text | Link)[] = [];
      let lastEnd = 0;
      let match: RegExpExecArray | null;

      while ((match = INLINE_CHUNK_REF_RE.exec(node.value)) !== null) {
        const [full, chunkId] = match;
        if (match.index > lastEnd) {
          replacement.push({ type: "text", value: node.value.slice(lastEnd, match.index) });
        }
        replacement.push({
          type: "link",
          url: `${CHUNK_REF_URL_SCHEME}${chunkId}`,
          children: [{ type: "text", value: full }],
        });
        lastEnd = match.index + full.length;
      }
      if (lastEnd < node.value.length) {
        replacement.push({ type: "text", value: node.value.slice(lastEnd) });
      }

      parent.children.splice(index, 1, ...replacement);
      // Skip past the nodes just inserted -- they're already resolved, and
      // re-visiting them would re-run the match against plain text nodes
      // that can no longer contain a bracketed reference.
      return index + replacement.length;
    });
  };
}

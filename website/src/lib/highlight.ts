/* ============================================================================
   Minimal, build-time syntax highlighter.

   Runs in Astro frontmatter (server) only — emits <span class="tk-*"> whose
   colors come from --code-* tokens, so code stays on-palette AND adapts to
   light mode (unlike inline-hex highlighters). Zero client JS.

   Scope is deliberately small: the exact JSON / YAML / bash snippets this site
   shows. Everything is HTML-escaped as it is tokenized (escape-per-token), so
   no raw input is ever emitted unescaped.
   ========================================================================== */

type Lang = 'json' | 'yaml' | 'bash';

const esc = (s: string): string =>
  s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

const wrap = (cls: string, s: string): string => `<span class="${cls}">${esc(s)}</span>`;

// [pattern, class] — first match wins; unmatched text is escaped as-is.
const RULES: Record<Lang, Array<[RegExp, string]>> = {
  json: [
    [/"(?:[^"\\]|\\.)*"(?=\s*:)/y, 'tk-key'],
    [/"(?:[^"\\]|\\.)*"/y, 'tk-str'],
    [/\b-?\d+(?:\.\d+)?\b/y, 'tk-num'],
    [/\b(?:true|false|null)\b/y, 'tk-num'],
    [/[{}[\]:,]/y, 'tk-punc'],
  ],
  yaml: [
    [/#[^\n]*/y, 'tk-comment'],
    [/^[ \t]*-?[ \t]*[\w.$-]+(?=:)/y, 'tk-key'],
    [/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/y, 'tk-str'],
    [/\b-?\d+(?:\.\d+)?\b/y, 'tk-num'],
    [/[:[\]{}|>-]/y, 'tk-punc'],
  ],
  bash: [
    [/#[^\n]*/y, 'tk-comment'],
    [/(?:^|\s)(?:pip|agentguard|echo|python|npm|npx)\b/y, 'tk-key'],
    [/--?[\w-]+/y, 'tk-num'],
    [/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/y, 'tk-str'],
  ],
};

export function highlight(code: string, lang: Lang): string {
  const rules = RULES[lang];
  let out = '';
  let i = 0;
  const n = code.length;
  while (i < n) {
    let matched = false;
    for (const [re, cls] of rules) {
      re.lastIndex = i;
      const m = re.exec(code);
      if (m && m.index === i && m[0].length > 0) {
        // Preserve any leading whitespace the bash command rule captured.
        const lead = m[0].match(/^\s+/)?.[0] ?? '';
        out += esc(lead) + wrap(cls, m[0].slice(lead.length));
        i += m[0].length;
        matched = true;
        break;
      }
    }
    if (!matched) {
      out += esc(code[i]);
      i += 1;
    }
  }
  return out;
}

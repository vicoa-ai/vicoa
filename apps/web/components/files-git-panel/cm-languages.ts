import type { Extension } from '@codemirror/state';
import { StreamLanguage } from '@codemirror/language';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';
import { json } from '@codemirror/lang-json';
import { markdown } from '@codemirror/lang-markdown';
import { html } from '@codemirror/lang-html';
import { css } from '@codemirror/lang-css';
import { yaml } from '@codemirror/lang-yaml';
import { rust } from '@codemirror/lang-rust';
import { go } from '@codemirror/lang-go';
import { sql } from '@codemirror/lang-sql';
import { cpp } from '@codemirror/lang-cpp';
import { java } from '@codemirror/lang-java';
import { php } from '@codemirror/lang-php';
import { xml } from '@codemirror/lang-xml';
// Grammars without a first-class package come from the CM5 legacy modes,
// wrapped for CM6 via StreamLanguage — this is what covers toml, shell,
// Dockerfile, ini, ruby, kotlin, and the rest.
import { toml } from '@codemirror/legacy-modes/mode/toml';
import { shell } from '@codemirror/legacy-modes/mode/shell';
import { dockerFile } from '@codemirror/legacy-modes/mode/dockerfile';
import { properties } from '@codemirror/legacy-modes/mode/properties';
import { ruby } from '@codemirror/legacy-modes/mode/ruby';
import { lua } from '@codemirror/legacy-modes/mode/lua';
import { perl } from '@codemirror/legacy-modes/mode/perl';
import { r } from '@codemirror/legacy-modes/mode/r';
import { clojure } from '@codemirror/legacy-modes/mode/clojure';
import { haskell } from '@codemirror/legacy-modes/mode/haskell';
import { swift } from '@codemirror/legacy-modes/mode/swift';
import { csharp, kotlin, scala, dart, objectiveC } from '@codemirror/legacy-modes/mode/clike';

function basename(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1);
}

function extOf(path: string): string {
  const base = basename(path);
  const i = base.lastIndexOf('.');
  if (i <= 0 || i === base.length - 1) return '';
  return base.slice(i + 1).toLowerCase();
}

/**
 * The CodeMirror language extension for a file, resolved from its name/extension.
 * Returns `null` only for genuinely unknown types — the file stays fully
 * editable, just without syntax highlighting. Keep the extension set broad;
 * users edit config files (toml/ini/env), shell scripts, and many languages.
 */
export function languageExtensionForPath(path: string): Extension | null {
  const name = basename(path);
  if (name === 'Dockerfile' || name.toLowerCase() === 'dockerfile') {
    return StreamLanguage.define(dockerFile);
  }

  switch (extOf(path)) {
    // First-class grammars.
    case 'ts':
      return javascript({ typescript: true });
    case 'tsx':
      return javascript({ typescript: true, jsx: true });
    case 'jsx':
      return javascript({ jsx: true });
    case 'js':
    case 'mjs':
    case 'cjs':
      return javascript();
    case 'py':
      return python();
    case 'rs':
      return rust();
    case 'go':
      return go();
    case 'java':
      return java();
    case 'c':
    case 'h':
    case 'cc':
    case 'cpp':
    case 'hpp':
      return cpp();
    case 'php':
      return php();
    case 'json':
    case 'jsonc':
      return json();
    case 'yaml':
    case 'yml':
      return yaml();
    case 'xml':
    case 'svg':
      return xml();
    case 'html':
    case 'htm':
      return html();
    case 'css':
    case 'scss':
    case 'sass':
      return css();
    case 'sql':
      return sql();
    case 'md':
    case 'mdx':
    case 'markdown':
      return markdown();

    // Legacy (StreamLanguage) grammars.
    case 'toml':
      return StreamLanguage.define(toml);
    case 'sh':
    case 'bash':
    case 'zsh':
      return StreamLanguage.define(shell);
    case 'ini':
    case 'cfg':
    case 'conf':
    case 'env':
    case 'properties':
      return StreamLanguage.define(properties);
    case 'rb':
      return StreamLanguage.define(ruby);
    case 'lua':
      return StreamLanguage.define(lua);
    case 'pl':
    case 'pm':
      return StreamLanguage.define(perl);
    case 'r':
      return StreamLanguage.define(r);
    case 'clj':
    case 'cljs':
    case 'cljc':
    case 'edn':
      return StreamLanguage.define(clojure);
    case 'hs':
      return StreamLanguage.define(haskell);
    case 'swift':
      return StreamLanguage.define(swift);
    case 'cs':
      return StreamLanguage.define(csharp);
    case 'kt':
    case 'kts':
      return StreamLanguage.define(kotlin);
    case 'scala':
    case 'sc':
      return StreamLanguage.define(scala);
    case 'dart':
      return StreamLanguage.define(dart);
    case 'm':
    case 'mm':
      return StreamLanguage.define(objectiveC);
    default:
      return null;
  }
}

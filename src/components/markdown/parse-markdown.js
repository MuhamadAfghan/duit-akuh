// ----------------------------------------------------------------------

/**
 * A small Markdown reader, for the one place the app receives Markdown:
 * the model's own replies.
 *
 * Nothing asks `qwen3.5-9b` to write Markdown and nothing can stop it —
 * it emits `**tebal**`, `- daftar` and `1.` numbering the way every
 * instruction-tuned model does. Until now the thread printed those
 * characters literally, so a tidy three-point answer arrived as a wall
 * of asterisks.
 *
 * It is hand-written rather than `react-markdown` on purpose. That
 * library and its unified/micromark tree are ~45 KB gzipped on a shell
 * budgeted at LCP <= 2.5s over 4G (PRD section 12), to read a subset a
 * chat bubble can even show. The same reasoning as the breakdown chart:
 * five labelled bars are five divs.
 *
 * Two properties matter more than completeness:
 *
 * * **It must survive half a document.** The text is parsed again on
 *   every streamed token, so an unclosed fence or a `**` with no mate
 *   is the normal case, not an error. Unterminated markers simply stay
 *   as the characters they are and resolve themselves a token later.
 * * **It never produces HTML.** Blocks and spans come out as plain
 *   objects that the renderer turns into React elements, so model
 *   output — which the PRD treats as untrusted data, never instructions
 *   — cannot inject anything. Link targets are filtered here too.
 *
 * Deliberately absent: raw HTML, reference links, setext headings,
 * footnotes, and `_single underscore_` emphasis. That last one is a
 * judgement call — `from_account` and `operation_id` appear in error
 * text far more often than anyone italicises a word in Indonesian.
 */

/** ```lang, or ~~~lang. */
const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([\w+-]*)\s*$/;
const HEADING = /^ {0,3}(#{1,6})\s+(.*)$/;
const RULE = /^ {0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$/;
const QUOTE = /^ {0,3}>[ \t]?(.*)$/;
const BULLET = /^([ \t]*)[-*+][ \t]+(.*)$/;
const ORDERED = /^([ \t]*)(\d{1,9})[.)][ \t]+(.*)$/;
/** The `|---|:--:|` line that turns the row above it into a header. */
const TABLE_RULE = /^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$/;

/** How deep a list may nest before we stop recursing. Prose, not YAML. */
const MAX_DEPTH = 4;

// ----------------------------------------------------------------------

/**
 * Read a document into blocks.
 *
 * Returns an array of `{ type, ... }`: `paragraph`, `heading`, `list`,
 * `quote`, `code`, `table`, `rule`. Inline spans are left as text and
 * read separately by `parseInline`, so a list item and a paragraph
 * share one code path for everything inside them.
 */
export function parseMarkdown(text, depth = 0) {
  const lines = String(text ?? '')
    .replace(/\r\n?/g, '\n')
    .split('\n');

  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(FENCE);

    if (fence) {
      const [, marker, language] = fence;
      const body = [];
      index += 1;

      // End of input closes the block. While a reply is streaming that
      // is every frame until the closing fence actually arrives.
      while (index < lines.length && !lines[index].trimEnd().startsWith(marker[0].repeat(3))) {
        body.push(lines[index]);
        index += 1;
      }

      index += 1;
      blocks.push({ type: 'code', language, value: body.join('\n') });
      continue;
    }

    const heading = line.match(HEADING);

    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2].trim() });
      index += 1;
      continue;
    }

    if (RULE.test(line)) {
      blocks.push({ type: 'rule' });
      index += 1;
      continue;
    }

    if (QUOTE.test(line)) {
      const quoted = [];

      while (index < lines.length && QUOTE.test(lines[index])) {
        quoted.push(lines[index].match(QUOTE)[1]);
        index += 1;
      }

      blocks.push({ type: 'quote', blocks: descend(quoted.join('\n'), depth) });
      continue;
    }

    if (line.includes('|') && index + 1 < lines.length && TABLE_RULE.test(lines[index + 1])) {
      const header = splitRow(line);
      const rows = [];
      index += 2;

      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitRow(lines[index]));
        index += 1;
      }

      blocks.push({ type: 'table', header, rows });
      continue;
    }

    if (BULLET.test(line) || ORDERED.test(line)) {
      const [list, next] = readList(lines, index, depth);
      blocks.push(list);
      index = next;
      continue;
    }

    const paragraph = [];

    while (index < lines.length && lines[index].trim() && !opensBlock(lines, index)) {
      paragraph.push(lines[index].trim());
      index += 1;
    }

    // A line that opens another block while a paragraph is still open
    // ends it; without this guard the loop could not advance.
    if (!paragraph.length) {
      paragraph.push(lines[index].trim());
      index += 1;
    }

    blocks.push({ type: 'paragraph', text: paragraph.join('\n') });
  }

  return blocks;
}

// ----------------------------------------------------------------------

/**
 * One run of list items, and the line the caller should resume at.
 *
 * A run stops at the first item of the other kind, so "1. 2. 3." under
 * three bullets is two lists rather than one with confused markers.
 * Indented lines that are not themselves items belong to the item above
 * — that is how a nested list reaches `parseMarkdown` again.
 */
function readList(lines, start, depth) {
  const ordered = ORDERED.test(lines[start]);
  const pattern = ordered ? ORDERED : BULLET;
  const indent = width(lines[start].match(pattern)[1]);
  const first = ordered ? Number(lines[start].match(ORDERED)[2]) : 1;

  const items = [];
  let index = start;

  while (index < lines.length) {
    const match = lines[index].match(pattern);

    if (!match || width(match[1]) !== indent) {
      break;
    }

    const own = [ordered ? match[3] : match[2]];
    index += 1;

    while (index < lines.length) {
      const line = lines[index];

      if (!line.trim()) {
        // A blank line only continues the item if something indented
        // follows it; otherwise the list is over.
        const after = lines[index + 1];

        if (!after?.trim() || width(leading(after)) <= indent) {
          break;
        }

        own.push('');
        index += 1;
        continue;
      }

      if (width(leading(line)) <= indent) {
        break;
      }

      own.push(line.slice(indent).replace(/^[ \t]{1,4}/, ''));
      index += 1;
    }

    items.push(descend(own.join('\n'), depth));
  }

  return [{ type: 'list', ordered, start: first, items }, index];
}

/**
 * Parse nested content, unless we are already too deep.
 *
 * Every recursion strips at least a marker, so this cannot loop — the
 * cap is about not rendering a list inside a list inside a list in a
 * 430px bubble, which is unreadable long before it is slow.
 */
function descend(text, depth) {
  if (depth >= MAX_DEPTH) {
    return [{ type: 'paragraph', text }];
  }

  return parseMarkdown(text, depth + 1);
}

/** Whether a line would start a block other than the paragraph in hand. */
function opensBlock(lines, index) {
  const line = lines[index];

  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    RULE.test(line) ||
    QUOTE.test(line) ||
    BULLET.test(line) ||
    ORDERED.test(line) ||
    (line.includes('|') && TABLE_RULE.test(lines[index + 1] ?? ''))
  );
}

function splitRow(line) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function leading(line) {
  return line.match(/^[ \t]*/)[0];
}

/** Tabs count as four columns, which is what every editor the model saw did. */
function width(space) {
  return space.replace(/\t/g, '    ').length;
}

// ----------------------------------------------------------------------

/**
 * Spans inside a block: code, emphasis, strikethrough, links, breaks.
 *
 * One regex, tried from the longest marker down, so `***both***` is not
 * read as bold followed by a stray asterisk. Code is first because
 * backticks suppress everything inside them.
 *
 * `*one star*` requires a non-space, non-star first character, which is
 * what keeps "3 * 4 * 5" from turning into emphasis. The CommonMark way
 * to say that uses lookbehind, and lookbehind is a parse error on iOS
 * Safari before 16.4 — a syntax error in a bundle takes the whole app
 * down, not just the chat.
 */
const INLINE =
  /`([^`]+)`|\*\*\*([\s\S]+?)\*\*\*|\*\*([\s\S]+?)\*\*|__([\s\S]+?)__|~~([\s\S]+?)~~|\*([^\s*][^*\n]*?)\*|\[([^\]\n]*)\]\(([^()\s]*)\)|(https?:\/\/[^\s<>)\]]+)/;

/** Returns `{ type, ... }` nodes: text, break, code, strong, em, strike, link. */
export function parseInline(text) {
  const nodes = [];
  let rest = String(text ?? '');

  while (rest) {
    const match = INLINE.exec(rest);

    if (!match) {
      pushText(nodes, rest);
      break;
    }

    if (match.index) {
      pushText(nodes, rest.slice(0, match.index));
    }

    const [, code, both, strong, underscored, strike, emphasis, label, href, bare] = match;

    if (code !== undefined) {
      nodes.push({ type: 'code', value: code });
    } else if (both !== undefined) {
      nodes.push({ type: 'strong', children: [{ type: 'em', children: parseInline(both) }] });
    } else if (strong !== undefined || underscored !== undefined) {
      nodes.push({ type: 'strong', children: parseInline(strong ?? underscored) });
    } else if (strike !== undefined) {
      nodes.push({ type: 'strike', children: parseInline(strike) });
    } else if (emphasis !== undefined) {
      nodes.push({ type: 'em', children: parseInline(emphasis) });
    } else if (href !== undefined) {
      const safe = safeHref(href);

      // A link we will not follow is still text the person should see.
      nodes.push(
        safe
          ? { type: 'link', href: safe, children: parseInline(label || href) }
          : { type: 'text', value: match[0] }
      );
    } else {
      nodes.push({ type: 'link', href: bare, children: [{ type: 'text', value: bare }] });
    }

    rest = rest.slice(match.index + match[0].length);
  }

  return nodes;
}

/**
 * A single newline is a line break here, not a space.
 *
 * CommonMark would fold it, but this is a chat: the bubble has shown
 * typed newlines since the first version, and a model listing three
 * things on three lines means three lines.
 */
function pushText(nodes, value) {
  value.split('\n').forEach((part, index) => {
    if (index) {
      nodes.push({ type: 'break' });
    }

    if (part) {
      nodes.push({ type: 'text', value: part });
    }
  });
}

/**
 * Only schemes a tap may safely follow.
 *
 * The model's output is data (FR06), and `[klik](javascript:...)` is the
 * oldest trick there is. Anything else renders as the literal text the
 * model wrote, which is both safe and honest about what it said.
 */
function safeHref(href) {
  const value = href.trim();

  if (!value) {
    return null;
  }

  if (/^(https?:\/\/|mailto:|tel:)/i.test(value)) {
    return value;
  }

  // A bare domain or an in-app path is fine; anything with a colon
  // before the first slash is a scheme we did not allow.
  return /^[^:]*(\/|$)/.test(value) ? value : null;
}

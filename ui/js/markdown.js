/* PCB Advisor UI - markdown: a small renderer for the general reference documents (shared/reference/*.md, listed in Sources).
   It reads what those files use: headings, paragraphs that are hard-wrapped, bullet and numbered lists (nested by indent,
   a wrapped item continues on the next line), pipe tables, quotes, fenced code, rules, `code`, **bold**, *italic*, links and
   bare http(s) addresses. The page markers `<!-- p.N -->` become a quiet "Page N" line; any other HTML comment is dropped.
   Safe by construction: every character of the source goes through esc() once, the only markup is the fixed tags below, and
   a link needs an http(s) address. Globals: mdToHTML(text), mdFindSection(box, where). */

// 1 `code`, 2 and 3 [text](address), 4 a bare address, 5 **bold**, 6 *italic* (not inside a word, not a multiplication sign)
const MD_INLINE = /`([^`\n]+)`|\[([^\]\n]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>"']+)|\*\*([^*\n]+)\*\*|(?<![\w*])\*([^*\s](?:[^*\n]*[^*\s])?)\*(?![\w*])/g;

function mdLink(href, label) {
  return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}
function mdInline(raw) {
  let out = '', at = 0;
  for (const m of raw.matchAll(MD_INLINE)) {                // matchAll works on a copy: bold may call mdInline again
    out += esc(raw.slice(at, m.index));
    at = m.index + m[0].length;
    if (m[1] !== undefined) out += `<code>${esc(m[1])}</code>`;
    else if (m[2] !== undefined) out += /^https?:\/\//i.test(m[3]) ? mdLink(m[3], esc(m[2])) : esc(m[2]);   // no other scheme becomes a link
    else if (m[4] !== undefined) {
      const url = m[4].replace(/[.,;:!?)\]]+$/, '');          // a full stop after an address is not part of it
      out += mdLink(url, esc(url)) + esc(m[4].slice(url.length));
    } else if (m[5] !== undefined) out += `<strong>${mdInline(m[5])}</strong>`;
    else out += `<em>${esc(m[6])}</em>`;
  }
  return out + esc(raw.slice(at));
}

const MD_ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const MD_RULE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
const MD_HEAD = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const MD_SEP = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;
const MD_PAGE = /^\s*<!--\s*p\.(\d+)\s*-->\s*$/;
const mdIsTable = (lines, i) => /^\s*\|/.test(lines[i]) && i + 1 < lines.length && MD_SEP.test(lines[i + 1]) && lines[i + 1].includes('-');
const mdStarts = (lines, i) => {                           // a line that begins a block of its own, so it ends a paragraph
  const l = lines[i];
  return MD_HEAD.test(l) || MD_RULE.test(l) || MD_ITEM.test(l) || /^\s*>/.test(l) || /^\s*```/.test(l) || /^\s*<!--/.test(l) || mdIsTable(lines, i);
};
const mdCells = row => {
  const cells = row.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '').split(/(?<!\\)\|/);
  return cells.map(c => c.trim().replace(/\\\|/g, '|'));
};
const mdKey = s => String(s).toLowerCase().replace(/[^a-z0-9À-￿]+/g, ' ').trim();      // how a heading is compared with a citation

function mdTable(lines, i) {
  const head = mdCells(lines[i]), align = mdCells(lines[i + 1]).map(c => (c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : ''));
  let j = i + 2;
  const rows = [];
  while (j < lines.length && /^\s*\|/.test(lines[j])) rows.push(mdCells(lines[j++]));
  const cell = (tag, c, k) => `<${tag}${align[k] ? ` class="a-${align[k]}"` : ''}>${mdInline(c || '')}</${tag}>`;
  const html = `<div class="tbl-wrap"><table class="tbl dense md-tbl"><thead><tr>${head.map((c, k) => cell('th', c, k)).join('')}</tr></thead>` +
    `<tbody>${rows.map(r => `<tr>${head.map((_, k) => cell('td', r[k], k)).join('')}</tr>`).join('')}</tbody></table></div>`;
  return {html, next: j};
}

function mdList(lines, i) {
  const items = [];
  let j = i;
  while (j < lines.length) {
    const m = lines[j].match(MD_ITEM);
    if (m) { items.push({indent: m[1].replace(/\t/g, '    ').length, ol: /\d/.test(m[2]), n: parseInt(m[2], 10), text: m[3]}); j++; continue; }
    if (!lines[j].trim()) {                                // a blank line keeps the list going only when another item follows
      let k = j;
      while (k < lines.length && !lines[k].trim()) k++;
      const next = k < lines.length && lines[k].match(MD_ITEM);   // ... and it is a deeper item or one of the same kind
      if (next && next[1].length >= items[0].indent && (next[1].length > items[items.length - 1].indent || /\d/.test(next[2]) === items[items.length - 1].ol)) { j = k; continue; }
      break;
    }
    if (mdStarts(lines, j)) break;
    items[items.length - 1].text += ' ' + lines[j].trim();   // the item's text wraps onto this line
    j++;
  }
  const build = (from, indent) => {                        // the items at `indent` and the deeper ones under them
    const first = items[from], tag = first.ol ? 'ol' : 'ul';
    let html = `<${tag}${first.ol && first.n !== 1 ? ` start="${first.n}"` : ''}>`, k = from;
    while (k < items.length && items[k].indent >= indent && !(k > from && items[k].indent === indent && items[k].ol !== first.ol)) {   // a bullet after a number starts a new list
      let sub = '', next = k + 1;
      if (next < items.length && items[next].indent > indent) {
        const r = build(next, items[next].indent);
        sub = r.html; next = r.next;
      }
      html += `<li>${mdInline(items[k].text)}${sub}</li>`;
      k = next;
    }
    return {html: html + `</${tag}>`, next: k};
  };
  let html = '', k = 0;
  while (k < items.length) { const r = build(k, items[k].indent); html += r.html; k = Math.max(r.next, k + 1); }
  return {html, next: j};
}

function mdToHTML(text) {
  const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  let out = '', para = [], i = 0;
  const flush = () => { if (para.length) out += `<p>${mdInline(para.join(' '))}</p>`; para = []; };
  while (i < lines.length) {
    const l = lines[i];
    let m;
    if (!l.trim()) { flush(); i++; continue; }
    if (/^\s*```/.test(l)) {
      flush();
      const code = [];
      for (i++; i < lines.length && !/^\s*```/.test(lines[i]); i++) code.push(lines[i]);
      out += `<pre class="md-code"><code>${esc(code.join('\n'))}</code></pre>`;
      i++;
      continue;
    }
    if (/^\s*<!--/.test(l)) {
      flush();
      if ((m = l.match(MD_PAGE))) out += `<div class="md-page" data-page="${m[1]}"><span>Page ${m[1]}</span></div>`;
      else while (i < lines.length && !lines[i].includes('-->')) i++;   // another comment: dropped, however many lines it takes
      i++;
      continue;
    }
    if ((m = l.match(MD_HEAD))) {
      flush();
      const level = m[1].length;
      out += `<h${Math.min(level + 2, 6)} class="md-h${level}" data-h="${esc(m[2])}">${mdInline(m[2])}</h${Math.min(level + 2, 6)}>`;
      i++;
      continue;
    }
    if (MD_RULE.test(l)) { flush(); out += '<hr>'; i++; continue; }
    if (/^\s*>/.test(l)) {
      flush();
      const quote = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i++) quote.push(lines[i].replace(/^\s*>\s?/, ''));
      out += `<blockquote>${mdToHTML(quote.join('\n'))}</blockquote>`;
      continue;
    }
    if (mdIsTable(lines, i)) { flush(); const r = mdTable(lines, i); out += r.html; i = r.next; continue; }
    if (MD_ITEM.test(l)) { flush(); const r = mdList(lines, i); out += r.html; i = r.next; continue; }
    para.push(l.trim());
    i++;
  }
  flush();
  return out;
}

/* The heading a citation points at: "§ 19.3.2 Rule Priorities", "§ [17] Calculating ...", "§ Drills, vias and annular ring",
   or a page ("PDF p.187"). Returns the element inside `box` (a rendered document) or null. */
function mdFindSection(box, where) {
  if (!box || !where) return null;
  const heads = [...box.querySelectorAll('[data-h]')];
  const w = String(where).replace(/^\s*(?:§|section)\s*/i, '').trim();
  const num = w.match(/^(\d+(?:\.\d+)+)(?=\s|$)/) || w.match(/^(\[\d+\])/);       // 19.3.2 or [17], at the start
  if (num) {
    const hit = heads.find(h => h.dataset.h === num[1] || h.dataset.h.startsWith(num[1] + ' '));
    if (hit) return hit;
  }
  const key = mdKey(w.replace(/\(.*?\)/g, ''));
  if (key.length >= 3) {
    const hit = heads.find(h => mdKey(h.dataset.h) === key) || heads.find(h => mdKey(h.dataset.h).startsWith(key)) ||
      heads.find(h => mdKey(h.dataset.h).includes(key)) || heads.find(h => mdKey(h.dataset.h).length >= 4 && key.includes(mdKey(h.dataset.h)));
    if (hit) return hit;
  }
  const page = w.match(/\bp(?:age|\.)?\s*(\d+)\b/i);
  return page ? box.querySelector(`.md-page[data-page="${page[1]}"]`) : null;
}

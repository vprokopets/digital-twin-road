/**
 * Offline Markdown, GFM table, Admonition, PrismJS syntax, and KaTeX math renderer
 * with strict HTML/URL sanitization for the built-in Documentation Workbench.
 */
import katex from 'katex'
import 'katex/dist/katex.min.css'
import Prism from './prism'

function renderKatex(expr: string, displayMode: boolean): string {
    const trimmed = expr.trim()
    if (!trimmed) return ''
    try {
        return katex.renderToString(trimmed, {
            displayMode,
            throwOnError: false,
            strict: 'ignore',
            trust: false,
            output: 'htmlAndMathml',
        })
    } catch {
        return `<code class="md-math-fallback">${escapeHtml(trimmed)}</code>`
    }
}

const LANGUAGE_ALIASES: Record<string, string> = {
    py: 'python',
    python: 'python',
    sh: 'bash',
    shell: 'bash',
    bash: 'bash',
    zsh: 'bash',
    json: 'json',
    yml: 'yaml',
    yaml: 'yaml',
    ts: 'typescript',
    typescript: 'typescript',
    js: 'javascript',
    javascript: 'javascript',
    css: 'css',
    html: 'markup',
    xml: 'markup',
    vue: 'markup',
    svg: 'markup',
    toml: 'toml',
}

/** Escape HTML special characters in plain text or attribute values. */
export function escapeHtml(raw: string): string {
    return raw
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
}

function slugifyHeading(text: string): string {
    return text
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '')
        .trim()
        .replace(/\s+/g, '-')
}

function isSafeExternalUrl(href: string): boolean {
    const trimmed = href.trim()
    return /^https?:\/\//i.test(trimmed)
}

function isSafeRelativeDocHref(href: string): boolean {
    const trimmed = href.trim()
    if (!trimmed || trimmed.startsWith('/') || trimmed.startsWith('\\')) return false
    // Reject any URI scheme prefix such as javascript:, data:, vbscript:, file:
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(trimmed)) return false
    const pathOnly = trimmed.split('#')[0]
    return pathOnly.toLowerCase().endsWith('.md') || pathOnly.length > 0
}

function sanitizeImageTag(altRaw: string, srcRaw: string): string {
    const src = srcRaw.trim()
    const alt = escapeHtml(altRaw)
    if (!isSafeExternalUrl(src)) {
        return alt ? `<span class="text-slate-400">[image: ${alt}]</span>` : ''
    }
    return `<img src="${escapeHtml(src)}" alt="${alt}" loading="lazy" class="inline-block max-w-full align-middle my-1 rounded" />`
}

function renderLink(labelHtml: string, hrefRaw: string): string {
    const href = hrefRaw.trim()
    if (isSafeExternalUrl(href)) {
        return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" class="md-link">${labelHtml}</a>`
    }
    if (href.startsWith('#')) {
        return `<a href="${escapeHtml(href)}" class="md-link">${labelHtml}</a>`
    }
    if (isSafeRelativeDocHref(href)) {
        return `<a href="#" data-doc-link="${escapeHtml(href)}" class="md-link">${labelHtml}</a>`
    }
    return labelHtml
}

function renderInline(raw: string): string {
    const placeholders: string[] = []
    const stash = (html: string): string => {
        const idx = placeholders.length
        placeholders.push(html)
        return `\u0000MDPH${idx}\u0000`
    }

    // 1. Protect inline code spans first so inner markdown/math stays literal
    let text = raw.replace(/`([^`\n]+)`/g, (_m, code) => {
        return stash(`<code class="md-inline-code">${escapeHtml(code)}</code>`)
    })

    // 2. Protect linked badge images [![alt](img)](href)
    text = text.replace(/\[!\[([^\]\n]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)/g, (_m, alt, imgSrc, linkHref) => {
        const imgHtml = sanitizeImageTag(alt, imgSrc)
        return stash(renderLink(imgHtml || escapeHtml(alt), linkHref))
    })

    // 3. Protect standalone images ![alt](src)
    text = text.replace(/!\[([^\]\n]*)\]\(([^)\s]+)\)/g, (_m, alt, imgSrc) => {
        return stash(sanitizeImageTag(alt, imgSrc))
    })

    // 4. Protect links [label](href)
    text = text.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (_m, label, href) => {
        const renderedLabel = escapeHtml(label).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        return stash(renderLink(renderedLabel, href))
    })

    // 5. Render and stash inline LaTeX math ($$...$$ mid-line, \(...\), and $...$)
    text = text.replace(/(?<!\\)\$\$([^\n]+?)\$\$/g, (_m, mathBody) => {
        return stash(`<span class="md-math-inline">${renderKatex(mathBody, false)}</span>`)
    })
    text = text.replace(/\\\((.+?)\\\)/g, (_m, mathBody) => {
        return stash(`<span class="md-math-inline">${renderKatex(mathBody, false)}</span>`)
    })
    text = text.replace(/(?<!\\)(?<!\$)\$(?!\$)([^\s$](?:[^$\n]*?[^\s$])?)\$(?!\$)/g, (_m, mathBody) => {
        return stash(`<span class="md-math-inline">${renderKatex(mathBody, false)}</span>`)
    })

    // 6. Escape all remaining raw HTML
    let safe = escapeHtml(text)

    // 7. Inline emphasis & strikethrough
    safe = safe.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    safe = safe.replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
    safe = safe.replace(/(^|[^\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>')
    safe = safe.replace(/~~([^~\n]+)~~/g, '<del>$1</del>')

    // 8. Unescape literal escaped dollar signs and restore stashed HTML tokens
    safe = safe.replace(/\\\$/g, '$')
    safe = safe.replace(/\u0000MDPH(\d+)\u0000/g, (_m, idxStr) => placeholders[Number(idxStr)] ?? '')
    return safe
}

function highlightCodeBlock(langRaw: string, code: string): string {
    const langKey = langRaw.trim().toLowerCase()
    if (langKey === 'mermaid') {
        return `<div class="md-mermaid-block"><div class="md-code-header"><span>mermaid diagram</span></div><pre class="md-code-pre"><code>${escapeHtml(code)}</code></pre></div>`
    }
    const prismLang = LANGUAGE_ALIASES[langKey] || ''
    const grammar = prismLang ? (Prism.languages as Record<string, any>)[prismLang] : null
    const highlighted = grammar ? Prism.highlight(code, grammar, prismLang) : escapeHtml(code)
    const displayLabel = escapeHtml(langKey || 'text')
    const langClass = prismLang ? `language-${prismLang}` : 'language-none'

    return (
        `<div class="md-code-block">` +
        `<div class="md-code-header"><span>${displayLabel}</span></div>` +
        `<pre class="md-code-pre ${langClass}"><code class="${langClass}">${highlighted}</code></pre>` +
        `</div>`
    )
}

function splitTableCells(line: string): string[] {
    let trimmed = line.trim()
    if (trimmed.startsWith('|')) trimmed = trimmed.slice(1)
    if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1)
    return trimmed.split('|').map((c) => c.trim())
}

function parseTableSeparator(line: string): Array<'left' | 'center' | 'right'> | null {
    const trimmed = line.trim()
    if (!trimmed.includes('|') || !trimmed.includes('-')) return null
    const cells = splitTableCells(trimmed)
    if (cells.length === 0) return null
    const aligns: Array<'left' | 'center' | 'right'> = []
    for (const c of cells) {
        if (!/^:?-{2,}:?$/.test(c)) return null
        if (c.startsWith(':') && c.endsWith(':')) aligns.push('center')
        else if (c.endsWith(':')) aligns.push('right')
        else aligns.push('left')
    }
    return aligns
}

/** Render sanitized Markdown with GFM tables, admonitions, Prism code highlighting, and KaTeX math. */
export function renderMarkdown(source: string): string {
    if (!source) return ''
    const lines = source.replace(/\r\n/g, '\n').split('\n')
    const blocks: string[] = []
    let i = 0

    while (i < lines.length) {
        const line = lines[i]
        const trimmed = line.trim()

        // Blank line
        if (!trimmed) {
            i++
            continue
        }

        // Fenced code block ``` or ~~~
        const fenceMatch = line.match(/^\s*(`{3,}|~{3,})\s*([a-zA-Z0-9_-]*)\s*$/)
        if (fenceMatch) {
            const fenceChar = fenceMatch[1][0]
            const fenceLen = fenceMatch[1].length
            const lang = fenceMatch[2] || ''
            const codeLines: string[] = []
            i++
            const closeRe = new RegExp(`^\\s*${fenceChar === '`' ? '`' : '~'}{${fenceLen},}\\s*$`)
            while (i < lines.length && !closeRe.test(lines[i])) {
                codeLines.push(lines[i])
                i++
            }
            if (i < lines.length) i++
            blocks.push(highlightCodeBlock(lang, codeLines.join('\n')))
            continue
        }

        // Display math $$...$$ or \[...\] (single line or multi-line)
        const displayDelim = trimmed.startsWith('$$') ? '$$' : trimmed.startsWith('\\[') ? '\\]' : null
        if (displayDelim) {
            if (trimmed.length >= 4 && trimmed.endsWith(displayDelim) && !trimmed.slice(2, -2).includes(displayDelim)) {
                const body = trimmed.slice(2, -2).trim()
                blocks.push(`<div class="md-math-block">${renderKatex(body, true)}</div>`)
                i++
                continue
            }
            if (!trimmed.slice(2).includes(displayDelim)) {
                const mathLines: string[] = [trimmed.slice(2)]
                i++
                while (i < lines.length && !lines[i].trim().endsWith(displayDelim)) {
                    mathLines.push(lines[i])
                    i++
                }
                if (i < lines.length) {
                    const closing = lines[i].trim()
                    const prefix = closing.slice(0, -2)
                    if (prefix.trim()) mathLines.push(prefix)
                    i++
                }
                blocks.push(`<div class="md-math-block">${renderKatex(mathLines.join('\n').trim(), true)}</div>`)
                continue
            }
        }

        // MkDocs/Zensical Admonition: !!! note "Optional Title"
        const admMatch = line.match(/^!!!\s+([a-zA-Z0-9_-]+)(?:\s+"([^"]*)")?\s*$/)
        if (admMatch) {
            const rawKind = admMatch[1].toLowerCase()
            const kind = ['note', 'info', 'tip', 'warning', 'danger', 'important'].includes(rawKind)
                ? rawKind
                : 'note'
            const titleText = admMatch[2] || rawKind.toUpperCase()
            const bodyLines: string[] = []
            i++
            while (i < lines.length) {
                const cur = lines[i]
                if (!cur.trim()) {
                    if (i + 1 < lines.length && /^(\s{2,}|\t)/.test(lines[i + 1])) {
                        bodyLines.push('')
                        i++
                        continue
                    }
                    break
                }
                if (/^\s{4}/.test(cur)) {
                    bodyLines.push(cur.slice(4))
                    i++
                } else if (cur.startsWith('\t')) {
                    bodyLines.push(cur.slice(1))
                    i++
                } else if (/^\s{2}/.test(cur)) {
                    bodyLines.push(cur.slice(2))
                    i++
                } else {
                    break
                }
            }
            const innerHtml = renderMarkdown(bodyLines.join('\n'))
            blocks.push(
                `<div class="md-admonition md-admonition-${kind}">` +
                    `<div class="md-admonition-title">${escapeHtml(titleText)}</div>` +
                    `<div class="md-admonition-body">${innerHtml}</div>` +
                    `</div>`
            )
            continue
        }

        // Heading (# .. ######)
        const headingMatch = line.match(/^(#{1,6})\s+(.*)$/)
        if (headingMatch) {
            const level = headingMatch[1].length
            const text = headingMatch[2].trim()
            const slug = slugifyHeading(text)
            blocks.push(`<h${level} id="${escapeHtml(slug)}">${renderInline(text)}</h${level}>`)
            i++
            continue
        }

        // Horizontal rule
        if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(trimmed)) {
            blocks.push('<hr />')
            i++
            continue
        }

        // GFM Table
        if (line.includes('|') && i + 1 < lines.length) {
            const aligns = parseTableSeparator(lines[i + 1])
            if (aligns) {
                const headers = splitTableCells(line)
                i += 2
                const rows: string[][] = []
                while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
                    rows.push(splitTableCells(lines[i]))
                    i++
                }
                const thHtml = headers
                    .map((h, idx) => `<th style="text-align:${aligns[idx] || 'left'}">${renderInline(h)}</th>`)
                    .join('')
                const trHtml = rows
                    .map((row) => {
                        const tds = headers
                            .map((_h, idx) => `<td style="text-align:${aligns[idx] || 'left'}">${renderInline(row[idx] ?? '')}</td>`)
                            .join('')
                        return `<tr>${tds}</tr>`
                    })
                    .join('')
                blocks.push(
                    `<div class="md-table-wrap"><table><thead><tr>${thHtml}</tr></thead><tbody>${trHtml}</tbody></table></div>`
                )
                continue
            }
        }

        // Blockquote
        if (/^\s*>/.test(line)) {
            const quoteLines: string[] = []
            while (i < lines.length && /^\s*>/.test(lines[i])) {
                quoteLines.push(lines[i].replace(/^\s*>\s?/, ''))
                i++
            }
            blocks.push(`<blockquote>${renderMarkdown(quoteLines.join('\n'))}</blockquote>`)
            continue
        }

        // Unordered list
        if (/^\s*[-*+]\s+/.test(line)) {
            const items: string[] = []
            while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
                let itemText = lines[i].replace(/^\s*[-*+]\s+/, '')
                i++
                while (
                    i < lines.length &&
                    lines[i].trim() &&
                    !/^\s*[-*+]\s+/.test(lines[i]) &&
                    !/^\s*\d+\.\s+/.test(lines[i]) &&
                    !/^(#{1,6}|>|```|~~~|!!!|\$\$|\\\[)/.test(lines[i].trim()) &&
                    !/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(lines[i].trim())
                ) {
                    if (/^\s{2,}/.test(lines[i])) {
                        itemText += ' ' + lines[i].trim()
                        i++
                    } else {
                        break
                    }
                }
                items.push(`<li>${renderInline(itemText)}</li>`)
            }
            blocks.push(`<ul>${items.join('')}</ul>`)
            continue
        }

        // Ordered list
        if (/^\s*\d+\.\s+/.test(line)) {
            const items: string[] = []
            while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
                let itemText = lines[i].replace(/^\s*\d+\.\s+/, '')
                i++
                while (
                    i < lines.length &&
                    lines[i].trim() &&
                    !/^\s*\d+\.\s+/.test(lines[i]) &&
                    !/^\s*[-*+]\s+/.test(lines[i]) &&
                    !/^(#{1,6}|>|```|~~~|!!!|\$\$|\\\[)/.test(lines[i].trim())
                ) {
                    if (/^\s{2,}/.test(lines[i])) {
                        itemText += ' ' + lines[i].trim()
                        i++
                    } else {
                        break
                    }
                }
                items.push(`<li>${renderInline(itemText)}</li>`)
            }
            blocks.push(`<ol>${items.join('')}</ol>`)
            continue
        }

        // Paragraph
        const paraLines: string[] = [trimmed]
        i++
        while (i < lines.length) {
            const next = lines[i]
            const nextTrim = next.trim()
            if (
                !nextTrim ||
                /^(#{1,6}\s|>\s?|```|~~~|!!!|\$\$|\\\[)/.test(nextTrim) ||
                /^\s*[-*+]\s+/.test(next) ||
                /^\s*\d+\.\s+/.test(next) ||
                /^\s*([-*_])(?:\s*\1){2,}\s*$/.test(nextTrim) ||
                (next.includes('|') && i + 1 < lines.length && parseTableSeparator(lines[i + 1]) !== null)
            ) {
                break
            }
            paraLines.push(nextTrim)
            i++
        }
        blocks.push(`<p>${renderInline(paraLines.join(' '))}</p>`)
    }

    return blocks.join('\n')
}

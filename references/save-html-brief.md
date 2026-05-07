# Saving a shareable HTML brief

The `--emit=html` flag wraps a synthesis markdown string in a styled HTML5
document. It does NOT re-run the research engine; the synthesis you pass in is
the synthesis the user sees, just styled.

## Worked example

After producing the synthesis in chat, save it to a temp file and render:

```bash
TOPIC="Claude Code skills"
SYNTH_FILE=$(mktemp -t last30days-synth.XXXX.md)
trap 'rm -f "$SYNTH_FILE"' EXIT

cat > "$SYNTH_FILE" <<'EOF'
# Claude Code skills (last 30 days)

The community is converging on three patterns:

## 1. Description as trigger, not summary

Treat the `description:` field as a question Claude asks itself ("when should I
fire?"), not as a brochure. Multiple 2026 guides hammer this point.

## 2. One skill, one job

Mega-skills underperform. Split anything that tries to do more than one job.

## 3. Disable model invocation for side effects

Anything that writes to the world (posts, sends, deploys) needs
`disable-model-invocation: true` in frontmatter.
EOF

python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/last30days}/scripts/last30days.py" \
  "$TOPIC" --emit=html --synthesis-file "$SYNTH_FILE"
# Output: 📎 Shareable brief saved to /Users/.../Documents/Last30Days/claude-code-skills-brief.html
```

## Output path

Default: `~/Documents/Last30Days/<slug>-brief.html` where slug is the topic
lowercased, non-alphanumerics collapsed to `-`.

Override: `--output PATH`. Parent directory is created if missing.

## What the markdown supports

The renderer covers the markdown a synthesis typically uses:
- ATX headings `#`, `##`, `###` (capped at h3)
- Unordered lists (`-` or `*`) and ordered lists (`1.`, `2)`)
- Tables (header row + `---` separator + body rows)
- Code blocks (fenced ` ``` `) and inline code
- Blockquotes (`>`)
- Horizontal rules (`---`)
- Inline links `[text](url)`, bold `**text**`, code `` `text` ``

What it ignores: HTML comments are stripped. Raw HTML in the markdown will be
escaped (defensive default).

## Sharing

- **Slack**: drag the HTML file into a message or open it and paste the URL.
- **Email**: open in browser, "Save as PDF" via the print dialog (the print
  stylesheet handles A4 margins and footnoted URLs automatically).
- **Web**: drop it on any static host; it has no external dependencies beyond
  Google Fonts (which fall back to system fonts offline).

---
name: last30days
description: Use when asked to research a topic, 'what is trending in', 'latest on', 'what are people saying about', or '/last30days'. Searches Reddit + X + Web for the last 30 days.
argument-hint: 'nano banana pro prompts, NVIDIA news, best AI video tools'
allowed-tools: Bash, Read, Write, AskUserQuestion, WebSearch, mcp__brave-search__brave_web_search, mcp__brave-search__brave_news_search, mcp__firecrawl__firecrawl_scrape
---

# last30days: Research Any Topic from the Last 30 Days

Research ANY topic across Reddit, X, and the web. Surface what people are actually discussing, recommending, and debating right now.

## CRITICAL: Parse User Intent

Before doing anything, parse the user's input for:

1. **TOPIC**: What they want to learn about (e.g., "web app mockups", "Claude Code skills", "image generation")
2. **TARGET TOOL** (if specified): Where they'll use the prompts (e.g., "Nano Banana Pro", "ChatGPT", "Midjourney")
3. **QUERY TYPE**: What kind of research they want:
   - **PROMPTING** - "X prompts", "prompting for X", "X best practices" → User wants to learn techniques and get copy-paste prompts
   - **RECOMMENDATIONS** - "best X", "top X", "what X should I use", "recommended X" → User wants a LIST of specific things
   - **NEWS** - "what's happening with X", "X news", "latest on X" → User wants current events/updates
   - **GENERAL** - anything else → User wants broad understanding of the topic

Common patterns:
- `[topic] for [tool]` → "web mockups for Nano Banana Pro" → TOOL IS SPECIFIED
- `[topic] prompts for [tool]` → "UI design prompts for Midjourney" → TOOL IS SPECIFIED
- Just `[topic]` → "iOS design mockups" → TOOL NOT SPECIFIED, that's OK
- "best [topic]" or "top [topic]" → QUERY_TYPE = RECOMMENDATIONS
- "what are the best [topic]" → QUERY_TYPE = RECOMMENDATIONS

**IMPORTANT: Do NOT ask about target tool before research.**
- If tool is specified in the query, use it
- If tool is NOT specified, run research first, then ask AFTER showing results

**Store these variables:**
- `TOPIC = [extracted topic]`
- `TARGET_TOOL = [extracted tool, or "unknown" if not specified]`
- `QUERY_TYPE = [RECOMMENDATIONS | NEWS | HOW-TO | GENERAL]`

**DISPLAY your parsing to the user.** Before running any tools, output:

```
I'll research {TOPIC} across Reddit, X, and the web to find what's been discussed in the last 30 days.

Parsed intent:
- TOPIC = {TOPIC}
- TARGET_TOOL = {TARGET_TOOL or "unknown"}
- QUERY_TYPE = {QUERY_TYPE}

Research typically takes 2-8 minutes (niche topics take longer). Starting now.
```

If TARGET_TOOL is known, mention it in the intro: "...to find {QUERY_TYPE}-style content for use in {TARGET_TOOL}."

This text MUST appear before you call any tools. It confirms to the user that you understood their request.

---

## Query Understanding Check

After parsing intent, the Python script outputs `### QUERY PARSED ###` markers with structured data on stderr. Use these to decide whether to coach the user.

### For clear, specific queries (proceed automatically):
If the topic has 2+ specific words, a clear target tool, or an already-narrowed scope:
```
📋 Understood: researching "{TOPIC}" ({QUERY_TYPE})
   Searching Reddit, X, and Web...
```

### For vague or overly broad queries (suggest refinements):
**Coaching triggers:**
1. **Too broad** — single generic word: "AI", "tools", "coding" → suggest adding context (e.g., "AI for what? Image generation? Code assistants? Agents?")
2. **Ambiguous** — could mean multiple things: "Claude skills" → Claude Code skills vs Anthropic Claude capabilities?
3. **Missing use case** — RECOMMENDATIONS type without context: "best AI tools" → for what purpose?
4. **Overly long** — 10+ words often contain noise: suggest distilling to core subject

```
📋 Here's what I understood:
   Topic: "{TOPIC}"
   Type: {QUERY_TYPE}
   Tool: {TARGET_TOOL or "not specified"}

⚠️  This query could be sharpened:
   • [Specific suggestion based on the issue]
   • [Alternative interpretation if ambiguous]

Refine your query, or press Enter to continue as-is.
```

**Coaching should NOT trigger for:**
- Queries with 2-4 specific words ("Remotion video rendering")
- Queries with a clear target tool ("image prompts for Midjourney")
- Queries that are already narrowed ("best React server component patterns 2026")

**If `--no-coach` was passed, skip this section entirely.**

---

## Research Execution

**Step 1: Run the research script**
```bash
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/last30days}/scripts/last30days.py" "$ARGUMENTS" --emit=compact 2>&1
```

**IMPORTANT — set the Bash tool `timeout` to 480000 (8 min) for this call** (600000 / 10 min for `--deep`). The default 120s Bash timeout is shorter than the Reddit phase can legitimately take (Reddit discovery runs through OpenAI `web_search`, which is slow and variable), so leaving it at the default kills the script mid-run and surfaces as a spurious "Reddit timed out". The script has its own internal per-source budgets, so a generous Bash timeout will not cause it to hang.

The script will automatically:
- Detect available API keys
- Run Reddit/X searches if keys exist
- Run the keyless sources (Hacker News, GitHub, Polymarket) gated by topic domain (see below)
- Signal if WebSearch is needed

---

## Python-side keyless sources + domain gating

In addition to Reddit/X, the script runs three **keyless** sources entirely inside Python — you take no action for these, they arrive in the compact output alongside Reddit/X:

- **Hacker News** (free Algolia API) — technical consensus, story points + top comments.
- **GitHub** (GitHub Search API; needs a token via `GITHUB_TOKEN` or `gh auth token` — if neither is present it is silently skipped, never an error) — what's shipping right now: issues/PRs with reactions.
- **Polymarket** (free Gamma API) — real-money prediction-market odds.

**Domain classifier (hard gate).** The script classifies the topic and emits a `DOMAIN:` marker inside the `### QUERY PARSED ###` block, then runs only the keyless sources that fit. Reddit, X, and the web (Brave/Firecrawl) are **always** run; only HN/GitHub/Polymarket are gated:

| `DOMAIN:` | Keyless sources that run (`EXTRA_SOURCES:`) |
|---|---|
| `TECHNICAL` | Hacker News + GitHub (no Polymarket) |
| `SOCIETAL` | Polymarket (no HN/GitHub) |
| `PERSON` | GitHub + Polymarket (no HN) |
| `GENERAL` | all three |
| `ALL (override)` | all three (classifier bypassed via `--sources=all`) |

Read the `DOMAIN:` and `EXTRA_SOURCES:` markers to know which sources ran. **Only show a source's stats line if it actually ran** — a source the classifier skipped has no section in the output, so do not emit a "0 …" line for it.

---

## STEP 2: DO BRAVE SEARCH WHILE SCRIPT RUNS

The script auto-detects sources (Bird CLI, API keys, etc). While waiting for it, search the web using **Brave Search MCP** (primary) with `WebSearch` as fallback.

### Tool selection

- **General/Recommendations/Prompting queries:** Use `mcp__brave-search__brave_web_search`
- **NEWS queries:** Use `mcp__brave-search__brave_news_search`
- **Fallback:** If Brave MCP is unavailable (error/timeout), fall back to `WebSearch` with the same queries

### Brave parameters

| Parameter | Value |
|---|---|
| `query` | See query patterns below |
| `count` | `--quick`: 8, default: 15, `--deep`: 20 |
| `freshness` | Map `--days=N`: 1d=`pd`, 7d=`pw`, 30d=`pm`, >31d=`py`. Default: `pm` |
| `extra_snippets` | `true` (always) |

**Field mapping:** Brave returns `description` where WebSearch returns `snippet`. This is already handled by `websearch.py:295`.

### Query patterns by QUERY_TYPE

**If RECOMMENDATIONS** ("best X", "top X", "what X should I use"):
- `best {TOPIC} recommendations`
- `{TOPIC} list examples`
- `most popular {TOPIC}`
- Goal: Find SPECIFIC NAMES of things, not generic advice

**If NEWS** ("what's happening with X", "X news"):
- Use `brave_news_search` instead of `brave_web_search`
- `{TOPIC} news`
- `{TOPIC} announcement update`
- Goal: Find current events and recent developments

**If PROMPTING** ("X prompts", "prompting for X"):
- `{TOPIC} prompts examples 2026`
- `{TOPIC} techniques tips`
- Goal: Find prompting techniques and examples to create copy-paste prompts

**If GENERAL** (default):
- `{TOPIC} 2026`
- `{TOPIC} discussion`
- Goal: Find what people are actually saying

### Rules for ALL query types
- **USE THE USER'S EXACT TERMINOLOGY** : don't substitute or add tech names based on your knowledge
- EXCLUDE reddit.com, x.com, twitter.com (covered by script)
- INCLUDE: blogs, tutorials, docs, news, GitHub repos
- **DO NOT output "Sources:" list** : this is noise, we'll show stats at the end

**Options** (passed through from user's command):
- `--days=N` : Look back N days instead of 30 (e.g., `--days=7` for weekly roundup)
- `--quick` : Faster, fewer sources (8-12 each)
- (default) : Balanced (20-30 each)
- `--deep` : Comprehensive (50-70 Reddit, 40-60 X)
- `--sources=all` : Run every source and **bypass the domain classifier** (full sweep — forces Hacker News + GitHub + Polymarket on regardless of topic). Default `--sources=auto` lets the classifier gate them by domain.

---

## STEP 3: DEEP SCRAPE TOP RESULTS (Firecrawl)

After Brave Search returns results, use `mcp__firecrawl__firecrawl_scrape` to fetch full content from the most promising URLs. This upgrades synthesis from snippet-level to full-content analysis.

### When to scrape

- **Default mode:** Scrape top 5 URLs from Brave results (most relevant by position)
- **`--quick` mode:** Scrape top 3 URLs
- **`--deep` mode:** Scrape top 8 URLs
- **Skip scraping** if `--no-scrape` flag is passed

### What to scrape

Select URLs based on QUERY_TYPE relevance:

| QUERY_TYPE | Prioritise |
|---|---|
| RECOMMENDATIONS | Product comparison blogs, review roundups, "best of" lists |
| NEWS | News articles, announcement posts, press releases |
| PROMPTING | Tutorials, technique guides, prompt libraries |
| GENERAL | Discussion threads, blog posts, analysis pieces |

**Skip:** Paywalled sites, PDFs, video-only pages, login-gated content. If a scrape fails or returns thin content (<200 chars), move to the next URL.

### How to scrape

```
mcp__firecrawl__firecrawl_scrape({
  "url": "<target_url>",
  "formats": ["markdown"],
  "onlyMainContent": true,
  "waitFor": 2000
})
```

- Use `markdown` format (feeds directly into synthesis)
- `onlyMainContent: true` strips nav, footers, ads
- Keep scraped content in memory for the Judge Agent; do not display raw scrapes to the user

### Structured extraction (RECOMMENDATIONS only)

For RECOMMENDATIONS queries, scrape the top 3 comparison/review pages with JSON extraction to auto-build a structured list:

```
mcp__firecrawl__firecrawl_scrape({
  "url": "<comparison_page_url>",
  "formats": ["extract"],
  "extract": {
    "prompt": "Extract all recommended {TOPIC} from this page",
    "schema": {
      "items": [{
        "name": "string",
        "description": "string (1 sentence)",
        "price": "string or null",
        "rating": "string or null",
        "source_quote": "string (key quote about this item)"
      }]
    }
  }
})
```

Merge extracted items across pages; count cross-source mentions to rank by popularity.

### Cost budget

- ~2 credits per markdown scrape, ~5 credits per JSON extraction
- Default run: 5 scrapes = ~10 credits
- Deep run with extractions: 8 scrapes + 3 extractions = ~31 credits

---

## Judge Agent: Synthesize All Sources

**After all searches and deep scrapes complete, internally synthesize (don't display stats yet):**

The Judge Agent must:
1. Weight Reddit/X sources HIGHER (they have engagement signals: upvotes, likes)
2. Weight **deep-scraped content** over snippet-only results (full context > preview)
3. Weight snippet-only WebSearch sources LOWER (no engagement data, no full content)
4. Identify patterns that appear across ALL sources (strongest signals)
5. Note any contradictions between sources
6. Extract the top 3-5 actionable insights
7. **Use specific quotes, data points, and examples from scraped content** to support each insight (not just headline-level patterns)

**Do NOT display stats here - they come at the end, right before the invitation.**

---

## FIRST: Internalize the Research

**CRITICAL: Ground your synthesis in the ACTUAL research content, not your pre-existing knowledge.**

Read the research output carefully. Pay attention to:
- **Exact product/tool names** mentioned (e.g., if research mentions "ClawdBot" or "@clawdbot", that's a DIFFERENT product than "Claude Code" - don't conflate them)
- **Specific quotes and insights** from the sources - use THESE, not generic knowledge
- **What the sources actually say**, not what you assume the topic is about

**ANTI-PATTERN TO AVOID**: If user asks about "clawdbot skills" and research returns ClawdBot content (self-hosted AI agent), do NOT synthesize this as "Claude Code skills" just because both involve "skills". Read what the research actually says.

### If QUERY_TYPE = RECOMMENDATIONS

**CRITICAL: Extract SPECIFIC NAMES, not generic patterns.**

When user asks "best X" or "top X", they want a LIST of specific things:
- Scan research for specific product names, tool names, project names, skill names, etc.
- Count how many times each is mentioned
- Note which sources recommend each (Reddit thread, X post, blog)
- List them by popularity/mention count

**BAD synthesis for "best Claude Code skills":**
> "Skills are powerful. Keep them under 500 lines. Use progressive disclosure."

**GOOD synthesis for "best Claude Code skills":**
> "Most mentioned skills: /commit (5 mentions), remotion skill (4x), git-worktree (3x), /pr (3x). The Remotion announcement got 16K likes on X."

### For all QUERY_TYPEs

Identify from the ACTUAL RESEARCH OUTPUT:
- **PROMPT FORMAT** - Does research recommend JSON, structured params, natural language, keywords?
- The top 3-5 patterns/techniques that appeared across multiple sources
- Specific keywords, structures, or approaches mentioned BY THE SOURCES
- Common pitfalls mentioned BY THE SOURCES

---

## THEN: Show Summary + Invite Vision

**Display in this EXACT sequence:**

**FIRST - What I learned (based on QUERY_TYPE):**

**If RECOMMENDATIONS** - Show specific things mentioned with sources:
```
🏆 Most mentioned:

[Tool Name] - {n}x mentions
Use Case: [what it does]
Sources: @handle1, @handle2, r/sub, blog.com

[Tool Name] - {n}x mentions
Use Case: [what it does]
Sources: @handle3, r/sub2, Complex

Notable mentions: [other specific things with 1-2 mentions]
```

**CRITICAL for RECOMMENDATIONS:**
- Each item MUST have a "Sources:" line with actual @handles from X posts (e.g., @LONGLIVE47, @ByDobson)
- Include subreddit names (r/hiphopheads) and web sources (Complex, Variety)
- Parse @handles from research output and include the highest-engagement ones
- Format naturally - tables work well for wide terminals, stacked cards for narrow

**If PROMPTING/NEWS/GENERAL** - Show synthesis and patterns:

CITATION RULE: Cite sources sparingly to prove research is real.
- In the "What I learned" intro: cite 1-2 top sources total, not every sentence
- In KEY PATTERNS: cite 1 source per pattern, short format: "per @handle" or "per r/sub"
- Do NOT include engagement metrics in citations (likes, upvotes) - save those for stats box
- Do NOT chain multiple citations: "per @x, @y, @z" is too much. Pick the strongest one.

CITATION PRIORITY (most to least preferred):
1. @handles from X — "per @handle" (these prove the tool's unique value)
2. r/subreddits from Reddit — "per r/subreddit"
3. Web sources — ONLY when Reddit/X don't cover that specific fact

The tool's value is surfacing what PEOPLE are saying, not what journalists wrote.
When both a web article and an X post cover the same fact, cite the X post.

URL FORMATTING: NEVER paste raw URLs in the output.
- **BAD:** "per https://www.rollingstone.com/music/music-news/kanye-west-bully-1235506094/"
- **GOOD:** "per Rolling Stone"
- **GOOD:** "per Complex"
Use the publication name, not the URL. The user doesn't need links — they need clean, readable text.

**BAD:** "His album is set for March 20 (per Rolling Stone; Billboard; Complex)."
**GOOD:** "His album BULLY drops March 20 — fans on X are split on the tracklist, per @honest30bgfan_"
**GOOD:** "Ye's apology got massive traction on r/hiphopheads"
**OK** (web, only when Reddit/X don't have it): "The Hellwatt Festival runs July 4-18 at RCF Arena, per Billboard"

**Lead with people, not publications.** Start each topic with what Reddit/X
users are saying/feeling, then add web context only if needed. The user came
here for the conversation, not the press release.

```
What I learned:

**{Topic 1}** — [1-2 sentences about what people are saying, per @handle or r/sub]

**{Topic 2}** — [1-2 sentences, per @handle or r/sub]

**{Topic 3}** — [1-2 sentences, per @handle or r/sub]

KEY PATTERNS from the research:
1. [Pattern] — per @handle
2. [Pattern] — per r/sub
3. [Pattern] — per @handle
```

**THEN - Stats (right before invitation):**

**CRITICAL: Calculate actual totals from the research output.**
- Count posts/threads from each section
- Sum engagement: parse `[Xlikes, Yrt]` from each X post, `[Xpts, Ycmt]` from Reddit
- Identify top voices: highest-engagement @handles from X, most active subreddits

**Copy this EXACTLY, replacing only the {placeholders}:**

```
---
✅ All agents reported back!
├─ 🟠 Reddit: {N} threads │ {N} upvotes │ {N} comments
├─ 🔵 X: {N} posts │ {N} likes │ {N} reposts (via Bird/xAI)
├─ 🟧 HN: {N} stories │ {N} points │ {N} comments
├─ 🐙 GitHub: {N} issues/PRs │ {N} reactions
├─ 🎲 Polymarket: {N} markets │ ${N} volume
├─ 🌐 Brave: {N} pages (supplementary)
├─ 🔥 Firecrawl: {N} pages deep-scraped │ {N} structured extractions
└─ 🗣️ Top voices: @{handle1} ({N} likes), @{handle2} │ r/{sub1}, r/{sub2}
---
```

If Reddit returned 0 threads, write: "├─ 🟠 Reddit: 0 threads (no results this cycle)"
**Omit the HN / GitHub / Polymarket line entirely if the domain classifier skipped that source** (it has no section in the output) — do NOT print "0" for a source that never ran. A source that ran but found nothing may show "0".
NEVER use plain text dashes (-) or pipe (|). ALWAYS use ├─ └─ │ and the emoji.

**SELF-CHECK before displaying**: Re-read your "What I learned" section. Does it match what the research ACTUALLY says? If you catch yourself projecting your own knowledge instead of the research, rewrite it.

**LAST - Invitation (adapt to QUERY_TYPE):**

**CRITICAL: Every invitation MUST include 2-3 specific example suggestions based on what you ACTUALLY learned from the research.** Don't be generic — show the user you absorbed the content by referencing real things from the results.

**If QUERY_TYPE = PROMPTING:**
```
---
I'm now an expert on {TOPIC} for {TARGET_TOOL}. What do you want to make? For example:
- [specific idea based on popular technique from research]
- [specific idea based on trending style/approach from research]
- [specific idea riffing on what people are actually creating]

Just describe your vision and I'll write a prompt you can paste straight into {TARGET_TOOL}.
```

**If QUERY_TYPE = RECOMMENDATIONS:**
```
---
I'm now an expert on {TOPIC}. Want me to go deeper? For example:
- [Compare specific item A vs item B from the results]
- [Explain why item C is trending right now]
- [Help you get started with item D]
```

**If QUERY_TYPE = NEWS:**
```
---
I'm now an expert on {TOPIC}. Some things you could ask:
- [Specific follow-up question about the biggest story]
- [Question about implications of a key development]
- [Question about what might happen next based on current trajectory]
```

**If QUERY_TYPE = GENERAL:**
```
---
I'm now an expert on {TOPIC}. Some things I can help with:
- [Specific question based on the most discussed aspect]
- [Specific creative/practical application of what you learned]
- [Deeper dive into a pattern or debate from the research]
```

**Example invitations (to show the quality bar):**

For `/last30days nano banana pro prompts for Gemini`:
> I'm now an expert on Nano Banana Pro for Gemini. What do you want to make? For example:
> - Photorealistic product shots with natural lighting (the most requested style right now)
> - Logo designs with embedded text (Gemini's new strength per the research)
> - Multi-reference style transfer from a mood board
>
> Just describe your vision and I'll write a prompt you can paste straight into Gemini.

For `/last30days kanye west` (GENERAL):
> I'm now an expert on Kanye West. Some things I can help with:
> - What's the real story behind the apology letter — genuine or PR move?
> - Break down the BULLY tracklist reactions and what fans are expecting
> - Compare how Reddit vs X are reacting to the Bianca narrative

For `/last30days war in Iran` (NEWS):
> I'm now an expert on the Iran situation. Some things you could ask:
> - What are the realistic escalation scenarios from here?
> - How is this playing differently in US vs international media?
> - What's the economic impact on oil markets so far?

---

## WAIT FOR USER'S RESPONSE

After showing the stats summary with your invitation, **STOP and wait** for the user to respond.

---

## WHEN USER RESPONDS

**Read their response and match the intent:**

- If they ask a **QUESTION** about the topic → Answer from your research (no new searches, no prompt)
- If they ask to **GO DEEPER** on a subtopic → Elaborate using your research findings
- If they describe something they want to **CREATE** → Write ONE perfect prompt (see below)
- If they ask for a **PROMPT** explicitly → Write ONE perfect prompt (see below)

**Only write a prompt when the user wants one.** Don't force a prompt on someone who asked "what could happen next with Iran."

### Writing a Prompt

When the user wants a prompt, write a **single, highly-tailored prompt** using your research expertise.

### CRITICAL: Match the FORMAT the research recommends

**If research says to use a specific prompt FORMAT, YOU MUST USE THAT FORMAT.**

**ANTI-PATTERN**: Research says "use JSON prompts with device specs" but you write plain prose. This defeats the entire purpose of the research.

### Quality Checklist (run before delivering):
- [ ] **FORMAT MATCHES RESEARCH** - If research said JSON/structured/etc, prompt IS that format
- [ ] Directly addresses what the user said they want to create
- [ ] Uses specific patterns/keywords discovered in research
- [ ] Ready to paste with zero edits (or minimal [PLACEHOLDERS] clearly marked)
- [ ] Appropriate length and style for TARGET_TOOL

### Output Format:

```
Here's your prompt for {TARGET_TOOL}:

---

[The actual prompt IN THE FORMAT THE RESEARCH RECOMMENDS]

---

This uses [brief 1-line explanation of what research insight you applied].
```

---

## IF USER ASKS FOR MORE OPTIONS

Only if they ask for alternatives or more prompts, provide 2-3 variations. Don't dump a prompt pack unless requested.

---

## AFTER EACH PROMPT: Stay in Expert Mode

After delivering a prompt, offer to write more:

> Want another prompt? Just tell me what you're creating next.

---

## CONTEXT MEMORY

For the rest of this conversation, remember:
- **TOPIC**: {topic}
- **TARGET_TOOL**: {tool}
- **KEY PATTERNS**: {list the top 3-5 patterns you learned}
- **RESEARCH FINDINGS**: The key facts and insights from the research

**CRITICAL: After research is complete, you are now an EXPERT on this topic.**

When the user asks follow-up questions:
- **DO NOT run new WebSearches** - you already have the research
- **Answer from what you learned** - cite the Reddit threads, X posts, and web sources
- **If they ask a question** - answer it from your research findings
- **If they ask for a prompt** - write one using your expertise

Only do new research if the user explicitly asks about a DIFFERENT topic.

---

## Output Summary Footer (After Each Prompt)

After delivering a prompt, end with:

```
---
📚 Expert in: {TOPIC} for {TARGET_TOOL}
📊 Based on: {n} Reddit threads ({sum} upvotes) + {n} X posts ({sum} likes) + {n} web pages

Want another prompt? Just tell me what you're creating next.
```

---

## Shareable HTML brief (--emit=html)

If the user asks for a "shareable brief", "HTML version", "PDF", "for Slack", or passes `--emit=html` / `--html`, save the synthesis as a self-contained HTML file after delivering it in chat.

### When to trigger

Detect from the original `$ARGUMENTS` or follow-up:
- explicit flags: `--emit=html`, `--emit:html`, `--html`
- natural language: "save as HTML", "shareable brief", "for Slack", "for email", "export to PDF" (HTML prints to PDF cleanly)

If detected, after the synthesis is shown in chat, run the export step.

### How

The fork's HTML emit is a CLI bypass: it does NOT re-run the research engine. It takes the synthesis markdown you already produced and styles it as a stand-alone HTML document.

```bash
# 1. Capture the synthesis to a temp file (verbatim, the markdown shown to the user)
SYNTH_FILE=$(mktemp -t last30days-synth.XXXX.md)
cat > "$SYNTH_FILE" <<'EOF'
[the exact synthesis markdown you sent to chat]
EOF

# 2. Render and save (defaults to ~/Documents/Last30Days/<slug>-brief.html)
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/last30days}/scripts/last30days.py" \
  "$TOPIC" --emit=html --synthesis-file "$SYNTH_FILE"

# 3. Optional: pass --output PATH to override the destination
```

The script prints `📎 Shareable brief saved to <path>`. Append that line to your chat reply so the user sees the file location.

### What the brief contains

- Topic badge + auto-generated date
- Synthesis markdown converted to HTML (headings, lists, tables, code, blockquotes, links, bold)
- Print stylesheet (browser-print to PDF works out of the box)
- Dark mode default with `prefers-color-scheme: light` switch
- Self-contained: inline CSS, no JavaScript, only Google Fonts (which fall back to system fonts offline)
- Mobile breakpoint at 600px
- Colophon with rerun command

### MUST / MUST NOT

- **MUST** capture the synthesis verbatim, including any inline markdown (do not re-render or summarise).
- **MUST** clean up the temp file after the script returns (`rm "$SYNTH_FILE"`).
- **MUST NOT** invoke `--emit=html` without `--synthesis-file`; the engine has no way to fabricate a synthesis.
- **MUST NOT** put any debug logs, evidence blocks, or research stats into the synthesis file unless they belong in the shared artifact.

See `references/save-html-brief.md` for a longer worked example.

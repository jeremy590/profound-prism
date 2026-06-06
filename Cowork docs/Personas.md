# Personas — Role-Aware Profound Views

Six personas for the role-aware dashboard / agent system. Each persona is the seed for a downstream Profound Agent: the **description** is written as that agent's goal, the **questions** become preloaded FAQs on the dashboard, and the **data points** map directly to MCP/REST calls.

---

## 1. Commercial Director / CMO

**Focus:** Top-line AI search health, sentiment direction, share-of-voice vs. rivals, and shifts in how customers are searching for the category. The "should I worry / should I invest more?" view.

**Description (agent goal):** Deliver the Commercial Director a weekly executive view of AI search performance. Surface visibility trend, sentiment trajectory, share-of-voice vs. top competitors, and any emerging search themes that change how customers describe the category. Return only the 3–5 items that warrant escalation, a decision, or new funding — not a data dump.

**Questions at log-on:**
- How has our visibility score moved this week vs. last?
- Is sentiment about us trending positive or negative overall?
- Are any competitors gaining share-of-voice on us?
- Are there new ways customers are searching for our category?
- What's the one number I should care about today?

**Profound data to pull:**
- `get_visibility_report` — `visibility_score`, `share_of_voice`, period-over-period delta
- `get_visibility_report` with `asset_filter` (top 3–5 competitors) — competitive movement
- `get_sentiment_report` — headline `positive` / `negative` / `occurrences`
- `list_prompts` filtered by recent additions — emerging search themes in the category
- `get_referrals_report` — AI-driven visits as a commercial leading indicator

---

## 2. SEO / Optimization Lead

**Focus:** Category-level visibility, where citations are decaying, content gaps competitors are filling, what to refresh next.

**Description (agent goal):** Give the SEO Lead a working board of citation opportunities. Find pages where the brand was cited and lost rank, third-party pages where rivals hold citations the brand should own, and topics where category visibility is decaying. Prioritise outputs by potential traffic impact, not raw visibility score.

**Questions at log-on:**
- Which of our pages have lost citation share this week?
- Which root domains are AI engines citing for our category that aren't ours?
- Which AI engines are we under-cited on?
- Which topics in our category drive the most citations?
- Which competitor pages are winning the citations we want?

**Profound data to pull:**
- `get_citations_report` with `dimensions: ["root_domain"]` — citation share leaderboard
- `get_citations_report` with `dimensions: ["url"]` — owned-page citation counts + period delta
- `get_citations_report` with `model_filter` — engine-level gaps (Perplexity vs. ChatGPT vs. Gemini)
- `get_visibility_report` with `dimensions: ["topic"]` — topic-level visibility deltas
- `list_topics` + `list_tags` — taxonomy for grouping and filtering

---

## 3. Product Manager

**Focus:** How customers describe the product to AI, which use-cases it surfaces in, and the adjacent questions buyers are asking that the product should also answer. ("Voice of the customer through AI.")

**Description (agent goal):** Give the Product Manager a clustered view of how AI engines describe the product and which use-case prompts surface it. Cluster the prompts into themes (e.g. for Claude: "AI design support", "AI therapist", "AI coding assistant"), highlight growing vs. shrinking use-cases, and surface adjacent questions the product should also answer.

**Questions at log-on:**
- What are the top use-cases (prompt clusters) where our product shows up?
- Which use-cases are growing in prompt volume? Which are shrinking?
- When AI describes our product, which features does it highlight?
- What adjacent questions are people asking that we currently don't answer?
- Which competitor products are being recommended for our use-cases?

**Profound data to pull:**
- `list_prompts` + `get_prompt_answers` — real prompts + actual AI answers featuring the product
- `get_visibility_report` with `dimensions: ["prompt"]` — use-case-level visibility
- `get_citations_report` with `dimensions: ["prompt"]` — citation behaviour by use-case
- `get_visibility_report` with `dimensions: ["topic"]` — clustering use-cases
- `list_topics` — taxonomy for clustering
- **Layer later — DataForSEO People Also Ask:** for each top prompt theme, pull related/follow-up questions to enrich with adjacent demand (`dataforseo_labs_google_related_keywords` and related PAA endpoints)

---

## 4. Brand Lead

**Focus:** Sentiment by theme, how AI characterises the brand, how rivals are being framed, reputation risks and opportunities.

**Description (agent goal):** Give the Brand Lead a sentiment-first view of how AI engines characterise the brand and its competitors. Surface which themes are trending positive or negative, which attributes AI associates with the brand, where rivals are winning positive characterisation we should claim, and any reputation risks emerging in specific markets or engines.

**Questions at log-on:**
- Which sentiment themes are spiking (positive or negative) about us this week?
- How does our sentiment compare to top competitors theme-by-theme?
- What attributes is AI associating with our brand?
- What positive themes are competitors winning that we should claim?
- Is there a reputation risk emerging in any market or on any engine?

**Profound data to pull:**
- `get_sentiment_report` with `theme_filter` — sentiment per theme (pricing, quality, support, etc.)
- `get_sentiment_report` with `asset_filter` (brand + competitors) — side-by-side comparison
- `get_sentiment_report` with `model_filter` — engine-level sentiment drift
- `get_prompt_answers` — raw answer text for spot-checking brand characterisations
- `get_visibility_report` with `dimensions: ["persona"]` — how different audiences are being addressed

---

## 5. PR / Earned Media Lead

**Focus:** Citation outreach — finding high-value third-party publications and authors that write about the category but don't cite the brand, then pitching them.

**Description (agent goal):** Give the PR Lead a working list of third-party domains and authors who write about the category but don't currently cite the brand. Rank by citation volume in the category, identify the editor or author, and prepare personalised pitch drafts ready for review. Also surface citations the brand has lost and competitor wins on target publications.

**Questions at log-on:**
- Which third-party domains are AI engines citing most in our category?
- Of those, which aren't currently citing us?
- Where have we lost citations we used to hold?
- Which authors at our target publications write about the category?
- Which competitors are winning citations on the publications we want?

**Profound data to pull:**
- `get_citations_report` with `dimensions: ["root_domain"]` — third-party domain leaderboard
- `get_citations_report` with `dimensions: ["url"]` — page-level citation map
- `get_citations_report` filtered to exclude owned `root_domain_filter` — non-owned only
- `get_citations_report` with period delta — citation losses
- `get_citations_report` with `asset_filter` (competitor) — domains where they win and we don't
- **Layer later — contact enrichment (Clay / Apollo):** resolve domain → editor / author for the outreach draft step

---

## 6. Regional / Global Marketing Lead

**Focus:** Cross-market gap analysis. Per-country visibility, sentiment, and citation behaviour tied to business KPIs per market, with the *why* behind the differences and the localisation actions that follow. Directly addressing the gap Max called out: AI search performance is currently measured as a global aggregate while business reality is regional.

**Description (agent goal):** Give the Regional Lead a country-by-country view of AI search performance. Surface visibility, sentiment, and citation behaviour per market; tie each market's AI performance to its business KPIs; and explain *why* one market wins where another loses (which sources matter where — e.g. NHS in the UK vs. health ministry in Australia). Recommend localisation actions per market and flag prompts that don't translate cleanly between regions (e.g. "running indoors" makes sense in Dubai but not Switzerland) so the prompt set owner can add region-specific variants rather than translating one-to-one.

**Questions at log-on:**
- Which markets are we winning in vs. losing in this period?
- Why is market X outperforming market Y? Which sources matter where?
- Where does our AI performance line up with — or contradict — business performance per market?
- Which prompts don't have a sensible equivalent in market Z and need a regional rewrite?
- Where do we need to localise content urgently to recover ground?

**Profound data to pull:**
- `get_visibility_report` with `dimensions: ["region"]` — country leaderboard + period delta
- `get_citations_report` with `dimensions: ["root_domain", "region"]` + `region_filter` — which authoritative sources matter per market (the NHS-vs-health-ministry insight)
- `get_sentiment_report` with `region_filter` — sentiment per market
- `get_referrals_report` per market-specific domain — AI-driven traffic by region
- `list_regions` — region taxonomy
- `list_prompts` per region — exposing prompt-set divergence vs. overlap across markets
- **Layer later — business KPI overlay:** join per-region GA/GSC/ecommerce signals to the visibility table so AI performance is read alongside the commercial reality

---

## Shared infrastructure note

All six personas hit the same underlying data layer — discovery (`whoami`, `list_organizations`, `list_categories`, etc.) and then a small set of report tools. The only thing that changes per persona is the **slice** (dimensions + filters), the **questions** that frame it, and the **downstream agent** that the insights feed. That's the whole architectural point of the role-aware approach: one data backbone, six framed views, six different actions.

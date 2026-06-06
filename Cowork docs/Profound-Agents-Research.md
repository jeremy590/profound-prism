# Profound Agents — Research Notes

Compiled 2026-06-01 from Profound's own marketing site, product blog posts, developer docs, and third-party reviews. Use this as the briefing doc when shaping hackathon ideas around Agents.

---

## TL;DR

Profound Agents are **no-code, multi-step automation workflows** that sit on top of Profound's AEO (Answer Engine Optimization) data. Think n8n / Zapier, but every node has native access to Profound's prompt-monitoring data, AI-citation data, and bot-traffic data — plus LLM, scraping, and integration nodes. They're framed as the "Create" half of a "read/write" marketing platform: insights flow in, agents take action, results feed back in a closed loop.

Originally launched as "Profound Workflows" in **public beta on 11 Dec 2025**, rebranded to **Agents**. The CTO's May 2026 vision post makes clear the agent layer is now Profound's central bet, not a side feature.

---

## What an Agent actually is

**Structure:** A workflow graph built from typed nodes. Each node has inputs and outputs that pipe into the next. Examples of node types referenced in marketing:

- Web Page Scrape
- LLM prompt nodes
- Answer Engine Insights lookups (their proprietary AI-citation data)
- Prompt Volumes data (200M+ user prompts they've ingested)
- Google Search
- Agent Analytics nodes (Bot Visits, Human Referrals — server-log data)
- API call (generic)
- Integration / publishing nodes — WordPress, Sanity, Framer CMS, Slack, PartnerStack, Noble, OpenAI Ads
- Iteration nodes (loop over a list — e.g. run the same flow against 50 URLs)
- Brand Kit / Knowledge Base nodes (pull tone, guidelines, internal context)
- Human-in-the-loop approval steps

**Build experience:**
- Drag-and-drop UI ("Agent Builder") aimed at marketers, no dev required
- Library of pre-built templates
- **Agent Assistant** (newer) — describe an agent in plain text or voice and it generates the workflow, validates each node, catches errors, hands you something editable. Every node remains exposed and tweakable — not a black-box chat agent
- **Sheets mode** — process hundreds of inputs in parallel, each column is an agent, intermediate steps visible and editable per row

**Execution model today:** You launch a run, it executes the graph, you approve, it publishes/exports.

**Execution model coming (per CTO May 2026 post):** **Background Agents** — always-on, trigger-based, run 24/7. Watch a visibility score threshold, monitor a competitor's sitemap, spawn responses automatically. Surface what they did for human review. This is the bit the CTO is most excited about.

---

## Architecture / what's under the hood

Profound doesn't publicly name a single foundation model powering the agents — it appears model-agnostic. Key data points:

- Each Agent run **queries 16 reasoning models** to identify what AI engines are citing for a topic before drafting begins. So research-heavy nodes are fan-out across multiple LLM providers.
- Agents have access to Profound's own data layer, which runs **15M+ prompts/day** across ChatGPT, Perplexity, Copilot, Gemini etc., processing **5M+ citations daily** and **4M+ crawler visits**.
- The platform actively **scrapes the AI engines directly** (headless-browser style) rather than just hitting model APIs — Max's intuition on the call was correct. This is positioned as a moat vs. API-only competitors.
- A proprietary **AEO Content Score** (ML model trained on millions of top-cited pages) sits underneath the content-optimization nodes.
- **Profound MCP** — they ship a hosted MCP server so external agents (Claude, ChatGPT, custom builds) can query Profound's data. Tool surface includes Visibility Reports, Sentiment, Citation Reports, Agent Analytics, Raw Data Access, Docs search. This means **you can build a hackathon project that uses Profound as a data source via MCP** without rebuilding their scraping layer.
- **Ask Profound** — natural-language query layer over their data. Anything askable in Ask Profound can be automated by an Agent. Also runs in Slack (Teams coming).
- **Profound Docs** — a collaborative rich-text doc layer shipping in the platform, so Agent outputs have a home for review/approval/editing without leaving Profound.

**Closed-loop bit:** Agents track which content types/formats earn citations after publication and feed that back into recommendations for future runs. This is the differentiator vs. a generic AI writer — they're claiming their agents learn from their own citation data.

---

## Pre-built templates (the canonical use cases)

1. **Content Refresh** — find pages with declining AI citation rates, rewrite them structured to reclaim visibility.
2. **AEO FAQ Generation** — produce structured FAQs in the format AI engines prefer to cite.
3. **Competitive Research** — monitor what AI engines cite in your category, brief content to compete.
4. **Net-New Content Creation** — generate full articles from a topic prompt, structured for citation.

---

## Real customer use cases (named)

- **Hone** — used Agents to become the #1 AI-cited source for key topics; **800% visibility growth**.
- **MongoDB** (Fiona Erickson, SEO Lead) — automating SME workflows so subject-matter experts focus on judgment work.
- **Deel** (Anja Simic, Director of Content Marketing) — scaling content engine via workflow automation.
- **Plaid** (Sarah Shaffer, Organic Growth) — incorporating AEO into content optimization process.

Use-case patterns from the CTO post and node-release blogs:

- "Find the top 10 third-party pages citing our brand, draft personalized pitch emails to those publications about our new feature, drop drafts in #media-targets Slack." (verbatim example used by CTO)
- Weekly content decay reports
- Semantic competitor analyses
- SME briefing systems
- Affiliate activation via **PartnerStack node** — match domains driving AI visibility against PartnerStack's 65,000+ publisher/creator network, push unmatched ones in for outreach + contracting + payment.
- Media placement via **Noble node** — export domains to Noble, which automates outreach, drafting, negotiation, payment.
- **OpenAI Ads node** — programmatic ad activation tied to AEO signals.
- **Framer CMS node** — agents stage live CMS items.
- Slack alerts on visibility drops, competitor share-of-voice shifts, CMS draft ready notifications.

---

## Strategic narrative (worth borrowing for hackathon framing)

Quoted/paraphrased from CTO Dylan Babbs' May 2026 product vision post:

- **"Software should work alongside you"** — old model: you log in, find insights, leave to act. New model: platform finds opportunities, recommends, does most of the work; marketer orchestrates.
- **"Talk to your data"** — Ask Profound is step 1; anything you can ask, an Agent can automate.
- **"Build agents by describing them"** — Agent Assistant lowers the build barrier.
- **"Chat is not the workflow"** — they're explicit that chat-only agents are a step backward for enterprise: no auditability, no surgical edits. Structured nodes underneath are non-negotiable.
- **"Agents will run 24/7"** — Background Agents shipping next.
- **"Work needs a home"** — Profound Docs is being built so agent outputs have a review/approve surface in-platform.

---

## What this means for hackathon ideas

**Strong signals about what they'll reward:**

1. **Use the Agent Builder, not a side-channel script.** Their whole pitch is "we built the rails — show us a great workflow on them." Building outside the platform misses the point.
2. **Background-agent-flavoured ideas are on-trend.** Anything triggered by a signal (visibility threshold, competitor publishing, prompt-volume spike) rather than launched manually fits where they're heading.
3. **Closed-loop / measurable ideas.** Agents that track whether their output earned citations and self-adjust are what their differentiation rests on.
4. **MCP / Ask Profound as the interface.** A judge-friendly demo could combine Ask-Profound-style natural language with an Agent that gets built and run from the conversation.
5. **Integrate a node people haven't yet.** PartnerStack, Noble, Framer, OpenAI Ads, Slack are shipping fast. Building or simulating a new node (HubSpot? GSC? Shopify? Reddit? Clay enrichment?) could differentiate.

**Lines up well with the two ideas in Ideas.md:**

- **Role-aware dashboard** — fits "talk to your data" + "Ask Profound" framing; the market/country layer is uncovered ground per the CTO's "platform should find opportunities" pitch. Could be packaged as a Background Agent that runs per-role daily briefings.
- **GSC traffic → AI citation tracker** — naturally maps to an Agent: GSC node (would need to build/mock) → Answer Engine Insights node → LLM node to classify intent → output to Profound Docs / Slack. Hits the "session loss vs. touchpoint preserved" north-star metric Max said is unsolved.

---

## Open questions worth checking with Profound before locking the idea

- Which nodes can a hackathon participant build vs. only consume?
- Is the MCP server open to read AND write (i.e. can an external agent trigger Profound Agent runs), or read-only?
- Does Agent Sheets mode allow custom output integrations beyond CMS/Slack?
- Is there a GSC / GA4 node already, or is that genuinely greenfield?
- Can Background Agents be demoed today, or is it shipping post-hackathon?

---

## Sources

- [Profound — Agents feature page](https://www.tryprofound.com/features/agents)
- [Profound blog — Where we're taking the Profound product (May 2026, CTO Dylan Babbs)](https://www.tryprofound.com/blog/profound-2026)
- [Profound blog — Introducing Profound Workflows public beta (Dec 2025)](https://www.tryprofound.com/blog/profound-workflows-public-beta)
- [Profound blog — Noble nodes for Profound Agents](https://www.tryprofound.com/blog/introducing-noble-nodes-for-profound-agents)
- [Profound blog — PartnerStack nodes for Profound Agents](https://www.tryprofound.com/blog/introducing-partnerstack-nodes-for-profound-agents)
- [Profound blog — Framer integration nodes](https://www.tryprofound.com/blog/introducing-framer-integration-nodes-for-profound-agents)
- [Profound blog — Iteration nodes](https://www.tryprofound.com/blog/introducing-iteration-nodes-for-profound-agents)
- [Profound blog — OpenAI Ads nodes](https://www.tryprofound.com/blog/introducing-openai-ads-nodes-for-profound-agents)
- [Profound blog — CMS and Slack integrations](https://www.tryprofound.com/blog/cms-and-slack-integrations)
- [Profound MCP overview — developer docs](https://docs.tryprofound.com/agent-apis/mcp/overview)
- [Profound Agent Analytics + Bot Visits / Human Referrals nodes](https://www.tryprofound.com/features/agent-analytics)
- [Nick Lafferty — Profound Review (AEO/GEO platform deep dive)](https://nicklafferty.com/reviews/profound-best-aeo-geo-platform-for-ai-search/)
- [Comcast LIFT Labs — From SEO to GEO: How Profound Helps Companies Stay Visible in AI Search](https://lift.comcast.com/from-seo-to-geo-how-profound-helps-companies-stay-visible-in-ai-search/)
- [Analyze AI — Profound AI Review 2026](https://www.tryanalyze.ai/blog/profound-ai-review)

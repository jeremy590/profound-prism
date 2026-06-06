# CMO Exec Brief — ChatGPT (product lens), United States

**ChatGPT rank in product pack: #5 of 12, 0.0527 SoV vs leader Claude 0.071**  
_Our flagship asset trails four rivals (Claude, Google, OpenAI, Gemini); the SoV gap to the leader is only 0.0183, so the position is recoverable with focused investment._

## Escalation items
### 🔴 Net-negative sentiment on ChatGPT
- **Finding:** Overall sentiment is net -403 (1,923 positive vs 2,326 negative across 4,249 occurrences), led by privacy concerns (-40) and accuracy/hallucination themes.
- **Decision:** ESCALATE: fund a brand-risk narrative addressing privacy and accuracy perception before it caps visibility upside.
- **Dispatch:** `brand_risk_response`

### 🔴 Double-digit engine gaps on four surfaces
- **Finding:** We trail the leader by 20.4pts on Microsoft Copilot (25.9 vs 46.3), 17.0pts on Google Gemini (49.1 vs 66.1), 13.1pts on Perplexity (15.4 vs 28.5), and 10.8pts on Google AI Mode (42.6 vs 53.4).
- **Decision:** REALLOCATE engine-optimization effort toward Copilot and Perplexity where we rank #5 and the gaps are widest.
- **Dispatch:** `seo_citation_gap_closer`

### 🟠 Owned domains barely cited
- **Finding:** Best owned domain openai.com ranks only #5 of 8,192 (1.18% share) and chatgpt.com sits at #322 (0.04%); third-party sources reddit, youtube and medium outrank us.
- **Decision:** FUND citation outreach so our own properties carry more weight than community sources.
- **Dispatch:** `pr_citation_outreach`

### 🟠 Coding is the weakest product topic
- **Finding:** Coding visibility is just 30.4 with citation rate 0.042 across 8 prompts — our lowest topic, alongside Reasoning at 36.3.
- **Decision:** FUND topic-targeted content for Coding and Reasoning to lift visibility where we are most exposed.
- **Dispatch:** `seo_citation_gap_closer`

### 🟢 Recoverable distance to category leader
- **Finding:** The SoV gap from ChatGPT (0.0527) to leader Claude (0.071) is only 0.0183, narrower than the full pack spread.
- **Decision:** WORRY less about the headline rank; closing engine and citation gaps could move us past OpenAI, Google and Gemini who sit just ahead.
- **Dispatch:** —

## Proposed north-star
- **ChatGPT mean visibility (product lens, US)** = 37.5 vs leader 49.9
- _A 12.4pt visibility gap to Claude defines the gap to close across the six engines measured._

## Dispatch manifest
- **seo_citation_gap_closer** [⏸ guarded] — inputs: `{"region": "United States", "weak_engines": ["Microsoft Copilot", "Google Gemini", "Perplexity", "Google AI Mode"], "weak_topics": ["Coding", "Reasoning", "Enterprise", "Safety", "Speed"]}`
  - _no such agent in org yet — build the graph in Profound Agent Builder, then this run goes live_
- **brand_risk_response** [⏸ guarded] — inputs: `{"region": "United States", "negative_themes": ["privacy concerns", "data privacy concerns", "accuracy issues", "hallucinations", "confident hallucinations", "too expensive for casual users", "accuracy concerns", "concerns about accuracy"]}`
  - _no such agent in org yet — build the graph in Profound Agent Builder, then this run goes live_
- **pr_citation_outreach** [⏸ guarded] — inputs: `{"region": "United States", "owned_domains": ["openai.com", "chatgpt.com"], "top_third_party": ["reddit.com", "youtube.com", "medium.com", "linkedin.com", "openai.com"]}`
  - _no such agent in org yet — build the graph in Profound Agent Builder, then this run goes live_
# Scoring System

## Overview

Every new content item is scored by a local LLM (Ollama, default model: qwen3:4b) against three foundational principles. The scorer outputs a relevance score (0-1), a tier (personal/work), and a one-line reason.

Scoring is entirely free — runs locally, no API keys or paid services.

## Three Principles

Defined in `config/principles.yml`, encoded in the LLM system prompt (`src/ainews/scoring/scorer.py`).

### 1. Signal over Noise (Shannon)

> Does this contain verifiable, new information?

**Signal indicators:**
- Reproducible results, benchmarks, or code
- References specific methods, architectures, or datasets
- New information not already widely circulated
- Evidence or data supporting claims

**Noise indicators:**
- Vague claims ("this changes everything")
- Restated press releases without added insight
- Emotional framing for engagement
- Redundant coverage

### 2. Mechanism over Opinion (First Principles)

> Does this explain HOW/WHY, not just WHAT?

**Mechanism indicators:**
- Explains why a model/method works
- Discusses constraints, tradeoffs, failure modes
- Shows architecture decisions, training details, ablations

**Opinion indicators:**
- Claims without explanation ("this AI is amazing")
- Appeals to authority/popularity instead of evidence
- Conclusions without reasoning

### 3. Builders over Commentators (Skin in the Game)

> Is the author someone who builds or deploys?

**High trust:** ML engineers, researchers publishing code, people deploying models, authors of papers/frameworks/tools, engineering blogs from labs

**Low trust:** AI influencers, hype commentators, tool reviewers without implementation experience, aggregators without analysis

## Information Flow Model

Signal originates at the top and degrades as it flows down:

```
Tier 1 (Origin)         Research papers, open code, researcher blogs
    ↓
Tier 2 (Implementation) Engineering blogs, practitioner discussions, tutorials with code
    ↓
Tier 3 (Derivative)     News coverage (acceptable if adds context), product announcements
    ↓
Tier 4 (Noise)          Hype amplification, listicles, engagement-bait
```

The scorer returns a `source_proximity` field: `origin`, `implementation`, `derivative`, or `noise`.

## Two Tiers

Each item is classified into one tier:

### Personal (weight: 1.0)
Deep technical learning:
- Foundational model breakthroughs (architecture, training, capabilities)
- Open-source tooling, frameworks, libraries
- Novel research directions and paradigm shifts
- Mechanistic interpretability and understanding

### Work (weight: 0.7)
Professional relevance:
- AI tooling evaluations and practical comparisons
- How companies are adopting and integrating AI
- Architecture decisions and lessons learned in production
- Competitive landscape shifts that affect strategy

## Core Test

> "Would I still learn something from this if AI hype disappeared tomorrow?"

This is the litmus test encoded in both the principles config and the LLM prompt.

## LLM Prompt

The scorer sends two messages to Ollama:

1. **System prompt** — encodes the three principles, information flow model, and expected JSON output format
2. **User prompt** — includes the item's title, source, author, tags, text (truncated to 2000 chars), and both tier definitions

The LLM responds with JSON:
```json
{
  "relevance_score": 0.85,
  "tier": "personal",
  "reason": "Original research with reproducible benchmarks from a lab engineer",
  "key_topics": ["transformer", "attention"],
  "source_proximity": "origin"
}
```

## Score Interpretation

| Score | Badge Color | Meaning |
|-------|------------|---------|
| 0.7 - 1.0 | Green | High signal — must-read |
| 0.4 - 0.69 | Yellow | Mixed — some value |
| 0.0 - 0.39 | Grey | Low signal — likely noise |

## Performance

- **Model:** qwen3:4b (runs on CPU, ~15-30s per item)
- **Batch size:** 30 unscored items per cycle
- **Timeout:** 300s per item (accommodates cold starts)
- **Failure handling:** defaults to score 0.5 / tier "personal" if LLM response can't be parsed

## Configuration

| Setting | Default | Env var |
|---------|---------|---------|
| Model | qwen3:4b | `AINEWS_OLLAMA_MODEL` |
| Ollama URL | http://localhost:11434 | `AINEWS_OLLAMA_BASE_URL` |
| Fetch interval | 30 min | `AINEWS_FETCH_INTERVAL_MINUTES` |

---

*Last updated: 2026-03-07*

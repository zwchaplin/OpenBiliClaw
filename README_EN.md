<div align="center">

# 🦀 OpenBiliClaw

**A general-purpose personalized content discovery Agent — runs locally, understands you across platforms, built only for you**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LINUX DO](https://img.shields.io/badge/LINUX_DO-Community-black?style=flat-square&logo=linux)](https://linux.do/)
[![Discussion](https://img.shields.io/badge/LINUX_DO-Discussion-orange?style=flat-square&logo=discourse)](https://linux.do/t/topic/1978894)

English | [中文](README.md)

</div>

> The name comes from Bilibili (`Bili` = Bilibili, `Claw` = "the claw that grabs content for you") — the project started as a Bilibili-only tool. Since v0.3.0 it has evolved into a general cross-platform Agent: Bilibili / Xiaohongshu / generic Web adapters all live in production, with more platforms on the roadmap.

---

## 📌 v0.3.0 Highlights (2026-04-28)

- **🌐 General multi-source architecture in production** — evolved from a Bilibili-only tool into a general-purpose content Agent; Xiaohongshu and generic-Web adapters shipped
- **🔌 Local embedding fallback** — optional Ollama + bge-m3, no extra API key needed for similarity computation (CPU-only, works on Mac/Win/Linux)
- **⚡ "Reshuffle" 5x faster** — popup reshuffle from 2.6s → 0.6s; rapid clicks no longer feel laggy
- **🎯 Cross-source topic dedup** — any single topic capped at ≤10% of the candidate pool; no more "all AI all day"

Full changelog: [docs/changelog.md](docs/changelog.md).

---

## Why OpenBiliClaw?

Recommendation systems are essentially a **middleman** — the platform sits between millions of videos and millions of users, matching and distributing content at scale. Modern systems are far more sophisticated than "just optimizing CTR": they jointly weigh click-through rate, completion rate, like/coin probability, dwell time, user retention, creator ecosystem health, ad revenue, and a dozen other objectives, compressing them into a single weighted ranking score. Sounds scientific, but here's the catch: **the weights are set by the platform, and the optimization targets ultimately serve the platform** — user satisfaction is valued as a means to retention and monetization, not as an end in itself. You think you're choosing content, but really the middleman decides what you get to see. The result: recommendations look more and more like what you've already watched, and the occasional surprise is pure luck.

**OpenBiliClaw is fundamentally different.** It's a locally-running AI Agent that doesn't care what everyone else watches. Instead, it understands **who you are**:

### 🧠 Understands *why* you like things, not just *what* you've watched

It infers your MBTI, cognitive style, and deep psychological needs from your behaviour, building a five-layer soul profile (Event → Preference → Awareness → Insight → Soul). It's not matching video tags — it's understanding you as a person.

### 🔮 Actively breaks your filter bubble

This is the core differentiator: the system **guesses domains you might enjoy but have never explored**. Someone into mechanical watches might love architectural aesthetics; a quantum physics viewer might resonate with philosophy — it uses psychological bridging logic to proactively explore, promotes correct guesses to real interests, and quietly retires wrong ones.

### 🔒 100% local, 100% yours

All data lives in a single SQLite file on your disk. LLM calls use your own API key. No cloud, no accounts, no one else can see your profile. How this Agent grows is entirely your call — send feedback, chat with it, swap LLMs, edit the database, whatever you want.

> 💡 **How it compares**
>
> | | Bilibili Official | Keyword Filter Plugins | OpenBiliClaw |
> |---|---|---|---|
> | Recommendation logic | Collaborative filtering | Tag matching | Psychological profiling + 5-layer memory |
> | Filter bubble | Gets narrower | Doesn't address it | Speculative interests actively break it |
> | Data ownership | Platform-owned | Usually cloud | 100% local |
> | Explains why | "Guess you'll like" | None | Friend-like explanations |
> | Customizable | No | Low | Swap LLMs / edit profile / write Skills |

## 🚀 Quick Start

### 🧩 Step 1: Install the Chrome Extension

The extension is your main interface — it shows recommendations in a Bilibili side panel, collects behavior, and lets you chat with the agent.

1. Open [OpenBiliClaw Releases](https://github.com/whiteguo233/OpenBiliClaw/releases) and find the latest `extension-v*` release
2. Download `openbiliclaw-extension-v*.zip` from that release
3. Open `chrome://extensions/`, enable "Developer mode" in the top right
4. Drag the downloaded `.zip` file into the page to install

> Developers can also `cd extension && npm install && npm run package` to build from source.

#### Important: log in to **every source you want to use**, in the same browser the extension is installed in

OpenBiliClaw doesn't farm credentials — it reuses **your** current browser sessions to discover content cross-platform. So after installing the extension, log in to every source you care about **in the same browser**:

| Source | How to log in | What you lose if you don't |
|---|---|---|
| **Bilibili** | Just log in normally at https://www.bilibili.com (the v0.3.12+ extension auto-syncs the cookie to the backend) | The backend can't fetch your watch history / favorites / following → your soul profile won't reflect your real interests; recommendations degrade to public trending |
| **Xiaohongshu** | Log in normally at https://www.xiaohongshu.com | The backend never crawls Xiaohongshu directly — **all discovery + detail fetches happen through your extension in hidden tabs**. No login = no Xiaohongshu content at all |
| Generic web sources | Log in normally on that site | Same as above |

> 💡 **Strongly recommended for Xiaohongshu: use a CDP-mode Chrome to reuse the login session** (avoids anti-scraping). Launch a separate-profile Chrome with `--remote-debugging-port=9222`, manually log in once, then set `[sources.browser] cdp_url = "http://localhost:9222"` in `config.toml`. See [config reference](docs/modules/config.md#sourcesbrowser).

### ⚙️ Step 2: Run the Backend Locally

> Pre-built backend binaries / one-liner install scripts are no longer published. **Run from source instead** — better dev ergonomics and clearer failure modes.

```bash
git clone https://github.com/whiteguo233/OpenBiliClaw.git
cd OpenBiliClaw

# Recommended: uv
uv sync

# Copy config template, fill in LLM API key etc.
cp config.example.toml config.toml

# One-command init (fetch history · build soul profile · first discovery)
uv run openbiliclaw init

# Start the backend API (default 127.0.0.1:8420 — the extension connects here)
uv run openbiliclaw serve-api
```

> 🧠 **Optional: local embedding fallback (no extra API key)** — install Ollama once:
> macOS: `brew install ollama && ollama serve &`; Windows: download from [ollama.com/download](https://ollama.com/download); Linux: `curl -fsSL https://ollama.com/install.sh | sh && ollama serve &`.
> Then `uv run openbiliclaw setup-embedding` auto-pulls `bge-m3` (~568MB, CPU-only) and writes the config.

For full dev environment, configuration and CLI reference, see [Contributing Guide](docs/contributing.md) · [CLI Reference](docs/modules/cli.md) · [Config Reference](docs/modules/config.md).

## 🤖 Integrate with OpenClaw / AI Coding Agents

This repo ships a [workspace skill](skills/openbiliclaw-adapter/SKILL.md). Point any skill-aware AI coding agent (OpenClaw / Claude Code / Codex CLI / Cursor, etc.) at this checkout and it can drive your local OpenBiliClaw directly.

### What you get after integration

- ✨ **Proactive recommendations** — the system continuously discovers content in the background; when it finds a high-scoring surprise, it pushes to OpenClaw via WebSocket — **you don't have to ask**
- 🔮 **Proactive interest probing** — the system guesses you might be into a new domain, generates a hypothesis and a question, and has OpenClaw come ask you "does this direction resonate?" — your answer automatically refines the profile
- 💬 **Socratic dialogue** — not just interest confirmation; OpenClaw can have deep conversations: probing motivations, proposing hypotheses, confirming understanding — the more you talk, the better it knows you
- 📖 **Read the current soul profile** — MBTI, core traits, deep needs, interest domains
- 🎯 **Fetch personalized recommendations on demand** — with explanations, confidence scores, and topic labels
- 💬 **Write feedback back into the learning loop** — `like` / `dislike` / `comment` instantly update the profile and pool scoring
- 🔄 **Sync Bilibili account signals** — pull history / favorites / following and feed them into the memory system

### One-sentence integration prompt

Paste the following into OpenClaw (or Claude Code / Codex CLI / Cursor) — it will read the guide and wire everything up:

```text
Please follow https://raw.githubusercontent.com/whiteguo233/OpenBiliClaw/main/docs/openclaw-quickstart.md to integrate this repository into OpenClaw (use Bash `curl` to fetch the document, NOT WebFetch — WebFetch summarises markdown and drops critical commands).
```

### Usage examples

After integration, it's not just "you ask, it answers" — **the system comes to you**. Here are the two core scenarios:

#### Scenario 1: System proactively pushes a surprise recommendation

OpenClaw is running `listen` in the background. After a refresh cycle, the system finds a high-scoring piece of content:

> **OpenClaw** (receives WebSocket `delight.candidate`, comes to you proactively):
>
> > Just found something you might unexpectedly enjoy:
> > **"Why You Can't Actually Lie Flat Even Back in a Small Town"** — the Minsky moment of county economies. You've been deep in geopolitics and macro debt; this one dissects how land finance and the debt cycle mesh together. `[BV1KMwuzdEcB]`
> >
> > Want to check it out?
>
> **You**: "That one nailed it."
>
> **OpenClaw** (internally runs `submit-feedback --recommendation-id 4268 --feedback-type like`)

You never asked for a recommendation — the system surfaced it on its own.

#### Scenario 2: System proactively asks about your interests

OpenClaw receives an `interest.probe` event (or pulls `next-probe`) and finds a speculative-interest hypothesis waiting for confirmation:

> **OpenClaw** (comes to you proactively):
>
> > I've been picking up signals that you might be into **architectural aesthetics** (e.g., parametric design, concrete minimalism) — you've been watching a lot of content about structure and space lately. Does this direction resonate with you?
>
> **You**: "Yeah, I've been looking at a lot of parametric design stuff. Tadao Ando's exposed concrete aesthetic really gets me."
>
> **OpenClaw** (internally runs `chat --message "Yeah, I've been looking at…"`, returns a Socratic follow-up):
>
> > Here's my hypothesis — you're not just interested in buildings, you're drawn to how minimal elements create maximum tension. Ando's approach to concrete is the same aesthetic drive as your obsession with "making the gears mesh" when you analyze LLM architectures. Am I close?

The dialogue automatically feeds back into the soul profile — the next discovery cycle will incorporate architectural aesthetics as a real interest and start searching in that direction.

#### Scenario 3: You can also just ask for recommendations

Of course, the traditional "you ask → it answers" flow works too:

> **You**: "Recommend three Bilibili videos worth watching today."
>
> **OpenClaw** (internally runs `recommend --limit 3`, formats and replies)

The whole loop stays local — OpenClaw just calls the CLI bridge; your profile and data never leave the SQLite file on your disk.

> 📖 Full command reference and troubleshooting: [OpenClaw Integration Guide](docs/openclaw-quickstart.md).

## ✨ Key Features

- 🧠 **Five-Layer Soul Profile** — Event → Preference → Awareness → Insight → Soul, inferring MBTI, cognitive style, and deep needs — like a psychologist understanding you
- 🔮 **Speculative Interest System** — Uses psychological bridging logic to guess unexplored domains you might love; promotes correct guesses, retires wrong ones, continuously breaking the filter bubble
- 🌐 **Cross-Platform Sources** — Started on Bilibili, now extended to Xiaohongshu and generic Web; the architecture is built to keep adding more platforms. Your interests no longer get siloed
- 🔍 **Multi-Source Discovery Strategies** — Bilibili four strategies (Search · Related Chain · Trending · Cross-domain Explore) + Xiaohongshu safe discovery (passive collection · keyword search · creator subscription · init-profile import), coordinated cross-platform
- 🎯 **Smart Diversity** — PoolCurator five-dimension scoring + cross-source/round topic quota (any topic ≤10% of pool) + share-aware pool trimming that protects smaller sources; goodbye to "all AI all day"
- ⚡ **Instant "Reshuffle"** — popup reshuffle ~0.6s (down from 2.6s in v0.3.0); rapid clicks stay snappy
- 💬 **Warm Recommendations** — Not "because you watched similar videos", but friend-like explanations of why you'd enjoy something
- 🔄 **Continuous Learning** — Socratic dialogue + behavioral analysis + instant feedback, understands you better over time
- 🧩 **Chrome Extension** — Side panel for recommendations, cross-site behavior collection (Bilibili + Xiaohongshu), chat, and cognition update cards — install and go
- 🔬 **Self-Optimizing Eval Loops** — Five modules each have an LLM-as-judge SGD/RL loop that automatically improves prompt quality over rounds — no manual tuning needed
- 🔒 **Fully Private** — All data in local SQLite; LLM calls use your own key; each instance is built for exactly one person
- 🔌 **Local Embedding Fallback** — Optional Ollama + bge-m3, no extra embedding API key required for similarity computation (CPU-only, runs on Mac/Win/Linux)
- 🔧 **Fully Controllable** — Swap LLMs per module, edit your profile directly, write custom Skills to extend discovery

## 🏛️ Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Chrome Extension                   │
│ (Behavior · Recs · Chat · Cookie Sync · XHS Init)       │
└────────────────────────┬────────────────────────────┘
                         │ REST API / WebSocket cookie request
┌────────────────────────▼────────────────────────────┐
│                 Agent Orchestration                   │
│            (Skill System · Dialogue Mgmt)            │
├─────────┬──────────┬───────────┬────────────────────┤
│  Soul   │ Memory   │ Discovery │  Recommendation    │
│  Engine │ System   │  Engine   │     Engine          │
│(Profile)│(5-Layer) │(4-Strategy│   (Expression)     │
├─────────┴──────────┴───────────┴────────────────────┤
│ LLM Adapters · Bilibili API · Extension Proxy · SQLite│
└─────────────────────────────────────────────────────┘
```

### Content Discovery Engine

Four Bilibili strategies work in coordination, each with independent API quota, and the source layer also accepts Xiaohongshu extension-proxy signals:

| Strategy | Description | Quota |
|----------|-------------|-------|
| **Search** | Generates queries from interests + speculative interests | Fair share |
| **Trending** | Popular content from multiple Bilibili ranking categories | Fair share |
| **Related Chain** | Expands from seed videos along recommendation chains | Fair share |
| **Explore** | LLM-driven cross-domain exploration | Fair share |

Results go through multi-dimensional diversity selection: source-family reservation (the four Bilibili strategies plus one unified `xiaohongshu` family) → topic deduplication → style balancing → ceiling caps, ensuring broad coverage in final recommendations.

For first-run profiling, `openbiliclaw init` can also enqueue an XHS `bootstrap_profile` task. The extension opens Xiaohongshu in the user's logged-in browser session; explicit scrolling tasks open `/explore` in the foreground and click the page's own "Me" profile entry instead of directly jumping to the profile URL. It then parses rendered profile state / DOM for saved / liked notes, and only imports Xiaohongshu-page history when the site exposes an explicit history/footprint state. Explicit scrolling tasks return `partial` batches as new notes appear, then finish with a final result. The backend converts those notes into normal `favorite / like / view` events and still does not crawl or log into Xiaohongshu directly.

### Soul Engine

Infers from user behavior:
- **Personality Portrait** — Natural language user profile
- **MBTI** — Four dimensions with confidence scores
- **Cognitive Style** — Information processing preferences
- **Deep Needs** — Psychological content drivers
- **Speculative Interests** — System-predicted potential interest domains (e.g., molecular gastronomy, architectural aesthetics, watchmaking...)

## 🏗️ Project Structure

```
OpenBiliClaw/
├── src/openbiliclaw/          # Python backend core
│   ├── agent/                 # Agent orchestration & Skill system
│   ├── soul/                  # Soul Engine (profiling · MBTI · interest speculation)
│   ├── memory/                # Multi-layer memory system
│   ├── discovery/             # Discovery engine (4 strategies · quota balancing · diversity)
│   ├── recommendation/        # Recommendation & expression engine
│   ├── sources/               # Source adapters and XHS task bridge
│   ├── bilibili/              # Bilibili API layer (WBI signing · rate control)
│   ├── llm/                   # Multi-model LLM adapters
│   └── storage/               # Data storage layer
├── extension/                 # Chrome browser extension
├── skills/                    # Built-in Skill definitions
├── docs/                      # Documentation
└── tests/                     # Tests (650+)
```

## 🛠️ Tech Stack

| Module | Technology |
|--------|-----------|
| Backend | Python 3.11+ |
| Browser Extension | TypeScript + Chrome Extension (Manifest V3) |
| LLM | Built-in Gemini / DeepSeek / OpenAI / Claude / OpenRouter / Ollama; any OpenAI-compatible endpoint works via custom base_url |
| Bilibili API | Custom client (WBI signing · v_voucher auto-recovery · rate control) |
| Xiaohongshu | Extension DOM/state extraction + task dispatch; scrolling init imports open `/explore` in the foreground, click the page's profile entry, then use bounded scrolling and partial batches; no backend crawling |
| Storage | SQLite + Embedding vector index |
| Agent Framework | Lightweight custom framework |

## 📖 Documentation

- [Documentation Hub](docs/index.md) — All-in-one entry point
- [Project Spec](docs/spec.md) — Complete design & planning
- [Architecture](docs/architecture.md) — System architecture deep dive
- [Memory Design](docs/memory-design.md) — Multi-layer memory architecture
- [Discovery Engine](docs/modules/discovery.md) — 4-strategy discovery + diversity selection
- [Soul Engine](docs/modules/soul.md) — Deep profiling + MBTI + interest speculation
- [CLI Reference](docs/modules/cli.md) · [Config Reference](docs/modules/config.md)
- [Contributing Guide](docs/contributing.md)

## 📜 Release History

| Version | Date | Key changes |
|---|---|---|
| **v0.3.45** | 2026-05-04 | "Reshuffle" stress-tested at 30 rounds, **all <1s** (P50 0.41s / P99 0.85s): MMR embedding warm-ahead into SQLite L2 during discovery, serve() switched to cache-only never calling the provider; `mark_pool_items_shown` detached from the critical path. |
| v0.3.44 | 2026-05-04 | MMR diversification (α·relevance − β·max_cosine_to_picked) replaces pure string-quota caps; every reshuffle hits unique_topics=10/10 and top_topic_share≤10%. |
| v0.3.37 | 2026-05-04 | Real-time popup ↔ backend sync: `delight.refreshed` / `pool_status` WebSocket events, `proactive_push_interval` 600 → 120. |
| v0.3.26 | 2026-05-02 | LLM billing module (`openbiliclaw cost`) + cost-friendly defaults (reasoning off · discovery 8h); fresh installs target ≈¥0.5/day. |
| v0.3.0 | 2026-04-28 | General-purpose multi-source architecture (Xiaohongshu / Web) · local Ollama embedding fallback · cross-source topic quota. |

Full history: [docs/changelog.md](docs/changelog.md)

## 🗺️ Roadmap

OpenBiliClaw aims to be your **personalized entry point to the entire web**. Started on Bilibili, v0.3.0 shipped Xiaohongshu and generic-Web adapters; next:

- **More content sources** — Zhihu, V2EX, Douyin, Weibo, various BBS / forums; each platform is a `SourceAdapter` and the architecture is proven extensible
- **Cross-platform interest fusion** — your mechanical-keyboard interest from Bilibili + your coffee-gear interest from Xiaohongshu = one complete you. Profile fusion stops your interests from being fragmented across silos
- **Smarter cross-source discovery** — "you started following coffee gear on Xiaohongshu, here's a hand-drip documentary on Bilibili you might love"
- **Community ecosystem** — user-defined SourceAdapters, shared discovery strategies, contributed platform adapters

## 🤝 Contributing

Contributions welcome! See the [Contributing Guide](docs/contributing.md) to get started.

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=whiteguo233/OpenBiliClaw&type=Date)](https://www.star-history.com/#whiteguo233/OpenBiliClaw&Date)

## 📄 License

[MIT](LICENSE)

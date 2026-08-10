# Agentic Content Pipeline

FastAPI service that generates content through an explicit multi-step agent loop
(**Plan → Draft → Critique → Revise → Finalize**). A **contextual Thompson Sampling
bandit** chooses the prompt strategy (`concise` / `storytelling` / `data_driven`)
per **platform**, and user feedback updates the bandit so it improves over time.

Supported platforms: LinkedIn, X/Twitter, Medium, YouTube script, newsletter,
Instagram caption, Threads — each with length caps, tone, CTA, hashtag, and
formatting presets.

> **LLM note:** The original SPEC suggested Anthropic Claude. This implementation
> supports **Cursor SDK** (`CURSOR_API_KEY`, default when set) and **Google Gemini**
> (`GEMINI_API_KEY`). Set `LLM_PROVIDER=cursor|gemini|auto|fake`.
>
> If both keys fail, set `USE_FAKE_LLM=true` to run the full pipeline with a
> deterministic stub (same path tests use).

This is deliberately **not** full RL (no PPO/DPO). Thompson Sampling over pipeline
arms is a lightweight, interview-defensible choice given the cost/latency of LLM
rollouts.

---

## Architecture

```
Client
  │
  ├─ POST /content/generate  ──► FastAPI ──► Postgres (job row)
  │                                  │
  │                                  └─► Arq enqueue ──► Redis
  │                                                         │
  │                                                         ▼
  │                                              Worker (Arq)
  │                                                │
  │                                                ├─ Bandit.select_arm(platform)
  │                                                ├─ Plan + draft (platform preset)
  │                                                ├─ Critic (rubric + Flesch + n-grams + length)
  │                                                ├─ Revise loop until score ≥ threshold
  │                                                └─ Persist versions + soft bandit update
  │
  ├─ GET  /content/{id}          ◄── poll status + versions
  ├─ WS   /content/{id}/stream   ◄── Redis pub/sub status events
  ├─ POST /content/{id}/feedback ──► update Beta(α, β) for the arm used
  └─ GET  /bandit/stats          ◄── current posteriors per arm
```

### Bandit (Thompson Sampling)

- **Arms:** `prompt_style ∈ {concise, storytelling, data_driven}`
- **Context:** separate Beta posterior per `(prompt_style, platform)` — 21 arms
- **Select:** sample `θ ~ Beta(α, β)`, pick `argmax`
- **Human reward:** rating ≥ 4 → `α += 1`; ≤ 2 → `β += 1`; 3 → no-op
- **Secondary reward:** automated critic score applies a fractional update
  (`critic_reward_weight`, default 0.3) so the bandit is not blind before feedback

---

## Quick start

### Prerequisites

- Docker + Docker Compose, **or** local Postgres 16 + Redis 7 + Python 3.12
- `CURSOR_API_KEY` and/or `GEMINI_API_KEY` in `.env`

### With Docker Compose

```bash
cp .env.example .env   # then set API keys
docker compose up --build
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

### Local (without Docker for the app)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Ensure Postgres DB exists, e.g.:
# createdb content_pipeline

# Terminal 1 — API
uvicorn app.main:app --reload --port 8000

# Terminal 2 — worker
arq app.worker.tasks.WorkerSettings
```

---

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/content/generate` | Enqueue generation (`brief`, `platform`) |
| `GET` | `/content/{job_id}` | Job status, versions, final content |
| `WS` | `/content/{job_id}/stream` | Status + draft events |
| `POST` | `/content/{job_id}/feedback` | Rating 1–5 → bandit update |
| `GET` | `/bandit/stats` | α/β (and mean) per arm |
| `GET` | `/health` | Liveness |

`platform` values: `linkedin`, `twitter`, `medium`, `youtube_script`, `newsletter`, `instagram`, `threads`.

Example:

```bash
curl -s -X POST http://localhost:8000/content/generate \
  -H 'Content-Type: application/json' \
  -d '{"brief":"Write about shipping faster with CI","platform":"linkedin"}'
```

---

## Streamlit UI

```bash
source .venv/bin/activate
pip install streamlit pandas   # if not already installed
streamlit run frontend/streamlit_app.py
```

Opens a simple UI for generate → poll → feedback and `/bandit/stats`.
Default API URL: `http://127.0.0.1:8000` (changeable in the sidebar).

---

## Tests

Tests mock the LLM — **no real Gemini/Cursor calls in CI**.

```bash
pip install -r requirements.txt
pytest -q
```

Coverage includes:

- Seeded-RNG bandit unit tests (determinism, preference for high-α arms, reward updates)
- Evaluator local metrics (Flesch, n-gram repetition, platform length caps)
- Orchestrator with `FakeLLMClient`
- API flow: generate → poll → feedback → `/bandit/stats` (21 arms)

---

## Project layout

```
app/
  api/           # FastAPI routers
  bandit/        # Thompson Sampling (~150 lines)
  db/            # SQLAlchemy models + async session
  llm/           # Cursor + Gemini clients + FakeLLMClient
  orchestrator/  # Pipeline state machine + evaluator + prompts
  platforms.py   # Platform presets (caps, tone, CTA, format)
  services/      # Bandit persistence + Redis event hub
  worker/        # Arq tasks
frontend/
  streamlit_app.py
tests/
```

---

## What I'd add at scale (future work)

Honest stretch, not built here:

- Multi-platform campaign packs (one brief → LinkedIn + thread + Medium)
- Multi-dimensional arms (`temperature`, `revision_rounds`) or LinUCB
- PPO/DPO / preference training offline (separate from online bandit)
- Vector DB / RAG for brand voice and prior examples
- Dedicated RL / ranking microservice
- Offline batch retraining + shadow evaluation
- Token-level WebSocket streaming (today: status + full draft events)

---

## Interview talking points

- Scoped to **pipeline-level** decisions, not token-level RL — deliberate given LLM rollout cost.
- Thompson Sampling explores naturally and decays exploration as posteriors concentrate (vs ε-greedy).
- Critic mixes **LLM rubric** with **free local signals** (Flesch, n-gram overlap, platform length).
- Worker and API are separate processes; progress streams via **Redis pub/sub**.

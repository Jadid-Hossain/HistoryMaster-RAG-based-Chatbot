# History Master — AI Chatbot on the History of Bangladesh (RAG)

A production-style **RAG (Retrieval-Augmented Generation) chatbot** that answers questions
**strictly from a custom knowledge base** (your PDF / documents), politely refuses anything
outside it, and shows **sources + match scores** for every answer.

> Final Project 1 — "AI-powered chatbot with knowledge handling capabilities"
> Built with **FastAPI + LangChain + ChromaDB + Google Gemini** on the backend and
> **React (Vite)** on the frontend.

---

## ✨ How it works (the RAG pipeline)

```
                         ┌────────────────────────── Backend (FastAPI) ─────────────────────────┐
 PDF / DOCX / TXT /      │                                                                       │
 MD / HTML / URL   ───►  │  LangChain Loaders ──► RecursiveCharacterTextSplitter ──► Embeddings  │
     (admin uploads)     │                                                            │          │
                         │                                                            ▼          │
                         │                                              ┌────────────────────┐   │
 user question  ───────► │  memory rewrite ──► similarity search ─────► │  CHROMA VECTOR DB  │   │
                         │  (short-term)       (cosine, top-k)          │  (persistent)      │   │
                         │                                              └────────────────────┘   │
                         │                                                            │          │
                         │              grounded prompt (context only)  ◄─────────────┘          │
                         │                        │                                              │
                         │                        ▼                                              │
                         │              Gemini LLM (API key)  ──► answer + sources + score       │
                         │                        │                                              │
                         │         NOT_IN_KB ──►  polite fallback message                        │
                         └───────────────────────────────────────────────────────────────────────┘
```

**Why it can't hallucinate:** the LLM receives *only* the retrieved knowledge-base chunks and is
instructed to reply `NOT_IN_KB` when the context lacks the answer — that reply is converted to a
graceful "not found in knowledge base" message. A similarity floor rejects unrelated questions
before the LLM is even called. **Ask anything outside your PDF → the bot honestly says it
doesn't know.**

---

## 📋 Requirements checklist (faculty mapping)

### Core requirements (must have)

| # | Requirement | Where |
|---|-------------|-------|
| 1 | Trainable on a custom, medium-size knowledge base | Drop your PDF into `backend/knowledge_base/` → `python scripts/seed_kb.py --reset` (or upload from the Admin Panel). LangChain splits it into chunks and embeds them into Chroma |
| 2 | Responds accurately **using only** the knowledge base | `app/services/rag.py` — grounded prompt + `NOT_IN_KB` contract |
| 3 | Graceful handling of out-of-scope questions | `app/services/chatbot.py::_fallback` — polite "not found in my knowledge base" + rephrasing suggestion |

### Additional features (good to have)

| # | Feature | Where |
|---|---------|-------|
| 1 | Intelligent knowledge retrieval | Chroma cosine similarity search + Gemini answer generation with source citations (`sources[]` in every response) |
| 2 | Conversation memory (short-term) | `app/services/memory.py` — follow-ups like *"Where is his office?"* are rewritten into standalone queries using the last turns |
| 3 | Multiple data formats | PDF, TXT, MD, DOCX, HTML + **web page URLs** (LangChain loaders) |
| 4 | KB updates without full retraining | New documents are chunk-embedded **incrementally** — upload a doc and ask about it immediately; deletion removes exactly its vectors |
| 5 | Authentication (users/admins) | JWT auth (`app/security.py`) — PBKDF2 password hashing, `admin` role gates KB management |
| 6 | API documentation | Auto-generated **Swagger UI** at `/docs` and ReDoc at `/redoc` |
| 7 | Logger for backend | Rotating file logger → `backend/logs/app.log` + every request/question/answer logged |

### System requirements (must have)

| # | Requirement | Where |
|---|-------------|-------|
| 1 | Complete frontend chat interface | React + Vite app (`frontend/`) — login, chat with sources, admin panel |
| 2 | Backend for queries / KB / responses | FastAPI (`backend/app/`) |
| 3 | Clean API-based architecture | Frontend ⇄ REST ⇄ backend, OpenAPI documented |
| 4 | Maintained on GitHub | Commit history + GitHub Actions CI (`.github/workflows/tests.yml`) |

---

## 🚀 Quick start

### 0. Prerequisites
- Python 3.11+ and Node 18+
- A (free) Google Gemini API key → https://aistudio.google.com/apikey

### 1. Configure the LLM key

`.env` at the project root:

```env
GEMINI_API_KEY=AIza...your_key_here
```

### 2. Backend setup (first time)

```bash
cd backend
python -m venv ../venv                      # (skip if venv/ already exists)
../venv/Scripts/activate                    # Windows Git Bash; on cmd: ..\venv\Scripts\activate.bat
pip install -r requirements.txt

python scripts/download_models.py           # one-time: local embedding model (~90 MB)
python scripts/check_setup.py               # ✅ verifies key + models + DB + a live LLM call
```

### 3. Load YOUR knowledge base

```bash
# drop your PDF into backend/knowledge_base/ then:
python scripts/seed_kb.py --reset           # wipes any old knowledge, loads ONLY your file(s)

# or point at any file directly:
python scripts/seed_kb.py --reset "C:\path\to\my_document.pdf"
```

(Admins can also upload/delete documents live from the web Admin Panel — updates are
instant, no retraining.)

### 4. Run

**One-click demo (Windows):** double-click **`run_demo.bat`** — builds the frontend, starts the
backend, and opens **http://localhost:8000**.

Manual:

```bash
# terminal 1 - backend (serves the built frontend too)
cd backend && ../venv/Scripts/python -m uvicorn app.main:app --port 8000

# terminal 2 - frontend dev mode (optional; hot reload)
cd frontend && npm install && npm run dev    # http://localhost:5173
```

- **Chat UI:** http://localhost:8000 (production build) or http://localhost:5173 (dev)
- **API docs (Swagger):** http://localhost:8000/docs
- **Demo accounts:** `admin / admin123` (admin) · `user / user123` (regular user)

### 5. Frontend production build

```bash
cd frontend && npm install && npm run build   # -> frontend/dist, served by FastAPI automatically
```

---

## 🎤 Live demo flow (details in [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md))

1. **Login** as `user/user123` — auth required.
2. Ask a fact **from your PDF** → correct answer with **📚 Sources + match %**.
3. Ask a follow-up (*"tell me more about that"*) → short-term **memory** resolves it.
4. Ask something **not in the PDF** (*"Who will win the World Cup?"*) → polite **fallback**, no hallucination.
5. **Admin live update:** upload a new file → ask about it **immediately** — no retraining.
6. Show **/docs** (Swagger) and **backend/logs/app.log**.

---

## 🧪 Tests

```bash
cd backend
python -m pytest    # hermetic: fake LLM, isolated temp DB, real Chroma + embeddings
```

Covers auth & roles, KB upload/delete/URL-ingest, incremental updates, grounded answers,
LLM-refusal → fallback, API-error → graceful message, session memory, ownership rules, and
API health. GitHub Actions runs the same suite on every push.

---

## 🗂 Project structure

```
History Master/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, lifespan, static frontend mount
│   │   ├── config.py             # .env config (LLM keys, RAG knobs)
│   │   ├── database.py           # SQLite: users, sessions, messages, doc registry
│   │   ├── security.py           # JWT + PBKDF2 + role dependencies
│   │   ├── logger.py             # rotating file logger + request middleware
│   │   ├── routers/              # auth.py, chat.py, kb.py
│   │   └── services/
│   │       ├── llm.py            # Gemini/OpenAI/Groq/… provider abstraction
│   │       ├── embeddings.py     # local MiniLM (or Gemini) embeddings
│   │       ├── vectorstore.py    # Chroma persistent vector DB
│   │       ├── ingest.py         # LangChain loaders → splitter → vector DB
│   │       ├── rag.py            # grounded prompt + NOT_IN_KB contract
│   │       ├── memory.py         # short-term conversation memory
│   │       └── chatbot.py        # pipeline orchestrator + fallback
│   ├── knowledge_base/           # ← put YOUR PDF(s) here, then run seed_kb.py
│   ├── scripts/                  # seed_kb, check_setup, download_models, eval_chat
│   ├── tests/                    # pytest suite (hermetic)
│   └── data/                     # runtime: SQLite DB, Chroma store, uploads (git-ignored)
├── frontend/
│   └── src/                      # React: Login, Chat, Admin pages + dark UI
├── docs/                         # DEMO_GUIDE.md
├── .env                          # ← your API key (git-ignored)
├── .env.example
├── run_demo.bat                  # one-click demo launcher (Windows)
└── .github/workflows/tests.yml   # CI
```

## 🔧 Configuration knobs (`.env`)

| Variable | Default | Meaning |
|----------|---------|---------|
| `GEMINI_API_KEY` | — | LLM API key (or `OPENAI_API_KEY` / `GROQ_API_KEY` / …) |
| `LLM_PROVIDER` | `auto` | `auto` picks the first key present; or force `gemini` / `openai` / `groq` / `deepseek` |
| `LLM_MODEL` | `gemini-flash-lite-latest` | e.g. `gemini-3.8-flash` (smarter, but free tier = 20 req/day), `gemini-3.5-flash-lite` |
| `EMBEDDINGS_PROVIDER` | `local` | `local` (offline MiniLM) or `gemini` (API embeddings) |
| `RETRIEVAL_TOP_K` / `RETRIEVAL_FLOOR` | 5 / 0.15 | chunks fetched / cheap pre-filter floor (precise guard is the LLM `NOT_IN_KB` contract) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 1000 / 150 | splitter settings |


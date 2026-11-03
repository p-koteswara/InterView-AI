# InterView AI

**InterView AI** is an intelligent, autonomous candidate screening and technical interview platform designed to simulate structured, role-specific technical evaluations.

The platform combines automated resume intelligence, Retrieval-Augmented Generation (RAG) anchored in authoritative technical literature, adaptive multi-turn questioning, and objective scoring into a seamless pair of decoupled applications.

---

## Architecture Overview

InterView AI is architected as two independent applications communicating via RESTful APIs:

```
┌──────────────────────────────────────┐          REST / HTTP          ┌──────────────────────────────────────┐
│        Frontend (Next.js 15)         │ ────────────────────────────> │          Backend (FastAPI)           │
│   TypeScript + Tailwind CSS UI       │                               │   Async Python REST API Service      │
└──────────────────────────────────────┘                               └──────────────────┬───────────────────┘
                                                                                          │
                                                                       ┌──────────────────▼───────────────────┐
                                                                       │       Database & Persistence         │
                                                                       │       SQLite via SQLAlchemy          │
                                                                       └──────────────────────────────────────┘
```

### Repository Structure

```
InterView AI/
├── backend/                        # FastAPI REST API backend application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI application factory, CORS, lifespan & error handlers
│   │   ├── api/                    # Route controllers
│   │   │   ├── __init__.py
│   │   │   └── health.py           # GET /api/health endpoint
│   │   ├── core/                   # Application configuration & logging
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # Pydantic Settings & environment variables
│   │   │   └── logging.py          # Unified log formatting
│   │   ├── database/               # Database connectivity & session handling
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # SQLAlchemy DeclarativeBase
│   │   │   └── session.py          # Engine, SessionLocal, and get_db dependency
│   │   ├── models/                 # SQLAlchemy ORM models (sessions, questions, answers, reports)
│   │   │   └── __init__.py
│   │   ├── schemas/                # Pydantic request/response validation schemas
│   │   │   ├── __init__.py
│   │   │   └── health.py           # Health check response model
│   │   └── services/               # Core business logic (resume parsing, RAG pipeline, LLM client)
│   │       └── __init__.py
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Template for backend environment variables
│   └── .env                        # Local runtime environment settings
├── frontend/                       # Next.js App Router client application
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx          # Root HTML layout & metadata
│   │   │   ├── page.tsx            # Main dashboard & live connectivity monitor
│   │   │   └── globals.css         # Tailwind CSS stylesheet
│   │   ├── components/
│   │   │   └── backend-status.tsx  # Interactive real-time backend health widget
│   │   └── lib/
│   │       └── api.ts              # Type-safe API client & fetch wrappers
│   ├── package.json                # Frontend dependencies and scripts
│   ├── tsconfig.json               # TypeScript compiler configuration
│   ├── tailwind.config.ts          # Tailwind CSS theme configuration
│   ├── postcss.config.mjs          # PostCSS configuration
│   ├── next.config.ts              # Next.js runtime configuration
│   ├── .env.example                # Template for frontend environment variables
│   └── .env.local                  # Local frontend environment settings
├── knowledge_base/                 # Reference textbooks & corpora for RAG grounding
│   └── README.md
├── .gitignore                      # Git ignore patterns
└── README.md                       # Project documentation
```

---

## Getting Started

### Prerequisites

- **Python**: 3.11 or newer (tested with Python 3.14)
- **Node.js**: 20.x or newer (tested with Node.js 24)
- **Package Manager**: npm

---

### 1. Backend Setup

1. Open a terminal in the project root:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Default values connect to `sqlite:///./interview_ai.db` and permit requests from `http://localhost:3000`.

5. Start the backend development server:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

6. Verify the backend:
   - **Health Endpoint**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
   - **Interactive API Docs (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - **Expected Health Response**:
     ```json
     {
       "status": "ok",
       "service": "InterView AI",
       "database": "connected"
     }
     ```

---

### 2. Frontend Setup

1. Open a second terminal in the project root:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Configure environment variables:
   - Copy `.env.example` to `.env.local`:
     ```bash
     cp .env.example .env.local
     ```
   - Ensure `NEXT_PUBLIC_API_BASE_URL` points to `http://127.0.0.1:8000`.

4. Start the frontend development server:
   ```bash
   npm run dev
   ```

5. Access the application:
   - Open [http://localhost:3000](http://localhost:3000) in your browser.
   - The dashboard automatically pings the backend service and displays live operational status for the API and SQLite database.
   - Click **Check Status** to trigger live status queries on demand.

---

## Incremental Roadmap

- [x] **Step 1: Project Foundation**
  - Modular FastAPI backend with SQLite + SQLAlchemy engine
  - Next.js 15 App Router frontend with Tailwind CSS
  - Verified REST communication via `GET /api/health`
  - Environment-based configuration, CORS middleware, and zero hardcoded credentials
- [ ] **Step 2: Resume Intelligence**
  - PyMuPDF text & structure extractor for PDF & TXT documents
  - Information extraction for technical skills, frameworks, and domain expertise
- [ ] **Step 3: RAG Knowledge Base Ingestion**
  - Document chunking strategy preserving technical context
  - ChromaDB vector store integration with semantic embeddings
  - Verified reference material indexing
- [ ] **Step 4: Dynamic Interview Engine**
  - Context construction aligning candidate background with target job roles
  - Role-grounded question generation via Gemini LLM
  - Adaptive difficulty and session continuity
- [ ] **Step 5: Assessment & Comprehensive Analytics**
  - Answer evaluation with detailed rubric scoring
  - Final candidate reporting highlighting strengths and growth areas

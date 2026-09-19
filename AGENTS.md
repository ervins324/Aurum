# AGENTS.md

## Core Operating Principles
1. **Preserve Comments**: Never delete existing comments. You may update comments to make them more relevant, but do not delete them and leave the code uncommented.
2. **Atomic & Scalable Changes**: Write atomic, modular code. Changes in one place must never break unrelated features. Structure code cleanly for easy maintenance and future updates.
3. **Concise Commits**: Create simple, concise commit messages. Never mention AI models, Claude, or conversation session links.
4. **Mobile-First UI**: Always ensure responsiveness on mobile viewports from the beginning using Tailwind breakpoints (`sm:`, `md:`, `lg:`).
5. **Zero Sensitive Data**: The codebase must contain no sensitive data (e.g., confidential information, real passwords, usernames, expense or income records). All confidential information must be stored ONLY locally on the user's PC and must never end up in a remote repository or the project's source code.
6. **Language**: Always reply to me in English.
7. **Fork & Migration Integrity**: Keep custom features modular (standalone services/utilities) to minimize merge conflicts when rebasing on `upstream/main`. Never introduce broken or diverging Alembic migration chains.

---

## Repository Structure & Architecture

```text
Aurum/
├── backend/
│   ├── alembic/              # Database migration scripts (linear revision history)
│   ├── app/
│   │   ├── api/routes/       # FastAPI route controllers (thin routing layer)
│   │   ├── core/             # Encryption, audit logging, config, utilities
│   │   ├── models/           # SQLAlchemy 2.0 ORM models
│   │   ├── schemas/          # Pydantic v2 validation & serialization schemas
│   │   └── services/         # Business logic, aggregations, external clients
│   └── tests/                # Pytest integration suite (runs against Postgres)
├── frontend/
│   └── src/
│       ├── api/              # HTTP client and backend endpoint callers
│       ├── components/       # Feature-specific & reusable UI components
│       ├── hooks/            # Custom React hooks & TanStack query wrappers
│       ├── lib/              # Formatting, i18n dictionary, utilities
│       └── pages/            # Top-level route pages (Dashboard, Accounts, etc.)
└── docker-compose.yml        # Multi-service stack (db, backend, web)
```

---

## Build, Lint & Test Commands

### Backend (Docker Compose Environment)
Backend tests run against an isolated Postgres test database (`aurum_test`) inside the container.

- **Start Stack**: `docker compose up -d`
- **Install Test Dependencies** (run once per container lifetime):
  ```bash
  docker compose exec backend pip install --user -r requirements-dev.txt
  ```
- **Run All Tests**:
  ```bash
  docker compose exec backend python -m pytest -v -p no:cacheprovider
  ```
- **Run a Single Test File**:
  ```bash
  docker compose exec backend python -m pytest tests/test_transactions.py -v -p no:cacheprovider
  ```
- **Run a Single Test by Name**:
  ```bash
  docker compose exec backend python -m pytest tests/test_transactions.py -k "test_create_transaction" -v -p no:cacheprovider
  ```
- **Database Migrations (Alembic)**:
  ```bash
  docker compose exec backend alembic upgrade head
  docker compose exec backend alembic revision --autogenerate -m "description"
  ```
  *Note: Always ensure a single head with `alembic heads`. Never branch heads.*

### Frontend (in `frontend/` directory)
- **Install Dependencies**: `npm ci`
- **Development Server**: `npm run dev`
- **Typecheck / Lint**: `npm run lint` (`tsc -b --noEmit`)
- **Production Build**: `npm run build` (`tsc -b && vite build`)
- **Run All Tests**: `npm test` (`vitest run`)
- **Run a Single Test File**:
  ```bash
  npx vitest run src/lib/format.test.ts
  ```
- **Run a Single Test by Name**:
  ```bash
  npx vitest run src/lib/format.test.ts -t "formats UAH"
  ```

---

## Code Style & Conventions

### Python / FastAPI Backend
- **Python Version**: Python 3.12+.
- **Imports**: Group imports cleanly in standard order:
  1. Standard library (`datetime`, `decimal`, `typing`)
  2. Third-party packages (`fastapi`, `sqlalchemy`, `pydantic`, `httpx`)
  3. Internal application modules (`from app.api.deps import ...`, `from app.models...`)
- **Type Annotations**:
  - Use modern builtins: `list[str]`, `dict[str, Any]`, `int | None` (avoid `typing.Optional`, `typing.List`).
  - Strict type hints on all function parameters and return types.
- **SQLAlchemy 2.0 ORM**:
  - Use `Mapped[...]` and `mapped_column(...)`.
  - Always specify foreign key ondelete behaviors (`CASCADE` or `SET NULL`).
  - Use `selectinload` for eager loading relationships in async queries to avoid N+1 queries.
- **Monetary & Financial Accuracy**: Always use `Decimal` in Python and `Numeric(14, 2)` in PostgreSQL for money. Never use floating-point `float` for currency calculations.
- **Error Handling**:
  - Raise `HTTPException(status_code=..., detail="...")` for client-facing validation errors.
  - Log server errors with contextual info using `logger.error("Context: %s", err, exc_info=True)`.
  - Never swallow exceptions silently.
- **Testing Guidelines**:
  - Use the `client` fixture (`httpx.AsyncClient`) to hit endpoints like the frontend.
  - Rely on `account_id` and `categories` fixtures; database cleans state between tests.

### TypeScript / React Frontend
- **Framework**: React 19 with functional components, hooks, and Vite 6.
- **Imports**:
  - Use `@/` path alias for `src/` (e.g., `@/components/...`, `@/lib/...`, `@/types/...`).
- **State Management**:
  - TanStack React Query (`useQuery`, `useMutation`) for server state and API interactions.
  - Invalidate queries via `queryClient.invalidateQueries({ queryKey: [...] })` after mutations.
- **Styling**:
  - Tailwind CSS v4 utility classes.
  - Use `cn(...)` from `@/lib/utils` (combines `clsx` and `tailwind-merge`) for dynamic class concatenation.
  - Every UI component must be mobile-responsive (`w-full sm:w-auto`, flex wraps, stack on mobile).
- **Internationalization & Formatting**:
  - Do not hardcode user-facing strings; use `t("key")` from `@/lib/i18n`.
  - Format monetary figures through `formatMoney` in `@/lib/format`.
- **Typing**:
  - All interfaces and types in `frontend/src/types/index.ts` matching backend schemas.
  - Avoid `any`. Use explicit interfaces or type unions.

---

## Bank & Card Parsing Rules (Monobank & Bybit)

### Monobank Statement Parsing (`app/services/monobank_client.py`)
- **Units**: Monobank amounts are in kopecks/cents; always divide by 100 (`Decimal(amount) / 100`).
- **ISO Currency Codes**: Map integer codes (`980` -> UAH, `840` -> USD, `978` -> EUR).
- **Direction**: Negative amount represents an `EXPENSE`, positive represents `INCOME`.
- **Deduplication**: Store external ID as `external_id = f"mono_{item.id}"`.
- **MCC Auto-Categorization**: Map merchant category codes with `resolve_category_by_mcc(session, item.mcc)`.
- **Chunking**: Adhere to Monobank's 30-day statement limit per call using `get_extended_statement`.

### Bybit Card Transaction Parsing (`app/services/bybit_client.py`)
- **API & Rate Limits**: POST to `/v5/card/transaction/query-asset-records` with HMAC-SHA256 signature; back off on 429 or codes `10006`/`10014`.
- **Dual Amounts & Currency Conversion**:
  - `transactionAmount` & `transactionCurrency`: terminal charge (e.g., UAH paid amount at local terminals).
  - `basicAmount` & `basicCurrency`: funding deduction from Bybit wallet (usually USDT).
  - If charged in UAH (`transactionCurrency == "UAH"`), record the exact UAH paid amount.
  - If charged in USD/USDT/EUR, convert to UAH via exchange rate (NBU / Monobank rate) and store original currency & amount in `notes`.
- **Transaction Types & Status**:
  - Skip failed or declined operations (`item.is_failed` / `status == "2"`).
  - Refunds / chargebacks (`is_refund` / `side in ("4", "5", "8", "10", "11")`) map to `TransactionType.INCOME`.
- **Timestamps & Deduplication**: Convert millisecond timestamps (`item.time / 1000`); use `external_id = f"bybit_{item.id}"`.

---

## Fork Synchronization & Git Workflow
- Fetch and rebase on upstream changes:
  ```bash
  git fetch upstream
  git rebase upstream/main
  ```
- Commit messages: Follow conventional format (e.g. `feat: add bybit card sync`, `fix: linearize migration head`).
- Keep all secrets in `.env` (never committed). Secrets stored in DB must use `app.core.encryption`.
# AQUA∞ FastAPI API

## Local development

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

The API creates `aqua.db` in the current directory at startup. Browse
http://localhost:8000/docs or check http://localhost:8000/health.

Run the API test suite with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

`DATABASE_URL` and `CORS_ORIGINS` are configurable in `.env`. The optional
coach provider reads `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL`
only on the backend. Without a configured key, it returns an explicitly
identified, context-based guided fallback.

## API

- `GET /health`
- `GET, PUT /api/v1/profile`
- `GET, POST /api/v1/entries`
- `PATCH, DELETE /api/v1/entries/{entry_id}`
- `GET /api/v1/dashboard`
- `GET /api/v1/analytics/weekly`
- `GET, POST /api/v1/reminders`
- `PUT, DELETE /api/v1/reminders/{reminder_id}`
- `POST /api/v1/coach`

Times are stored/aggregated in UTC. Naive intake timestamps are interpreted as
UTC. Reminder records hold local `HH:MM` wall-clock values; clients are
responsible for scheduling them in their local timezone.

## Security status

Authentication and authorization are not implemented. `user_id` is an
untrusted development partition parameter, not authentication. Requests can
choose another ID. Do not expose this service to the public or use real user
data until authenticated identity is derived server-side and authorization is
enforced. CORS is not an access-control mechanism.

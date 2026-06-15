# FileDrop

## Why this stack

Each component earns its place from a single property: this is a read-heavy, multi-user, public distribution workload.

| Component | Why it's here |
|-----------|--------------|
| **3× FastAPI instances** | Handle concurrent users; no single point of failure |
| **MinIO** | Shared object storage — files uploaded via app1 are instantly downloadable via app2 or app3. This is what makes the instances stateless and interchangeable |
| **HAProxy** | Distributes requests evenly across the stateless instances |
| **Redis** | Caches file metadata so repeated downloads skip the database entirely |
| **Nginx** | Rate limits uploads, handles large file streaming, acts as the single public entry point |
| **Prometheus + Grafana** | Per-instance request rates and HAProxy health, visible in real time |

## Prerequisites

- Docker
- Docker Compose

## Quick start

```bash
git clone https://github.com/gavishka-sahan/filedrop.git
cd filedrop
cp .env.example .env
# Edit .env with your own credentials
docker compose up -d
```

Grafana dashboard loads automatically on first start via provisioning — no manual setup needed.

## Service ports

| Service    | Port | Purpose |
|------------|------|---------|
| Nginx      | 80   | Public entry point |
| HAProxy    | 8404 | Stats page |
| MinIO API  | 9000 | Object storage API |
| MinIO UI   | 9001 | MinIO web console |
| Prometheus | 9090 | Metrics |
| Grafana    | 3000 | Dashboards (admin / see .env) |
| PostgreSQL | 5432 | Database |
| Redis      | 6379 | Cache |

## API

Upload a file:

```bash
curl -X POST http://localhost/upload -F "file=@yourfile.txt"
# {"file_id": "...", "filename": "...", "download_url": "..."}
```

Download a file (redirects to a MinIO presigned URL):

```bash
curl -L http://localhost/files/<file_id> -o output.txt
```

Health check:

```bash
curl http://localhost/health
```

## How it was built — phase by phase

| Phase | What was added | The point |
|-------|---------------|-----------|
| 0 | Single FastAPI container, `/health` route | Confirm the baseline runs |
| 1 | PostgreSQL, upload/download with local disk storage | End-to-end flow working |
| 2 | HAProxy + 3 app instances | Hit the wall: a file uploaded to instance A is invisible on instance B |
| 3 | MinIO shared object storage | The keystone fix — instances become truly stateless |
| 4 | Redis metadata cache | Skip Postgres on every repeated download |
| 5 | Nginx reverse proxy | Rate limiting, large upload streaming |
| 6 | Prometheus + Grafana | Observability — see the system working in real time |
| 7 | Stress testing, failover, presigned URLs | Validate everything under real load |

## Key design decisions

**Presigned URL downloads** — the `/files/<id>` endpoint redirects the client directly to MinIO rather than proxying the bytes through FastAPI. This means the app tier is not involved in the actual file transfer at all — MinIO serves it directly. The result is dramatically lower latency and much higher download throughput at no extra infrastructure cost.

**Stateless app tier** — no instance holds any local state. Files live in MinIO, metadata lives in PostgreSQL (with Redis in front), sessions are not used. Any instance can handle any request, which means HAProxy can route freely and instances can be added, removed, or replaced without affecting users.

**Cache-aside pattern** — Redis does not receive writes on upload. Instead, it is populated lazily: on the first download of a file, the metadata is fetched from Postgres and written to Redis. Every subsequent download hits Redis and skips Postgres entirely until the TTL expires.

## Notes

- `.env` is gitignored — copy `.env.example` and set your own values before running
- TLS is not configured here — add it at the Nginx layer with Certbot when deploying with a real domain
- The Grafana dashboard is provisioned automatically from `grafana/dashboards/`
- MinIO credentials in `.env.example` are placeholders — change them before any internet-facing deployment

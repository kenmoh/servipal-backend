# servipal-backend

Backend service for Servipal.

## Development
Render for testing

The project uses `uv` for dependency management.

```bash
uv sync
uv run fastapi dev
```

### Gradual queue migration (Supabase queue + Celery/RabbitMQ)

The existing Supabase queue stays available.
You can select queue backend behavior with:

- `PAYMENT_QUEUE_BACKEND=celery` (default)
- `PAYMENT_QUEUE_BACKEND=dual` (enqueue to Supabase and Celery)
- `PAYMENT_QUEUE_BACKEND=supabase` (existing queue-only fallback)

Run production-style standalone Celery + RabbitMQ stack:

```bash
docker compose -f compose.celery.yaml up -d --build
```

Required environment values for Celery mode:

- `CELERY_ENABLED=true`
- `CELERY_BROKER_URL=amqp://<user>:<password>@rabbitmq:5672/<vhost>`
- `CELERY_RESULT_BACKEND=rpc://`
- `RABBITMQ_DEFAULT_USER=<user>`
- `RABBITMQ_DEFAULT_PASS=<strong-password>`
- `RABBITMQ_DEFAULT_VHOST=<vhost>`
- `RABBITMQ_ERLANG_COOKIE=<long-random-secret>`

RabbitMQ dashboard online access:

- RabbitMQ management UI is host-local by default: `RABBITMQ_MANAGEMENT_BIND_IP=127.0.0.1`.
- Online access is served via `rabbitmq-dashboard-proxy` (Nginx) on `443`.
- Dashboard URL: `https://<server-or-domain>:<RABBITMQ_PROXY_HTTPS_PORT>`
- Reverse proxy auth uses Basic Auth file at `deploy/rabbitmq-proxy/auth/.htpasswd`.
- TLS cert files must exist at:
  - `deploy/rabbitmq-proxy/certs/fullchain.pem`
  - `deploy/rabbitmq-proxy/certs/privkey.pem`
- Inbound network policy recommendation:
  - restrict `15672` to localhost/private network only
  - allow `443` only from trusted IPs (or place behind your identity-aware gateway)

Generate a basic-auth file:

```bash
htpasswd -c ./deploy/rabbitmq-proxy/auth/.htpasswd admin
```

Webhook to retry flow:

1. Flutterwave webhook hits `/api/v1/payments/webhook`.
2. Signature is validated.
3. Tx ref idempotency is checked before enqueue.
4. Dispatcher enqueues to backend(s) based on `PAYMENT_QUEUE_BACKEND`.
5. Celery worker executes existing payment handlers via `app.common.order.process_payment`.
6. Worker uses exponential retry backoff for retryable failures and skips duplicate/already-processed events.

### Removing Supabase queue support later (optional)

When you are fully confident in Celery/RabbitMQ, remove Supabase queue support with this checklist:

1. Set `PAYMENT_QUEUE_BACKEND=celery` in all environments.
2. Remove Supabase enqueue branch in `app/services/payment_queue_dispatcher.py` (`_enqueue_supabase_payment_queue` and `supabase` / `dual` branches).
3. Remove Supabase queue consumer route file `app/routes/order_create.py`.
4. Remove `order_create` router registration from `app/main.py`.
5. Remove Supabase-queue specific tests in `tests/test_payment_queue_dispatcher.py` that assert `supabase_msg_id` behavior.

Keep `app/common/order.py` and `app/services/payment_service.py` — they are part of the Celery worker processing path.

## Deployment

The application is configured for deployment on Google Cloud Run.

### Prerequisites

- Google Cloud SDK (`gcloud`) installed and authenticated.
- A Google Cloud Project.

### Deploy with Cloud Build

You can deploy using Google Cloud Build which builds the container and deploys it to Cloud Run.

```bash
gcloud builds submit --config cloudbuild.yaml .
```

Alternatively, you can build and deploy manually:

```bash
# Build
docker build -t gcr.io/[PROJECT_ID]/servipal-backend .

# Push
docker push gcr.io/[PROJECT_ID]/servipal-backend

# Deploy
gcloud run deploy servipal-backend --image gcr.io/[PROJECT_ID]/servipal-backend --platform managed
```

# ServiPal Fraud Detection (Rules-Based v1)

This backend includes a rules-based risk engine and fraud logging layer that evaluates critical actions and can `allow`, `review`, or `block` the action.

## Response Shape

Every evaluation returns:

```json
{
  "risk_score": 0,
  "risk_level": "low",
  "action": "allow",
  "reasons": ["string"],
  "signals": { "optional_debug_key": "value" }
}
```

## Critical Integration Points

The fraud engine is enforced at:

1. Payment initiation (before creating `transaction_intents`):
   - Delivery
   - Food
   - Laundry
   - Product
   - Reservation (booking create)
2. Payment confirmation (after provider verification, before fulfilling the order)
3. Service completion:
   - Delivery completion can hold payout when action is `review` (completion still occurs)
4. Payout requests:
   - Wallet withdrawals
   - Vendor payout transfers
   - Escrow fund release

## Admin Review API

Routes:

- `GET /api/v1/admin/fraud/logs`
- `POST /api/v1/admin/fraud/logs/{log_id}/review` with `{ "decision": "APPROVED" | "REJECTED", "notes": "..." }`

## Database Table (Supabase)

The fraud module writes to `fraud_logs`.

Suggested table (Postgres):

```sql
create table if not exists public.fraud_logs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),

  event text not null,
  user_id uuid null,
  vendor_id uuid null,
  transaction_id uuid null,
  order_id uuid null,
  order_type text null,
  tx_ref text null,
  amount numeric null,

  risk_score int not null,
  risk_level text not null,
  action text not null,
  reasons jsonb not null default '[]'::jsonb,

  ip_address text null,
  user_agent text null,

  status text not null default 'OPEN',
  reviewed_by uuid null,
  reviewed_at timestamptz null,
  review_notes text null,

  details jsonb null
);
```

Notes:
- Logging is best-effort: failures will not break the primary payment/order flows.
- Use RLS as appropriate; admin routes use the service role client.


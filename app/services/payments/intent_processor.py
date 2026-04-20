from decimal import Decimal

HANDLERS = {}

def register_handler(service_type: str):
    def wrapper(fn):
        HANDLERS[service_type] = fn
        return fn
    return wrapper


async def process_payment_intent(
    tx_ref: str,
    paid_amount: str,
    flw_ref: str,
    payment_method: str,
    supabase,
):
    # 1. Load intent (SOURCE OF TRUTH)
    intent_res = await supabase.table("transaction_intents") \
        .select("*") \
        .eq("tx_ref", tx_ref) \
        .single() \
        .execute()

    if not intent_res.data:
        raise Exception("Intent not found")

    intent = intent_res.data

    # 2. Idempotency
    if intent["status"] == "COMPLETED":
        return {"status": "already_processed"}

    service_type = intent["service_type"]
    payload = intent["payload"]

    # 3. Find handler
    handler = HANDLERS.get(service_type)
    if not handler:
        raise Exception(f"No handler for {service_type}")

    # 4. Execute handler
    result = await handler(
        intent=intent,
        payload=payload,
        paid_amount=Decimal(str(paid_amount)),
        flw_ref=flw_ref,
        payment_method=payment_method,
        supabase=supabase,
    )

    # 5. Mark completed
    await supabase.table("transaction_intents") \
        .update({"status": "COMPLETED"}) \
        .eq("tx_ref", tx_ref) \
        .execute()

    return result
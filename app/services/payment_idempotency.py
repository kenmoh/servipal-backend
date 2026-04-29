from supabase import AsyncClient

from app.config.logging import logger


async def check_payment_already_processed(
    *,
    supabase: AsyncClient,
    tx_ref: str,
) -> tuple[bool, str | None]:
    """
    Check whether this tx_ref has already been finalized in the database.

    Returns:
        (is_processed, source_table)
    """
    probes = (
        ("transaction_intents", "status"),
        ("transactions", "id"),
        ("transfers", "id"),
    )

    for table, column in probes:
        try:
            result = (
                await supabase.table(table)
                .select(column)
                .eq("tx_ref", tx_ref)
                .limit(1)
                .execute()
            )
            row = (result.data or [None])[0]
            if not row:
                continue

            if table == "transaction_intents":
                status = str(row.get("status", "")).upper()
                if status == "COMPLETED":
                    return True, table
                continue

            if row.get(column):
                return True, table
        except Exception as exc:
            logger.warning(
                "payment_idempotency_probe_failed",
                tx_ref=tx_ref,
                table=table,
                error=str(exc),
            )

    return False, None

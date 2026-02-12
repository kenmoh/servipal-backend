# from rq import Queue
# from redis import Redis
# from app.config.config import settings
# # Imports not strictly needed here for queue definition,
# # but must be importable by the RQ worker process.
# from app.services.payment_service import (
#     process_successful_delivery_payment,
#     process_successful_food_payment,
#     # process_successful_laundry_payment
# )


# redis_conn = Redis.from_url(settings.REDIS_URL)
# queue = Queue(connection=redis_conn)


import os
import asyncio
from rq import Queue
from redis import Redis
from rq.job import Job
from app.config.config import settings, redis_client, sync_redis_client


# Default queue
queue = Queue(connection=sync_redis_client)


def run_async_job(func_module, func_name, *args, **kwargs):
    """
    Wrapper to run async functions in a synchronous RQ worker.
    """
    import importlib

    module = importlib.import_module(func_module)
    func = getattr(module, func_name)

    # Get a supabase client (ADMIN)
    from app.database.supabase import create_supabase_admin_client

    async def _run():
        supabase = await create_supabase_admin_client()
        return await func(*args, supabase=supabase, **kwargs)

    return asyncio.run(_run())


# Function to enqueue a job
def enqueue_job(func, *args, **kwargs):
    """
    Enqueues a job. If the function is async, it uses run_async_job wrapper.
    """
    import inspect

    if inspect.iscoroutinefunction(func):
        job = queue.enqueue(
            run_async_job, func.__module__, func.__name__, *args, **kwargs
        )
    else:
        job = queue.enqueue(func, *args, **kwargs)
    return job.id

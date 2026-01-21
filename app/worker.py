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
from rq import Queue
from redis import Redis
from rq.job import Job
from app.config.config import settings, redis_client, sync_redis_client


# Default queue
queue = Queue(connection=sync_redis_client)

# Function to enqueue a job
def enqueue_job(func, *args, **kwargs):
    job = queue.enqueue(func, *args, **kwargs)
    return job.id

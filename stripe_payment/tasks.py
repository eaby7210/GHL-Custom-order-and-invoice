from celery import shared_task
from stripe_payment.management.commands.pull_notary_company import Command as pull_companies
import logging

logger = logging.getLogger(__name__)

@shared_task
def example_task(arg1, arg2):
    # Your task logic here
    return arg1 + arg2

@shared_task
def sample_beat_task():
    # Logic for the periodic task
    logger.info("Sample beat task executed.")
    return "Task completed"

@shared_task
def create_order_task(order_id, user_id):
    pass

@shared_task
def pull_clients():
    p =pull_companies()
    p.handle()


from enum import Enum


class TransactionStaus(str, Enum):
    INITIATED = "INITAITED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    AUTHORIZED = "AUTHORIZED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def transition(transaction, new_status):
    allowed = {
        "INITAITED": ["PAYMENT_PENDING"],
        "PAYMENT_PENDING": ["AUTHORIZED", "FAILED"],
        "AUTHORIZED": ["PAID", "COMPLETED"],
        "PAID": ["IN_PROGRESS"],
        "IN_PROGRESS": ["COMPLETED"],
    }

    if new_status not in allowed.get(transaction.status, []):
        raise Exception("Invalid state transition")
    transaction.status = new_status
    return transaction.status

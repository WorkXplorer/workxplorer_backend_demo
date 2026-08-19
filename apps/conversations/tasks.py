"""Background delivery of chat events to the Go gateway.

Publishing used to happen inline, on the request's own thread, right after the
transaction committed. That is the shortest path to the recipient, but it puts
a network call to another service inside the request/response cycle: the
worker handling the request sits blocked until the gateway answers or the
timeout expires.

On a sync worker pool that cost is not paid by the sender alone. A blocked
worker is a worker serving nobody, so with a small pool a slow gateway becomes
site-wide latency — including on pages that have nothing to do with chat.
Worse, the gateway calls back into the platform to persist a message, so the
two services can end up waiting on each other while the queue behind them
grows.

Delivery therefore runs here, on the queue. Enqueuing costs a Redis round trip
over loopback; whether the gateway is fast, slow or dead stops being something
a request can feel.
"""

import logging

logger = logging.getLogger(__name__)


def deliver_event(user_ids, event: dict) -> None:
    """Push *event* to *user_ids*. Runs on an RQ worker.

    Failures are logged rather than raised. The message is already committed,
    so a failed push costs the recipient a refresh, not a message — and a
    retry would arrive long after it stopped being realtime.
    """
    from apps.conversations import realtime

    realtime.publish(user_ids, event)

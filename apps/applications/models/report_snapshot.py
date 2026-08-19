"""
Stored copies of the daily application report payload.

The report is built fresh every morning, pushed to the Telegram bot and then
forgotten, which leaves the platform unable to answer any question that spans
more than one day. Keeping the payload fixes that, and the distinction worth
knowing is which half of it is recoverable without this table:

* Numbers derived from timestamped rows — applications, signups, per-company
  counts — can be recomputed for any past date by rebuilding the report with
  that ``report_date``. Losing them costs CPU, not information.
* Point-in-time numbers cannot. Churn, the current status backlog, open and
  idle vacancy counts and recruiter last-sign-ins all describe the platform at
  the moment the report ran; nothing records what they were last Tuesday. A day
  that is never snapshotted loses these permanently.

That asymmetry is the whole reason this table exists, and the reason nothing
here prunes old rows: a full payload is roughly 4 KB, so a decade of daily
snapshots is about 16 MB. Deleting them would save nothing worth the loss.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from utils import AbstractBaseModel


class DailyReportSnapshot(AbstractBaseModel):
    """One day's report payload, exactly as it was sent to the bot."""

    # unique already builds the index the date lookups need; adding db_index
    # on top would create a second one for nothing.
    report_date = models.DateField(
        unique=True,
        help_text=_("The local day this report describes."),
    )
    payload = models.JSONField(
        help_text=_(
            "The full report payload as built for the bot. Stored verbatim so "
            "a later reader sees what was actually reported, not what today's "
            "code would compute."
        ),
    )

    class Meta:
        verbose_name = _("Daily report snapshot")
        verbose_name_plural = _("Daily report snapshots")
        ordering = ["-report_date"]

    def __str__(self) -> str:
        return f"Daily report {self.report_date}"

    @classmethod
    def store(cls, payload: dict) -> "DailyReportSnapshot | None":
        """
        Save ``payload`` under its own report date, replacing any earlier copy.

        Re-running a day is a normal thing to do — the scheduled job can be
        retried, and a missed day gets re-sent by hand — so the newer payload
        wins rather than colliding on the unique date.

        Returns ``None`` when the payload carries no usable date: a snapshot
        that cannot be placed on the timeline is worse than no snapshot, and
        this is never worth failing the report over.
        """
        report_date = payload.get("report_date")
        if not report_date:
            return None

        snapshot, _created = cls.objects.update_or_create(
            report_date=report_date, defaults={"payload": payload}
        )
        return snapshot

from django.urls import path
from apps.subscriptions.views import (
    plan_list_view,
    my_subscription_view,
    seat_assignment_list_view,
    assign_seat_view,
    revoke_seat_view,
)


urlpatterns = [
    # Subscription plans
    path("plans/", plan_list_view, name="plan-list"),

    # Current user's subscription
    path("my/", my_subscription_view, name="my-subscription"),

    # Seat management (company admin only)
    path("seats/", seat_assignment_list_view, name="seat-list"),
    path("seats/assign/", assign_seat_view, name="seat-assign"),
    path("seats/revoke/", revoke_seat_view, name="seat-revoke"),
]

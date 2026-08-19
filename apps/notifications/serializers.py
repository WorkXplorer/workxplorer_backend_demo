from rest_framework import serializers


class NotificationListItemSerializer(serializers.Serializer):
    """Schema serializer for a single user notification item."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    message = serializers.CharField()
    created_at = serializers.DateTimeField()
    notification_type = serializers.CharField()
    is_read = serializers.BooleanField()
    read_at = serializers.DateTimeField(allow_null=True)


class NotificationListPayloadSerializer(serializers.Serializer):
    """Schema serializer for the wrapped notification list payload."""

    notifications = NotificationListItemSerializer(many=True)
    unread_count = serializers.IntegerField()


class NotificationListResponseSerializer(serializers.Serializer):
    """Schema serializer for the raw paginated notification response."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = NotificationListPayloadSerializer()

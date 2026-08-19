from rest_framework import serializers


class DeviceSerializer(serializers.Serializer):
    """
    Device metadata attached to every mobile session-creating request.
    NOTE: purely descriptive (session listing, risk signals) — never a
    security boundary. device_id is client-generated and unverifiable.
    """

    device_id = serializers.CharField(max_length=100)
    platform = serializers.ChoiceField(choices=["ios", "android"])
    app_version = serializers.CharField(max_length=20, required=False, allow_blank=True)
    build_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    device_name = serializers.CharField(max_length=100, required=False, allow_blank=True)

from django.test import SimpleTestCase

from drf_spectacular.generators import SchemaGenerator


class NotificationSchemaTests(SimpleTestCase):
    def test_notification_list_schema_includes_notification_payload_shape(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)

        response_schema = schema["paths"]["/api/v1/notifications/"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        data_schema_ref = response_schema["properties"]["data"]["$ref"]
        data_schema = schema["components"]["schemas"][data_schema_ref.split("/")[-1]]
        pagination_schema = response_schema["properties"]["pagination"]

        self.assertEqual(data_schema["type"], "object")
        self.assertIn("notifications", data_schema["properties"])
        self.assertIn("unread_count", data_schema["properties"])
        self.assertEqual(pagination_schema["type"], "object")
        self.assertEqual(pagination_schema["properties"]["next"]["type"], "string")
        self.assertEqual(pagination_schema["properties"]["previous"]["type"], "string")

        notifications_schema = data_schema["properties"]["notifications"]
        self.assertEqual(notifications_schema["type"], "array")

        item_schema_ref = notifications_schema["items"]["$ref"]
        item_schema = schema["components"]["schemas"][item_schema_ref.split("/")[-1]]

        self.assertIn("id", item_schema["properties"])
        self.assertIn("title", item_schema["properties"])
        self.assertIn("message", item_schema["properties"])
        self.assertIn("notification_type", item_schema["properties"])
        self.assertIn("is_read", item_schema["properties"])
        self.assertNotIn("sent_count", item_schema["properties"])
        self.assertNotIn("success_count", item_schema["properties"])
        self.assertNotIn("failure_count", item_schema["properties"])

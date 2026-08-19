from rest_framework import serializers


class RecommendedCompanySerializer(serializers.Serializer):
    id = serializers.UUIDField(source="company_id")
    name = serializers.CharField(source="company_name")
    logo = serializers.URLField(allow_null=True)
    domain_name = serializers.SerializerMethodField()
    employees_count = serializers.IntegerField(allow_null=True)
    open_vacancies_count = serializers.IntegerField()
    matching_vacancies_count = serializers.IntegerField()
    salary_min = serializers.CharField(allow_null=True)
    salary_max = serializers.CharField(allow_null=True)
    is_top_match = serializers.BooleanField()
    subscription_tier = serializers.CharField()

    def get_domain_name(self, obj):
        domain = obj.get("domain")
        if not domain:
            return None
        language = self.context.get("language", "en")
        if language == "ru":
            return domain.name_ru or domain.name_en or domain.name
        if language == "uz":
            return domain.name_uz or domain.name_en or domain.name
        return domain.name_en or domain.name

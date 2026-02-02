from rest_framework import serializers
from accounts.models import User


def _get_full_file_url(file_field, request=None):
    if not file_field:
        return None

    file_path = file_field.name if hasattr(file_field, 'name') else str(file_field)
    if not file_path:
        return None

    if file_path.startswith('http://') or file_path.startswith('https://'):
        return file_path

    from django.conf import settings
    custom_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
    if custom_domain:
        return f"https://{custom_domain}/{file_path}"
    if request:
        return request.build_absolute_uri(f"{settings.MEDIA_URL}{file_path}")
    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    if media_url.startswith('http'):
        return f"{media_url.rstrip('/')}/{file_path}"
    return f"{media_url}{file_path}"


class SubjectAnalyticsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    count = serializers.IntegerField()


class TeacherAnalyticsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    count = serializers.IntegerField()


class YearAnalyticsSerializer(serializers.Serializer):
    year = serializers.CharField()
    count = serializers.IntegerField()


class SalesAnalyticsSerializer(serializers.Serializer):
    summary = serializers.DictField()
    subjects = SubjectAnalyticsSerializer(many=True)
    teachers = TeacherAnalyticsSerializer(many=True)
    years = YearAnalyticsSerializer(many=True)


class BestSellerProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.FloatField()
    subject = serializers.CharField(allow_null=True)
    teacher = serializers.CharField(allow_null=True)
    year = serializers.CharField(allow_null=True)
    sales_count = serializers.IntegerField()
    total_revenue = serializers.FloatField()


class AnalysisProductListSerializer(serializers.Serializer):
    """A Product serialized in the same shape as dashboard purchased-books items, plus paid_times."""

    id = serializers.IntegerField()
    book_token = serializers.CharField(allow_null=True)
    product_number = serializers.CharField(allow_null=True)
    name = serializers.CharField(allow_null=True)
    product_name = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)
    student_name = serializers.CharField(allow_null=True)
    student_phone = serializers.CharField(allow_null=True)
    type = serializers.CharField(allow_null=True)
    year = serializers.CharField(allow_null=True)
    subject_id = serializers.IntegerField(allow_null=True)
    subject_name = serializers.CharField(allow_null=True)
    teacher_id = serializers.IntegerField(allow_null=True)
    teacher_name = serializers.CharField(allow_null=True)
    base_image = serializers.CharField(allow_null=True)
    pdf_file = serializers.CharField(allow_null=True)
    paid_times = serializers.IntegerField()
    free_paid_times = serializers.IntegerField()
    manual_assigned_times = serializers.IntegerField()
    total_paid_times = serializers.IntegerField()


class AnalysisProductPurchaserSerializer(serializers.Serializer):
    name = serializers.CharField(allow_null=True)
    username = serializers.CharField(allow_null=True)
    year_displayed = serializers.CharField(allow_null=True)


class AnalysisPurchaserUserSerializer(serializers.ModelSerializer):
    year_displayed = serializers.SerializerMethodField()
    purchase_method = serializers.CharField(source='purchase_method_label', allow_null=True, read_only=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'username', 'year_displayed', 'purchase_method']

    def get_year_displayed(self, obj):
        try:
            return obj.get_year_display()
        except Exception:
            return None

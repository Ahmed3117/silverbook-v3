from rest_framework import serializers


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

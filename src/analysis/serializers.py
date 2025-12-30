from rest_framework import serializers


class CategoryAnalyticsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    count = serializers.IntegerField()


class SubCategoryAnalyticsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    count = serializers.IntegerField()


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
    categories = CategoryAnalyticsSerializer(many=True)
    subcategories = SubCategoryAnalyticsSerializer(many=True)
    subjects = SubjectAnalyticsSerializer(many=True)
    teachers = TeacherAnalyticsSerializer(many=True)
    years = YearAnalyticsSerializer(many=True)


class BestSellerProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.FloatField()
    category = serializers.CharField(allow_null=True)
    subcategory = serializers.CharField(allow_null=True)
    subject = serializers.CharField(allow_null=True)
    teacher = serializers.CharField(allow_null=True)
    year = serializers.CharField(allow_null=True)
    sales_count = serializers.IntegerField()
    total_revenue = serializers.FloatField()

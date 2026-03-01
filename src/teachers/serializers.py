from rest_framework import serializers
from products.serializers import get_full_file_url


class PurchasedBookDetailSerializer(serializers.Serializer):
    """Individual purchase record for a product."""
    id = serializers.IntegerField()
    student_name = serializers.CharField(allow_null=True)
    student_phone = serializers.CharField(allow_null=True)
    student_year = serializers.CharField(allow_null=True)
    student_government = serializers.CharField(allow_null=True)
    purchase_method = serializers.CharField()
    purchase_method_display = serializers.CharField()
    price_at_sale = serializers.FloatField(allow_null=True)
    created_at = serializers.DateTimeField()


class TeacherProductSerializer(serializers.Serializer):
    """Product belonging to the teacher with purchase analytics."""
    id = serializers.IntegerField()
    product_number = serializers.CharField(allow_null=True)
    name = serializers.CharField()
    type = serializers.CharField()
    year = serializers.CharField(allow_null=True)
    price = serializers.FloatField(allow_null=True)
    discounted_price = serializers.FloatField(allow_null=True)
    has_discount = serializers.BooleanField()
    is_available = serializers.BooleanField()
    base_image = serializers.CharField(allow_null=True)
    subject_id = serializers.IntegerField(allow_null=True)
    subject_name = serializers.CharField(allow_null=True)
    date_added = serializers.DateTimeField()
    # Purchase analytics
    paid_count = serializers.IntegerField()
    free_count = serializers.IntegerField()
    admin_added_count = serializers.IntegerField()
    total_purchases = serializers.IntegerField()
    total_revenue = serializers.FloatField()



class TeacherProfileSerializer(serializers.Serializer):
    """Full teacher profile info."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    bio = serializers.CharField(allow_null=True)
    image = serializers.CharField(allow_null=True)
    subject_id = serializers.IntegerField(allow_null=True)
    subject_name = serializers.CharField(allow_null=True)
    facebook = serializers.CharField(allow_null=True)
    instagram = serializers.CharField(allow_null=True)
    twitter = serializers.CharField(allow_null=True)
    youtube = serializers.CharField(allow_null=True)
    linkedin = serializers.CharField(allow_null=True)
    telegram = serializers.CharField(allow_null=True)
    website = serializers.CharField(allow_null=True)
    tiktok = serializers.CharField(allow_null=True)
    whatsapp = serializers.CharField(allow_null=True)


class BestSellerSerializer(serializers.Serializer):
    """Product ranked by paid purchases."""
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    product_number = serializers.CharField(allow_null=True)
    year = serializers.CharField(allow_null=True)
    base_image = serializers.CharField(allow_null=True)
    paid_count = serializers.IntegerField()
    total_revenue = serializers.FloatField()


class TeacherDashboardSerializer(serializers.Serializer):
    """Top-level response for the teacher dashboard endpoint."""
    teacher = TeacherProfileSerializer()
    summary = serializers.DictField()
    best_sellers = BestSellerSerializer(many=True)
    products = TeacherProductSerializer(many=True)


class TeacherProductDetailSerializer(serializers.Serializer):
    """Detailed analytics for a single product belonging to the teacher."""
    product = TeacherProductSerializer()
    summary = serializers.DictField()

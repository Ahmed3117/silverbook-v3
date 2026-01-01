from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from collections import defaultdict
from urllib.parse import urljoin
from django.utils import timezone
from django.db.models import Sum, F
from django.db import transaction
from django.conf import settings
from accounts.models import User
from .models import (
    BestProduct, CouponDiscount, Discount, LovedProduct,
    PillItem,
    SpecialProduct,
    Product, ProductImage, Pill, Subject, Teacher,
    PurchasedBook, PackageProduct
)


def get_full_file_url(file_field, request=None):
    """
    Get the full URL for a file/image field.
    Returns the complete URL including domain.
    """
    if not file_field:
        return None
    
    # Get the file path/name
    file_path = file_field.name if hasattr(file_field, 'name') else str(file_field)
    
    if not file_path:
        return None
    
    # If already a full URL, return as-is
    if file_path.startswith('http://') or file_path.startswith('https://'):
        return file_path
    
    # Build full URL using S3 custom domain or request
    custom_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
    
    if custom_domain:
        # Use S3/R2 custom domain
        return f"https://{custom_domain}/{file_path}"
    elif request:
        # Use request to build absolute URI
        return request.build_absolute_uri(f"{settings.MEDIA_URL}{file_path}")
    else:
        # Fallback to MEDIA_URL
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        if media_url.startswith('http'):
            return f"{media_url.rstrip('/')}/{file_path}"
        return f"{media_url}{file_path}"

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = '__all__'

    def validate_name(self, value):
        """Ensure subject name is unique (case-insensitive)."""
        # Exclude self when updating
        qs = Subject.objects.filter(name__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("توجد مادة بالفعل بنفس الاسم , اختر اسم اخر من فضلك .")
        return value

class TeacherSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
    # Make image writable for uploads, but serialize as full URL on read
    image = serializers.ImageField(required=False, allow_null=True, use_url=False)

    class Meta:
        model = Teacher
        fields = ['id', 'name', 'bio','image','subject','subject_name' , 'facebook', 'instagram', 'twitter', 'youtube', 'linkedin', 'telegram', 'website','tiktok', 'whatsapp']

    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        if instance and getattr(instance, 'image', None):
            ret['image'] = get_full_file_url(instance.image, request)
        else:
            ret['image'] = None
        return ret

class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'image', 'created_at']

    def get_image(self, obj):
        return get_full_file_url(obj.image, self.context.get('request'))

class ProductImageBulkUploadSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False
    )


class ProductS3UploadSerializer(serializers.Serializer):
    """
    Serializer for creating/updating products with S3 URLs instead of file uploads.
    Accepts object keys from S3 presigned uploads.
    """
    name = serializers.CharField(max_length=100)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    price = serializers.FloatField(required=False, allow_null=True)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    year = serializers.CharField(max_length=20, required=False, allow_blank=True)
    
    # S3 URLs - these come from presigned upload responses
    pdf_object_key = serializers.CharField(max_length=500, required=False, allow_blank=True, help_text="S3 object key for PDF file (e.g., 'pdfs/uuid.pdf')")
    base_image_object_key = serializers.CharField(max_length=500, required=False, allow_blank=True, help_text="S3 object key for product image (e.g., 'products/uuid.jpg')")
    
    is_available = serializers.BooleanField(default=True)
    
    def create(self, validated_data):
        """Create a product from S3 object keys"""
        from services.s3_service import s3_service
        
        pdf_key = validated_data.pop('pdf_object_key', None)
        image_key = validated_data.pop('base_image_object_key', None)
        
        # Update file fields to use S3 URLs
        if pdf_key:
            validated_data['pdf_file'] = pdf_key
        if image_key:
            validated_data['base_image'] = image_key
        
        # Create the product
        product = Product.objects.create(**validated_data)
        return product
    
    def update(self, instance, validated_data):
        """Update a product with S3 object keys"""
        pdf_key = validated_data.pop('pdf_object_key', None)
        image_key = validated_data.pop('base_image_object_key', None)
        
        if pdf_key:
            instance.pdf_file = pdf_key
        if image_key:
            instance.base_image = image_key
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


class ProductSerializer(serializers.ModelSerializer):
    discounted_price = serializers.SerializerMethodField()
    has_discount = serializers.SerializerMethodField()
    current_discount = serializers.SerializerMethodField()
    discount_expiry = serializers.SerializerMethodField()
    subject_id = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    teacher_image = serializers.SerializerMethodField()
    related_products = serializers.SerializerMethodField()
    
    # Override file fields - accept strings on write, return full URLs on read
    base_image = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            'id', 'product_number','name','type','year','subject' ,'teacher', 
            'subject_id' ,'subject_name', 'teacher_id','teacher_name','teacher_image', 
            'price', 'description', 'date_added', 'discounted_price',
            'has_discount', 'current_discount', 'discount_expiry',
            'base_image', 'is_available', 'related_products'
        ]
        read_only_fields = [
            'product_number', 'date_added'
        ]

    def to_representation(self, instance):
        """Override to return full URLs for file fields"""
        ret = super().to_representation(instance)
        request = self.context.get('request')
            
        # Convert base_image to full URL
        if instance.base_image:
            ret['base_image'] = get_full_file_url(instance.base_image, request)
        else:
            ret['base_image'] = None
            
        return ret

    def get_subject_id(self, obj):
        return obj.subject.id if obj.subject else None
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    def get_teacher_id(self, obj):
        return obj.teacher.id if obj.teacher else None
    def get_teacher_name(self, obj):
        return obj.teacher.name if obj.teacher else None
    def get_teacher_image(self, obj):
        if obj.teacher and obj.teacher.image:
            return get_full_file_url(obj.teacher.image, self.context.get('request'))
        return None

    def get_discounted_price(self, obj):
        return obj.discounted_price()

    def get_current_discount(self, obj):
        now = timezone.now()
        product_discount = obj.discounts.filter(
            is_active=True,
            discount_start__lte=now,
            discount_end__gte=now
        ).order_by('-discount').first()
        return product_discount.discount if product_discount else None

    def get_discount_expiry(self, obj):
        now = timezone.now()
        discount = obj.discounts.filter(
            is_active=True,
            discount_start__lte=now,
            discount_end__gte=now
        ).order_by('-discount_end').first()
        return discount.discount_end if discount else None
    
    def get_has_discount(self, obj):
        return obj.has_discount()

    def get_related_products(self, obj):
        """Return list of related products if this is a package, otherwise empty list."""
        if obj.type == 'package':
            from .models import PackageProduct
            package_products = PackageProduct.objects.filter(package_product=obj).select_related('related_product').order_by('-created_at')
            related_items = []
            request = self.context.get('request')
            for pp in package_products:
                related = pp.related_product
                related_items.append({
                    'id': pp.id,
                    'created_at': pp.created_at,
                    'product_id': related.id,
                    'product_number': related.product_number,
                    'name': related.name,
                    'type': related.type,
                    'subject_id': related.subject.id if related.subject else None,
                    'subject_name': related.subject.name if related.subject else None,
                    'teacher_id': related.teacher.id if related.teacher else None,
                    'teacher_name': related.teacher.name if related.teacher else None,
                    'description': related.description,
                    'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                    'pdf_file': None,  # Hidden for student endpoints
                    'year': related.year,
                    'is_available': related.is_available,
                    'date_added': related.date_added,
                })
            return related_items
        return []
    
    def validate(self, data):
        """Validate that product name is unique per subject, teacher, and year"""
        name = data.get('name')
        subject = data.get('subject')
        teacher = data.get('teacher')
        year = data.get('year')
        
        # Build query to check for duplicates
        query = Product.objects.filter(
            name=name,
            subject=subject,
            teacher=teacher,
            year=year
        )
        
        # Exclude current instance if updating
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        
        # Check if duplicate exists
        if query.exists():
            error_parts = []
            if subject:
                error_parts.append(f"subject '{subject.name}'")
            if teacher:
                error_parts.append(f"teacher '{teacher.name}'")
            if year:
                year_display = dict(Product._meta.get_field('year').choices).get(year, year)
                error_parts.append(f"year '{year_display}'")
            
            error_msg = f"يوجد منتج بالاسم '{name}' بالفعل لـ {', '.join(error_parts) if error_parts else 'هذا المزيج'}."
            raise serializers.ValidationError({'name': error_msg})
        
        return data

    def create(self, validated_data):
        """Handle S3 object keys for base_image"""
        base_image = validated_data.pop('base_image', None)
        
        product = Product.objects.create(**validated_data)
        
        # Set the file fields with the S3 keys
        if base_image:
            product.base_image.name = base_image
            product.save()
        
        return product

    def update(self, instance, validated_data):
        """Handle S3 object keys for base_image on update"""
        base_image = validated_data.pop('base_image', None)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Set the file fields with the S3 keys
        if base_image:
            instance.base_image.name = base_image
        
        instance.save()
        return instance


class AdminProductSerializer(ProductSerializer):
    """Admin version of ProductSerializer that includes pdf_file field"""
    # Override file fields - accept strings on write, return full URLs on read
    pdf_file = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            'id', 'product_number','name','type','year','subject' ,'teacher', 
            'subject_id' ,'subject_name', 'teacher_id','teacher_name','teacher_image', 
            'price', 'description', 'date_added', 'discounted_price',
            'has_discount', 'current_discount', 'discount_expiry',
            'base_image', 'is_available', 'related_products', 'pdf_file'
        ]
        read_only_fields = [
            'product_number', 'date_added'
        ]

    def get_related_products(self, obj):
        """Return list of related products with pdf_file for admin endpoints."""
        if obj.type == 'package':
            from .models import PackageProduct
            package_products = PackageProduct.objects.filter(package_product=obj).select_related('related_product').order_by('-created_at')
            related_items = []
            request = self.context.get('request')
            for pp in package_products:
                related = pp.related_product
                related_items.append({
                    'id': pp.id,
                    'created_at': pp.created_at,
                    'product_id': related.id,
                    'product_number': related.product_number,
                    'name': related.name,
                    'type': related.type,
                    'subject_id': related.subject.id if related.subject else None,
                    'subject_name': related.subject.name if related.subject else None,
                    'teacher_id': related.teacher.id if related.teacher else None,
                    'teacher_name': related.teacher.name if related.teacher else None,
                    'description': related.description,
                    'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                    'pdf_file': get_full_file_url(related.pdf_file, request) if related.pdf_file else None,
                    'year': related.year,
                    'is_available': related.is_available,
                    'date_added': related.date_added,
                })
            return related_items
        return []

    def to_representation(self, instance):
        """Override to return full URLs for file fields including pdf_file"""
        ret = super().to_representation(instance)
        request = self.context.get('request')
            
        # Convert pdf_file to full URL
        if instance.pdf_file:
            ret['pdf_file'] = get_full_file_url(instance.pdf_file, request)
        else:
            ret['pdf_file'] = None
            
        return ret

    def create(self, validated_data):
        """Handle S3 object keys for pdf_file and base_image"""
        pdf_file = validated_data.pop('pdf_file', None)
        base_image = validated_data.pop('base_image', None)
        
        product = Product.objects.create(**validated_data)
        
        # Set the file fields with the S3 keys
        if pdf_file:
            product.pdf_file.name = pdf_file
        if base_image:
            product.base_image.name = base_image
        
        if pdf_file or base_image:
            product.save()
        
        return product

    def update(self, instance, validated_data):
        """Handle S3 object keys for pdf_file and base_image on update"""
        pdf_file = validated_data.pop('pdf_file', None)
        base_image = validated_data.pop('base_image', None)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Set the file fields with the S3 keys
        if pdf_file:
            instance.pdf_file.name = pdf_file
        if base_image:
            instance.base_image.name = base_image
        
        instance.save()
        return instance

class ProductBreifedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name']

class SimpleProductSerializer(serializers.ModelSerializer):
    """Simple serializer for product listings with minimal fields"""
    class Meta:
        model = Product
        fields = ['id', 'name', 'type']

class SimpleSubjectSerializer(serializers.ModelSerializer):
    """Simple serializer for subject listings with minimal fields"""
    class Meta:
        model = Subject
        fields = ['id', 'name']

class SimpleTeacherSerializer(serializers.ModelSerializer):
    """Simple serializer for teacher listings with minimal fields"""
    class Meta:
        model = Teacher
        fields = ['id', 'name']

class CouponCodeField(serializers.Field):
    def to_internal_value(self, data):
        try:
            return CouponDiscount.objects.get(coupon=data)
        except CouponDiscount.DoesNotExist:
            raise serializers.ValidationError("الكوبون غير موجود.")

    def to_representation(self, value):
        return value.coupon

class SpecialProductSerializerBase(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )
    # Accept file uploads for special_image and return full URL on read
    special_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = SpecialProduct
        fields = [
            'id', 'product', 'product_id', 'special_image',
            'order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        if instance.special_image:
            ret['special_image'] = get_full_file_url(instance.special_image, request)
        else:
            ret['special_image'] = None
        return ret


class ProductImageBulkUploadSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False
    )


class ProductImageBulkS3UploadSerializer(serializers.Serializer):
    """
    Serializer for bulk uploading product images via S3 object keys.
    Accept a list of S3 object keys and create ProductImage records.
    
    Request format:
    {
        "product": 1,
        "images": [
            {"object_key": "products/uuid1.jpg"},
            {"object_key": "products/uuid2.jpg"}
        ]
    }
    """
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    images = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="List of image objects with object_key"
    )
    
    def validate_images(self, value):
        """Validate that each image has an object_key"""
        for i, img in enumerate(value):
            if 'object_key' not in img:
                raise serializers.ValidationError(f"الصورة في الموضع {i} تفتقد إلى 'object_key'")
        return value
    
    def create(self, validated_data):
        """Create ProductImage records from S3 object keys"""
        product = validated_data['product']
        images_data = validated_data['images']
        
        product_images = []
        for img in images_data:
            product_image = ProductImage(
                product=product,
                image=img['object_key']
            )
            product_images.append(product_image)
        
        created_images = ProductImage.objects.bulk_create(product_images)
        return created_images


class SpecialProductSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )
    special_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = SpecialProduct
        fields = [
            'id', 'product', 'product_id', 'special_image',
            'order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        if instance.special_image:
            ret['special_image'] = get_full_file_url(instance.special_image, request)
        else:
            ret['special_image'] = None
        return ret


class AdminSpecialProductSerializer(serializers.ModelSerializer):
    """Admin version that uses AdminProductSerializer to include pdf_file"""
    product = AdminProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )
    special_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = SpecialProduct
        fields = [
            'id', 'product', 'product_id', 'special_image',
            'order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        if instance.special_image:
            ret['special_image'] = get_full_file_url(instance.special_image, request)
        else:
            ret['special_image'] = None
        return ret


class BestProductSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )

    class Meta:
        model = BestProduct
        fields = [
            'id', 'product', 'product_id',
            'order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class AdminBestProductSerializer(serializers.ModelSerializer):
    """Admin version that uses AdminProductSerializer to include pdf_file"""
    product = AdminProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )

    class Meta:
        model = BestProduct
        fields = [
            'id', 'product', 'product_id',
            'order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']






class PillItemCreateUpdateSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = PillItem
        fields = ['id', 'product']

    def validate(self, data):
        return data


class PillItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = PillItem
        fields = ['id', 'product', 'status', 'date_added']


class PillItemWithProductSerializer(serializers.ModelSerializer):
    """Serializer that returns full product details for pill items"""
    # Flatten product fields to top level
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    product_number = serializers.CharField(source='product.product_number', read_only=True)
    name = serializers.CharField(source='product.name', read_only=True)
    type = serializers.CharField(source='product.type', read_only=True)
    year = serializers.CharField(source='product.year', read_only=True)
    subject = serializers.IntegerField(source='product.subject_id', read_only=True)
    teacher = serializers.IntegerField(source='product.teacher_id', read_only=True)
    subject_id = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    teacher_image = serializers.SerializerMethodField()
    price = serializers.FloatField(source='product.price', read_only=True)
    description = serializers.CharField(source='product.description', read_only=True)
    date_added = serializers.DateTimeField(source='product.date_added', read_only=True)
    discounted_price = serializers.SerializerMethodField()
    has_discount = serializers.SerializerMethodField()
    current_discount = serializers.SerializerMethodField()
    discount_expiry = serializers.SerializerMethodField()
    base_image = serializers.SerializerMethodField()
    is_available = serializers.BooleanField(source='product.is_available', read_only=True)
    related_products = serializers.SerializerMethodField()
    pdf_file = serializers.SerializerMethodField()

    class Meta:
        model = PillItem
        fields = [
            'id', 'status', 'product_id', 'product_number', 'name', 'type', 'year',
            'subject', 'teacher',
            'subject_id', 'subject_name',
            'teacher_id', 'teacher_name', 'teacher_image',
            'price', 'description',
            'date_added', 'discounted_price', 'has_discount', 'current_discount',
            'discount_expiry',
            'base_image',
            'is_available', 'related_products', 'pdf_file'
        ]

    def get_subject_id(self, obj):
        return obj.product.subject.id if obj.product.subject else None

    def get_subject_name(self, obj):
        return obj.product.subject.name if obj.product.subject else None

    def get_teacher_id(self, obj):
        return obj.product.teacher.id if obj.product.teacher else None

    def get_teacher_name(self, obj):
        return obj.product.teacher.name if obj.product.teacher else None

    def get_teacher_image(self, obj):
        if obj.product.teacher and obj.product.teacher.image:
            return get_full_file_url(obj.product.teacher.image, self.context.get('request'))
        return None

    def get_discounted_price(self, obj):
        return obj.product.discounted_price()

    def get_has_discount(self, obj):
        return obj.product.has_discount()

    def get_current_discount(self, obj):
        now = timezone.now()
        product_discount = obj.product.discounts.filter(
            is_active=True,
            discount_start__lte=now,
            discount_end__gte=now
        ).order_by('-discount').first()
        return product_discount.discount if product_discount else None

    def get_discount_expiry(self, obj):
        now = timezone.now()
        discount = obj.product.discounts.filter(
            is_active=True,
            discount_start__lte=now,
            discount_end__gte=now
        ).order_by('-discount_end').first()
        return discount.discount_end if discount else None

    def get_base_image(self, obj):
        return get_full_file_url(obj.product.base_image, self.context.get('request'))

    def get_pdf_file(self, obj):
        return get_full_file_url(obj.product.pdf_file, self.context.get('request'))

    def get_related_products(self, obj):
        if obj.product.type == 'package':
            from .models import PackageProduct
            package_products = PackageProduct.objects.filter(package_product=obj.product).select_related('related_product').order_by('-created_at')
            related_items = []
            request = self.context.get('request')
            for pp in package_products:
                related = pp.related_product
                related_items.append({
                    'id': pp.id,
                    'created_at': pp.created_at,
                    'product_id': related.id,
                    'product_number': related.product_number,
                    'name': related.name,
                    'type': related.type,
                    'subject_id': related.subject.id if related.subject else None,
                    'subject_name': related.subject.name if related.subject else None,
                    'teacher_id': related.teacher.id if related.teacher else None,
                    'teacher_name': related.teacher.name if related.teacher else None,
                    'description': related.description,
                    'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                    'pdf_file': None,
                    'year': related.year,
                    'is_available': related.is_available,
                    'date_added': related.date_added,
                })
            return related_items
        return []


class PillItemInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_available=True))


class AdminPillItemSerializer(PillItemCreateUpdateSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False
    )
    user_details = serializers.SerializerMethodField()
    product_details = serializers.SerializerMethodField()
    pill_details = serializers.SerializerMethodField()

    class Meta(PillItemCreateUpdateSerializer.Meta):
        fields = ['id', 'user', 'user_details', 'product', 'product_details', 'status', 'date_added', 'pill', 'pill_details']
        read_only_fields = ['date_added']

    def get_user_details(self, obj):
        user = obj.user
        if not user:
            return None
        return {
            'id': user.id,
            'name': user.name,
            'email': user.email
        }

    def get_product_details(self, obj):
        product = obj.product
        request = self.context.get('request')

        image_url = None
        if product.base_image:
            image_url = get_full_file_url(product.base_image, request)

        return {
            'id': product.id,
            'name': product.name,
            'price': float(product.price),
            'product_number': product.product_number,
            'image': image_url
        }

    def get_pill_details(self, obj):
        pill = obj.pill
        if not pill:
            return None
        return {
            'id': pill.id,
            'pill_number': pill.pill_number,
            'status': pill.status
        }


class AdminLovedProductSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all()
    )
    user_details = serializers.SerializerMethodField()
    product_details = serializers.SerializerMethodField()

    class Meta:
        model = LovedProduct
        fields = [
            'id', 'user', 'user_details', 'product', 'product_details', 
            'created_at'
        ]
        read_only_fields = ['created_at']

    def get_user_details(self, obj):
        return {
            'id': obj.user.id if obj.user else None,
            'name': obj.user.name if obj.user else None,
            'email': obj.user.email if obj.user else None
        }

    def get_product_details(self, obj):
        product = obj.product
        request = self.context.get('request')
        
        image_url = None
        if product.base_image:
            image_url = get_full_file_url(product.base_image, request)
        
        return {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'image': image_url
        }

    def validate(self, data):
        # Check for duplicates
        if self.instance is None and LovedProduct.objects.filter(
            user=data.get('user', self.context.get('request').user),
            product=data['product']
        ).exists():
            raise serializers.ValidationError({
                'product': 'هذا المنتج موجود بالفعل في قائمة المفضلة للمستخدم'
            })
        return data

    def create(self, validated_data):
        # Set default user if not provided
        if 'user' not in validated_data and hasattr(self.context.get('request'), 'user'):
            validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class PillCreateSerializer(serializers.ModelSerializer):
    items = PillItemInputSerializer(many=True, write_only=True)
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    user_name = serializers.SerializerMethodField()
    user_username = serializers.SerializerMethodField()
    user_parent_phone = serializers.SerializerMethodField()
    _items_details = PillItemSerializer(source='items', many=True, read_only=True)

    class Meta:
        model = Pill
        fields = [
            'id',
            'user',
            'user_name',
            'user_username',
            'user_parent_phone',
            'items',
            '_items_details',
            'status',
            'date_added',
        ]
        read_only_fields = [
            'id',
            'user_name',
            'user_username',
            'user_parent_phone',
            '_items_details',
            'status',
            'date_added',
        ]

    def get_user_name(self, obj):
        return obj.user.name

    def get_user_username(self, obj):
        return obj.user.username

    def get_user_parent_phone(self, obj):
        return obj.user.parent_phone if obj.user else None

    def validate(self, attrs):
        items = attrs.get('items', [])
        if not items:
            raise ValidationError({'items': ['يجب تحديد عنصر واحد على الأقل']})

        product_ids = [item['product'].id for item in items]
        duplicates = {pid for pid in product_ids if product_ids.count(pid) > 1}
        if duplicates:
            raise ValidationError({'items': ['المنتجات المكررة غير مسموح بها في نفس الطلب']})

        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        user = validated_data['user']
        status_value = validated_data.get('status', Pill._meta.get_field('status').default)

        owned_numbers = set()
        owned_ids = set()
        for product_number, product_id in PurchasedBook.objects.filter(user=user).values_list(
            'product__product_number', 'product_id'
        ):
            if product_number:
                owned_numbers.add(product_number)
            if product_id:
                owned_ids.add(product_id)

        filtered_items = []
        for item_data in items_data:
            product = item_data['product']
            product_number = getattr(product, 'product_number', None)

            if product_number and product_number in owned_numbers:
                continue
            if not product_number and product.id in owned_ids:
                continue

            filtered_items.append(item_data)

        if not filtered_items:
            raise ValidationError({'items': ['جميع المنتجات المحددة مملوكة بالفعل']})

        with transaction.atomic():
            pill = Pill.objects.create(**validated_data)

            pill_items = []
            for item_data in filtered_items:
                product = item_data['product']

                if not product.is_available:
                    raise ValidationError({'items': [f'المنتج "{product.name}" غير متاح للشراء']})

                pill_item = PillItem.objects.create(
                    user=user,
                    product=product,
                    status=status_value,
                    pill=pill,
                )
                pill_items.append(pill_item)

            pill.items.set(pill_items)

        return pill

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['items'] = representation.pop('_items_details', [])
        return representation

class CouponDiscountSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = CouponDiscount
        fields = [
            'id', 'coupon', 'discount_value', 'coupon_start', 'coupon_end',
            'available_use_times', 'user', 'min_order_value', 'is_active',
            'is_available'
        ]

    def get_is_active(self, obj):
        now = timezone.now()
        return obj.coupon_start <= now <= obj.coupon_end

    def get_is_available(self, obj):
        return obj.available_use_times > 0 and self.get_is_active(obj)


class BulkCouponDiscountSerializer(serializers.Serializer):
    """Serializer for bulk coupon creation"""
    number_of_coupons = serializers.IntegerField(min_value=1, max_value=1000, help_text="Number of coupons to create (1-1000)")
    discount_value = serializers.FloatField(required=False, allow_null=True)
    coupon_start = serializers.DateTimeField(required=False, allow_null=True)
    coupon_end = serializers.DateTimeField(required=False, allow_null=True)
    available_use_times = serializers.IntegerField(default=1, min_value=1)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    min_order_value = serializers.FloatField(required=False, allow_null=True)

    def create(self, validated_data):
        number_of_coupons = validated_data.pop('number_of_coupons')
        coupons = []
        
        for _ in range(number_of_coupons):
            coupon = CouponDiscount.objects.create(**validated_data)
            coupons.append(coupon)
        
        return coupons


class PillDetailSerializer(serializers.ModelSerializer):
    items = PillItemSerializer(many=True, read_only=True)
    coupon = CouponDiscountSerializer(read_only=True)
    status_display = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    user_username = serializers.SerializerMethodField()
    user_parent_phone = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    payment_url = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = Pill
        fields = [
            'id','pill_number', 'user_name', 'user_username', 'user_parent_phone' ,'items', 'status', 
            'status_display', 'date_added', 'coupon', 'final_price', 'shakeout_invoice_id', 
            'easypay_invoice_uid','easypay_fawry_ref', 'easypay_invoice_sequence', 'payment_gateway', 'payment_url', 'payment_status'
        ]
        read_only_fields = [
            'id','pill_number', 'user_name', 'user_username', 'items', 'status', 'status_display', 'date_added', 'coupon',
            'final_price', 'shakeout_invoice_id', 'easypay_invoice_uid','easypay_fawry_ref', 
            'easypay_invoice_sequence', 'payment_gateway', 'payment_url', 'payment_status'
        ]

    def get_user_name(self, obj):
        return obj.user.name

    def get_user_username(self, obj):
        return obj.user.username
    
    def get_user_parent_phone(self, obj):
        return obj.user.parent_phone if obj.user else None

    def get_status_display(self, obj):
        return obj.get_status_display()
    
    def get_final_price(self, obj):
        return obj.final_price()
    
    def get_shakeout_invoice_url(self, obj):
        if obj.shakeout_invoice_id and obj.shakeout_invoice_ref:
            return f"https://dash.shake-out.com/invoice/{obj.shakeout_invoice_id}/{obj.shakeout_invoice_ref}"
        return None
    
    def get_easypay_invoice_url(self, obj):
        if obj.easypay_invoice_uid and obj.easypay_invoice_sequence:
            return f"https://stu.easy-adds.com/invoice/{obj.easypay_invoice_uid}/{obj.easypay_invoice_sequence}"
        return None
    
    def get_payment_url(self, obj):
        return getattr(obj, 'payment_url', None)
    
    def get_payment_status(self, obj):
        return getattr(obj, 'payment_status', None)


class PillSerializer(serializers.ModelSerializer):
    coupon = CouponDiscountSerializer(read_only=True)
    status_display = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    user_username = serializers.SerializerMethodField()
    user_parent_phone = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    shakeout_invoice_url = serializers.SerializerMethodField()
    easypay_invoice_url = serializers.SerializerMethodField()
    payment_url = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = Pill
        fields = [
            'id', 'pill_number', 'user_name', 'user_username', 
            'user_parent_phone', 'items', 'items_count', 'status', 
            'status_display', 'date_added', 'coupon', 'final_price', 'shakeout_invoice_id', 
            'shakeout_invoice_url', 'easypay_invoice_uid', 'easypay_invoice_sequence', 
            'easypay_invoice_url', 'payment_gateway', 'payment_url', 'payment_status'
        ]
        read_only_fields = [
            'id', 'pill_number', 'user_name', 'user_username', 
            'status', 'status_display', 'date_added', 'coupon', 'final_price', 'items_count',
            'shakeout_invoice_id', 'shakeout_invoice_url', 'easypay_invoice_uid', 
            'easypay_invoice_sequence', 'easypay_invoice_url', 'payment_gateway', 
            'payment_url', 'payment_status'
        ]

    def get_user_name(self, obj):
        return obj.user.name if obj.user else None

    def get_user_username(self, obj):
        return obj.user.username if obj.user else None

    def get_user_parent_phone(self, obj):
        return obj.user.parent_phone if obj.user else None

    def get_status_display(self, obj):
        return obj.get_status_display()

    def get_final_price(self, obj):
        return obj.final_price()

    def get_items_count(self, obj):
        return getattr(obj, 'items_count', obj.items.count())
    
    def get_shakeout_invoice_url(self, obj):
        if obj.shakeout_invoice_id and obj.shakeout_invoice_ref:
            return f"https://dash.shake-out.com/invoice/{obj.shakeout_invoice_id}/{obj.shakeout_invoice_ref}"
        return None
    
    def get_easypay_invoice_url(self, obj):
        if obj.easypay_invoice_uid and obj.easypay_invoice_sequence:
            return f"https://stu.easy-adds.com/invoice/{obj.easypay_invoice_uid}/{obj.easypay_invoice_sequence}"
        return None
    
    def get_payment_url(self, obj):
        return getattr(obj, 'payment_url', None)
    
    def get_payment_status(self, obj):
        return getattr(obj, 'payment_status', None)


class PillDetailWithoutItemsSerializer(serializers.ModelSerializer):
    """Pill detail serializer without items - for separate items endpoint"""
    coupon = CouponDiscountSerializer(read_only=True)
    user_name = serializers.SerializerMethodField()
    user_username = serializers.SerializerMethodField()
    user_parent_phone = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()

    class Meta:
        model = Pill
        fields = [
            'id', 'pill_number', 'user_name', 'user_username', 
            'user_parent_phone', 'status', 'date_added', 'coupon', 
            'final_price', 'shakeout_invoice_id', 'easypay_invoice_uid', 
            'easypay_fawry_ref', 'easypay_invoice_sequence', 'payment_gateway'
        ]
        read_only_fields = [
            'id', 'pill_number', 'user_name', 'user_username', 
            'user_parent_phone', 'status', 'date_added', 'coupon', 
            'final_price', 'shakeout_invoice_id', 'easypay_invoice_uid', 
            'easypay_fawry_ref', 'easypay_invoice_sequence', 'payment_gateway'
        ]

    def get_user_name(self, obj):
        return obj.user.name if obj.user else None

    def get_user_username(self, obj):
        return obj.user.username if obj.user else None

    def get_user_parent_phone(self, obj):
        return obj.user.parent_phone if obj.user else None

    def get_final_price(self, obj):
        return float(obj.final_price())


class DiscountSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Discount
        fields = [
            'id', 'product', 'product_name',
            'discount', 'discount_start', 'discount_end', 'is_active'
        ]
        read_only_fields = ['is_active']

    def get_product_name(self, obj):
        return obj.product.name if obj.product else None

    def get_is_active(self, obj):
        return obj.is_currently_active

    def validate(self, data):
        if not data.get('product'):
            raise serializers.ValidationError("يجب تحديد المنتج")
        return data

class LovedProductSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )

    class Meta:
        model = LovedProduct
        fields = ['id', 'product', 'product_id', 'created_at']
        read_only_fields = ['id', 'product', 'created_at']
        validators = []

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError({'detail': 'لم يتم توفير بيانات الاعتماد.'})

        product = attrs['product']
        if LovedProduct.objects.filter(user=user, product=product).exists():
            raise serializers.ValidationError({'product_id': 'هذا المنتج موجود بالفعل في قائمة المفضلة لديك.'})

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError({'detail': 'لم يتم توفير بيانات الاعتماد.'})

        return LovedProduct.objects.create(user=user, **validated_data)


class LovedProductListSerializer(serializers.ModelSerializer):
    """Serializer that returns only product data for loved products list"""
    
    class Meta:
        model = LovedProduct
        fields = []  # We'll override to_representation
    
    def to_representation(self, instance):
        """Return only the product data"""
        return ProductSerializer(instance.product, context=self.context).data


class AdminLovedProductSerializer(serializers.ModelSerializer):
    """Admin version that uses AdminProductSerializer to include pdf_file"""
    product = AdminProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False
    )
    user_details = serializers.SerializerMethodField()

    class Meta:
        model = LovedProduct
        fields = ['id', 'product', 'product_id', 'created_at', 'user', 'user_details']
        read_only_fields = ['id', 'product', 'created_at']
        validators = []

    def get_user_details(self, obj):
        if not obj.user:
            return None
        return {
            'id': obj.user.id,
            'name': obj.user.name,
            'email': obj.user.email
        }

    def validate(self, attrs):
        user = attrs.get('user')
        if not user:
            request_user = getattr(self.context.get('request'), 'user', None)
            if request_user and request_user.is_staff:
                user = request_user
            else:
                raise serializers.ValidationError({'user': 'يجب تحديد المستخدم.'})

        product = attrs['product']
        if LovedProduct.objects.filter(user=user, product=product).exists():
            raise serializers.ValidationError({'product_id': 'هذا المنتج موجود بالفعل في قائمة المفضلة لهذا المستخدم.'})

        attrs['user'] = user
        return attrs

    def create(self, validated_data):
        user = validated_data.pop('user')
        return LovedProduct.objects.create(user=user, **validated_data)


class PurchasedBookSerializer(serializers.ModelSerializer):
    # Read fields
    id = serializers.IntegerField(read_only=True)
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    pill_id = serializers.IntegerField(source='pill.id', read_only=True, allow_null=True)
    pill_number = serializers.CharField(source='pill.pill_number', read_only=True, allow_null=True)
    
    # Write fields (for create/update)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), write_only=True)
    pill = serializers.PrimaryKeyRelatedField(queryset=Pill.objects.all(), required=False, allow_null=True, write_only=True)
    pill_item = serializers.PrimaryKeyRelatedField(queryset=PillItem.objects.all(), required=False, allow_null=True, write_only=True)
    
    product_number = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    student_phone = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    subject_id = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    base_image = serializers.SerializerMethodField()
    pdf_file = serializers.SerializerMethodField()
    related_products = serializers.SerializerMethodField()

    class Meta:
        model = PurchasedBook
        fields = [
            'id', 'user',
            'product', 'product_id', 'product_number',
            'pill', 'pill_id', 'pill_number',
            'pill_item', 'product_name', 'created_at',
            'student_name', 'student_phone', 'type', 'year', 'subject_id', 'subject_name',
            'teacher_id', 'teacher_name', 'base_image', 'pdf_file', 'related_products'
        ]
        read_only_fields = ['id', 'created_at', 'product_id', 'pill_id', 'pill_number']

    def _product(self, obj):
        return getattr(obj, 'product', None)

    def _build_absolute_uri(self, path):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(path)
        return path

    def get_product_number(self, obj):
        product = self._product(obj)
        return product.product_number if product else None

    def get_student_name(self, obj):
        user = getattr(obj, 'user', None)
        return user.name if user else None

    def get_student_phone(self, obj):
        user = getattr(obj, 'user', None)
        # Historically `student_phone` may map to username in some responses
        return user.username if user else None

    def get_type(self, obj):
        product = self._product(obj)
        return product.type if product else None

    def get_year(self, obj):
        product = self._product(obj)
        return product.year if product else None

    def get_subject_id(self, obj):
        product = self._product(obj)
        return product.subject_id if product else None

    def get_subject_name(self, obj):
        product = self._product(obj)
        return product.subject.name if product and product.subject else None

    def get_teacher_id(self, obj):
        product = self._product(obj)
        return product.teacher_id if product else None

    def get_teacher_name(self, obj):
        product = self._product(obj)
        return product.teacher.name if product and product.teacher else None

    def get_base_image(self, obj):
        product = self._product(obj)
        if product and product.base_image:
            return self._build_absolute_uri(product.base_image.url)
        return None

    def get_pdf_file(self, obj):
        product = self._product(obj)
        if product and product.pdf_file:
            return self._build_absolute_uri(product.pdf_file.url)
        return None

    def get_related_products(self, obj):
        """Return list of related products if this is a package, otherwise empty list."""
        product = self._product(obj)
        if not product or product.type != 'package':
            return []
        
        from .models import PackageProduct
        package_products = PackageProduct.objects.filter(package_product=product).select_related('related_product').order_by('-created_at')
        related_items = []
        request = self.context.get('request')
        for pp in package_products:
            related = pp.related_product
            related_items.append({
                'id': pp.id,
                'created_at': pp.created_at,
                'product_id': related.id,
                'product_number': related.product_number,
                'name': related.name,
                'type': related.type,
                'subject_id': related.subject.id if related.subject else None,
                'subject_name': related.subject.name if related.subject else None,
                'teacher_id': related.teacher.id if related.teacher else None,
                'teacher_name': related.teacher.name if related.teacher else None,
                'description': related.description,
                'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                'pdf_file': get_full_file_url(related.pdf_file, request) if related.pdf_file else None,
                'year': related.year,
                'is_available': related.is_available,
                'date_added': related.date_added,
            })
        return related_items


class PillCouponApplySerializer(serializers.ModelSerializer):
    coupon = CouponDiscountSerializer(read_only=True)
    coupon_code = serializers.CharField(write_only=True)
    final_price = serializers.SerializerMethodField()

    class Meta:
        model = Pill
        fields = ['id', 'coupon_code', 'coupon', 'coupon_discount', 'final_price']
        read_only_fields = ['id', 'coupon', 'coupon_discount', 'final_price']

    def to_internal_value(self, data):
        if isinstance(data, dict) and 'coupon' in data and 'coupon_code' not in data:
            data = data.copy()
            data['coupon_code'] = data.pop('coupon')
        return super().to_internal_value(data)

    def validate(self, attrs):
        coupon_code = attrs.get('coupon_code')
        if not coupon_code:
            raise serializers.ValidationError({'coupon_code': 'يجب توفير رمز الكوبون.'})

        coupon_code = coupon_code.strip()
        pill = self.instance

        try:
            coupon = CouponDiscount.objects.get(coupon__iexact=coupon_code)
        except CouponDiscount.DoesNotExist:
            raise serializers.ValidationError({'coupon_code': 'الكوبون غير موجود.'})

        now = timezone.now()
        if coupon.coupon_start and coupon.coupon_start > now:
            raise serializers.ValidationError({'coupon_code': 'الكوبون غير مفعل بعد.'})
        if coupon.coupon_end and coupon.coupon_end < now:
            raise serializers.ValidationError({'coupon_code': 'انتهت صلاحية الكوبون.'})
        if coupon.available_use_times <= 0 and pill.coupon_id != coupon.id:
            raise serializers.ValidationError({'coupon_code': 'تم استخدام هذا الكوبون بالكامل.'})
        if coupon.user_id and pill.user_id != coupon.user_id:
            raise serializers.ValidationError({'coupon_code': 'الكوبون غير صالح لهذا المستخدم.'})
        if not coupon.discount_value or coupon.discount_value <= 0:
            raise serializers.ValidationError({'coupon_code': 'الكوبون لا يحتوي على قيمة خصم صالحة.'})

        subtotal = self._calculate_subtotal(pill)
        if subtotal <= 0:
            raise serializers.ValidationError({'coupon_code': 'يجب أن يكون إجمالي الطلب أكبر من صفر لتطبيق الكوبون.'})
        if coupon.min_order_value and subtotal < coupon.min_order_value:
            raise serializers.ValidationError({'coupon_code': f'الحد الأدنى لقيمة الطلب لهذا الكوبون هو {coupon.min_order_value}.'})

        discount_amount = subtotal * (coupon.discount_value / 100)
        discount_amount = min(subtotal, discount_amount)

        self._coupon = coupon
        self._discount_amount = round(float(discount_amount), 2)
        return attrs

    def update(self, instance, validated_data):
        validated_data.pop('coupon_code', None)
        coupon = getattr(self, '_coupon', None)
        discount_amount = getattr(self, '_discount_amount', None)

        if coupon is None or discount_amount is None:
            raise serializers.ValidationError({'coupon_code': 'فشل التحقق من الكوبون.'})

        with transaction.atomic():
            try:
                coupon_for_update = CouponDiscount.objects.select_for_update().get(pk=coupon.pk)
            except CouponDiscount.DoesNotExist:  # pragma: no cover - defensive
                raise serializers.ValidationError({'coupon_code': 'الكوبون غير موجود.'})

            if coupon_for_update.available_use_times <= 0 and instance.coupon_id != coupon_for_update.pk:
                raise serializers.ValidationError({'coupon_code': 'تم استخدام هذا الكوبون بالكامل.'})

            if instance.coupon_id and instance.coupon_id != coupon_for_update.pk:
                raise serializers.ValidationError({'coupon_code': 'تم تطبيق كوبون مختلف بالفعل على هذا الطلب.'})

            is_new_coupon = instance.coupon_id != coupon_for_update.pk

            if is_new_coupon:
                updated = CouponDiscount.objects.filter(
                    pk=coupon_for_update.pk,
                    available_use_times__gt=0
                ).update(available_use_times=F('available_use_times') - 1)
                if not updated:
                    raise serializers.ValidationError({'coupon_code': 'وصل هذا الكوبون إلى حد الاستخدام.'})
                instance.coupon = coupon_for_update

            instance.coupon_discount = discount_amount
            update_fields = ['coupon_discount']
            if is_new_coupon:
                update_fields.append('coupon')
            instance.save(update_fields=update_fields)

        return instance

    def get_final_price(self, obj):
        return obj.final_price()

    def _calculate_subtotal(self, pill):
        total = 0.0
        for item in pill.items.select_related('product').all():
            product = getattr(item, 'product', None)
            if not product:
                continue
            price = product.discounted_price()
            if price is None:
                price = product.price or 0.0
            total += float(price)
        return total


class UserCartSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    product = ProductSerializer(read_only=True)
    status = serializers.CharField(read_only=True)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['product'] = ProductSerializer(instance.product, context=self.context).data
        return ret


class PackageProductListSerializer(serializers.ModelSerializer):
    """Serializer for listing packages with their related products in flat structure"""
    id = serializers.IntegerField(source='package_product.id')
    product_number = serializers.CharField(source='package_product.product_number')
    name = serializers.CharField(source='package_product.name')
    type = serializers.CharField(source='package_product.type')
    subject_id = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    price = serializers.FloatField(source='package_product.price')
    discounted_price = serializers.SerializerMethodField()
    has_discount = serializers.SerializerMethodField()
    discount_expiry = serializers.SerializerMethodField()
    description = serializers.CharField(source='package_product.description')
    base_image = serializers.SerializerMethodField()
    year = serializers.CharField(source='package_product.year')
    is_available = serializers.BooleanField(source='package_product.is_available')
    date_added = serializers.DateTimeField(source='package_product.date_added')
    related_products = serializers.SerializerMethodField()

    class Meta:
        model = PackageProduct
        fields = [
            'id', 'product_number', 'name', 'type', 'subject_id', 'subject_name',
            'teacher_id', 'teacher_name', 'price', 'discounted_price', 'has_discount',
            'discount_expiry', 'description', 'base_image', 'year', 'is_available',
            'date_added', 'related_products'
        ]

    def get_subject_id(self, obj):
        return obj.package_product.subject.id if obj.package_product.subject else None

    def get_subject_name(self, obj):
        return obj.package_product.subject.name if obj.package_product.subject else None

    def get_teacher_id(self, obj):
        return obj.package_product.teacher.id if obj.package_product.teacher else None

    def get_teacher_name(self, obj):
        return obj.package_product.teacher.name if obj.package_product.teacher else None

    def get_discounted_price(self, obj):
        return obj.package_product.discounted_price()

    def get_has_discount(self, obj):
        return obj.package_product.has_discount()

    def get_discount_expiry(self, obj):
        discount = obj.package_product.get_current_discount()
        return discount.discount_end if discount else None

    def get_base_image(self, obj):
        request = self.context.get('request')
        return get_full_file_url(obj.package_product.base_image, request) if obj.package_product.base_image else None

    def get_related_products(self, obj):
        """Return all related products for this package"""
        from .models import PackageProduct
        package_products = PackageProduct.objects.filter(
            package_product=obj.package_product
        ).select_related('related_product').order_by('-created_at')
        
        related_items = []
        request = self.context.get('request')
        for pp in package_products:
            related = pp.related_product
            related_items.append({
                'package_product_id': pp.id,
                'created_at': pp.created_at,
                'product_id': related.id,
                'product_number': related.product_number,
                'name': related.name,
                'type': related.type,
                'subject_id': related.subject.id if related.subject else None,
                'subject_name': related.subject.name if related.subject else None,
                'teacher_id': related.teacher.id if related.teacher else None,
                'teacher_name': related.teacher.name if related.teacher else None,
                'description': related.description,
                'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                'pdf_file': get_full_file_url(related.pdf_file, request) if related.pdf_file else None,
                'year': related.year,
                'is_available': related.is_available,
                'date_added': related.date_added,
            })
        return related_items


class PackageProductSerializer(serializers.ModelSerializer):
    """Serializer for PackageProduct model with detailed product data"""
    package_product = serializers.SerializerMethodField()
    related_product = serializers.SerializerMethodField()

    class Meta:
        model = PackageProduct
        fields = ['id', 'created_at', 'package_product', 'related_product']
        read_only_fields = ['id', 'created_at']

    def get_package_product(self, obj):
        """Return package product details without extra data."""
        package = obj.package_product
        request = self.context.get('request')
        
        return {
            'id': package.id,
            'product_number': package.product_number,
            'name': package.name,
            'type': package.type,
            'subject_id': package.subject.id if package.subject else None,
            'subject_name': package.subject.name if package.subject else None,
            'teacher_id': package.teacher.id if package.teacher else None,
            'teacher_name': package.teacher.name if package.teacher else None,
            'price': package.price,
            'discounted_price': package.discounted_price(),
            'has_discount': package.has_discount(),
            'description': package.description,
            'base_image': get_full_file_url(package.base_image, request) if package.base_image else None,
            'year': package.year,
            'is_available': package.is_available,
            'date_added': package.date_added,
        }

    def get_related_product(self, obj):
        """Return related product details without prices"""
        related = obj.related_product
        request = self.context.get('request')
        
        return {
            'id': related.id,
            'product_number': related.product_number,
            'name': related.name,
            'type': related.type,
            'subject_id': related.subject.id if related.subject else None,
            'subject_name': related.subject.name if related.subject else None,
            'teacher_id': related.teacher.id if related.teacher else None,
            'teacher_name': related.teacher.name if related.teacher else None,
            'description': related.description,
            'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
            'pdf_file': get_full_file_url(related.pdf_file, request) if related.pdf_file else None,
            'year': related.year,
            'is_available': related.is_available,
            'date_added': related.date_added,
        }

    def validate(self, data):
        """Validate that package_product is a package and related_product is a book."""
        package = data.get('package_product')
        related = data.get('related_product')
        
        if package and package.type != 'package':
            raise serializers.ValidationError({'package_product': 'يجب أن يكون المنتج من نوع حزمة.'})
        if related and related.type != 'book':
            raise serializers.ValidationError({'related_product': 'يجب أن يكون المنتج المرتبط من نوع كتاب.'})
        if package and related and package.id == related.id:
            raise serializers.ValidationError('لا يمكن ربط المنتج بنفسه.')
        
        return data


class AddBooksToPackageSerializer(serializers.Serializer):
    """Serializer for adding multiple books to a package"""
    package = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(type='package'))
    related_products = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text="List of product IDs to add to the package"
    )

    def validate_related_products(self, value):
        """Ensure all IDs exist in the database"""
        if not value:
            raise serializers.ValidationError("يجب تحديد منتج واحد على الأقل.")
        return value













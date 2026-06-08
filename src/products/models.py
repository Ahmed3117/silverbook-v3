import random
import string
import uuid
from django.db import models, transaction
from django.db.models import Prefetch
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from services.beon_service import send_beon_sms
from accounts.models import YEAR_CHOICES, User
from core import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

GOVERNMENT_CHOICES = [
    ('1', 'Cairo'),
    ('2', 'Alexandria'),
    ('3', 'Kafr El Sheikh'),
    ('4', 'Dakahleya'),
    ('5', 'Sharkeya'),
    ('6', 'Gharbeya'),
    ('7', 'Monefeya'),
    ('8', 'Qalyubia'),
    ('9', 'Giza'),
    ('10', 'Bani-Sweif'),
    ('11', 'Fayoum'),
    ('12', 'Menya'),
    ('13', 'Assiut'),
    ('14', 'Sohag'),
    ('15', 'Qena'),
    ('16', 'Luxor'),
    ('17', 'Aswan'),
    ('18', 'Red Sea'),
    ('19', 'Behera'),
    ('20', 'Ismailia'),
    ('21', 'Suez'),
    ('22', 'Port-Said'),
    ('23', 'Damietta'),
    ('24', 'Marsa Matrouh'),
    ('25', 'Al-Wadi Al-Gadid'),
    ('26', 'North Sinai'),
    ('27', 'South Sinai'),
]

PILL_STATUS_CHOICES = [
    ('i', 'initiated'),
    ('w', 'Waiting'),
    ('p', 'Paid'),
    ('c', 'Cancelled'),
    ('e', 'Expired'),
]

PAYMENT_GATEWAY_CHOICES = [
    ('easypay', 'EasyPay'),
    ('shakeout', 'Shake-out'),
]

PRODUCT_TYPE_CHOICES = [
    ('book', 'Book'),
    ('package', 'Package'),
]

PURCHASE_METHOD_CHOICES = [
    ('user_paid', 'مدفوع'),
    ('free', 'مجاني'),
    ('admin_added', 'تعيين يدوي'),
    ('promo_code', 'كود ترويجي'),
]

BOOK_PUBLISH_REQUEST_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('accepted', 'Accepted'),
    ('refused', 'Refused'),
]

def generate_pill_number():
    """Generate a unique 20-digit pill number."""
    while True:
        pill_number = ''.join(random.choices(string.digits, k=20))
        if not Pill.objects.filter(pill_number=pill_number).exists():
            return pill_number

def create_random_coupon():
    nums = ['0', '2', '3', '4', '5', '6', '7', '8', '9']
    return ''.join(random.choice(nums) for _ in range(11))

class Subject(models.Model):
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name
    
class Teacher(models.Model):
    bio = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='teachers/', null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teachers')
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='teacher_profile',
        help_text="Link to the User account (user_type='teacher')"
    )
    facebook = models.CharField(max_length=200, null=True, blank=True)
    instagram = models.CharField(max_length=200, null=True, blank=True)
    twitter = models.CharField(max_length=200, null=True, blank=True)
    linkedin = models.CharField(max_length=200, null=True, blank=True)
    youtube = models.CharField(max_length=200, null=True, blank=True)
    whatsapp = models.CharField(max_length=200, null=True, blank=True)
    tiktok = models.CharField(max_length=200, null=True, blank=True)
    telegram = models.CharField(max_length=200, null=True, blank=True)
    website = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def name(self):
        """Teacher name is derived from the linked User."""
        return self.user.name if self.user else ''
    
    def __str__(self):
        return self.name

class Product(models.Model):
    product_number = models.CharField(max_length=20, null=True, blank=True)
    name = models.CharField(max_length=100)
    type = models.CharField(
        max_length=10,
        choices=PRODUCT_TYPE_CHOICES,
        default='book',
        help_text="Product type: Book or Package"
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True, related_name='products')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, null=True, blank=True, related_name='products')
    price = models.FloatField(null=True, blank=True)
    description = models.TextField(max_length=1000, null=True, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    year = models.CharField(
        max_length=20,
        choices=YEAR_CHOICES,
        null=True,
        blank=True,
    )
    
    # PDF File storage (for S3 in production)
    pdf_file = models.FileField(
        upload_to='pdfs/',
        null=True,
        blank=True,
        help_text="PDF file stored in S3 in production"
    )
    
    # Base image for product cover
    base_image = models.ImageField(
        upload_to='products/',
        null=True,
        blank=True,
        help_text="Main product cover image"
    )
    
    is_available = models.BooleanField(
        default=True,
        help_text="Whether this digital book is available for purchase"
    )

    is_downloadable = models.BooleanField(
        default=False,
        help_text="Whether this product can be downloaded as a file"
    )

    book_token = models.CharField(max_length=64, null=True, blank=True, editable=False, db_index=True)
    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Display order (lower numbers appear first). Default 0 means no priority.",
    )
    
    def get_current_discount(self):
        """Returns the active product discount"""
        now = timezone.now()
        product_discount = self.discounts.filter(
            is_active=True,
            discount_start__lte=now,
            discount_end__gte=now
        ).order_by('-discount').first()
        return product_discount

    def price_after_product_discount(self):
        last_product_discount = self.discounts.last()
        if last_product_discount:
            return self.price - ((last_product_discount.discount / 100) * self.price)
        return self.price

    def discounted_price(self):
        discount = self.get_current_discount()
        if discount:
            return self.price * (1 - discount.discount / 100)
        return self.price

    def has_discount(self):
        return self.get_current_discount() is not None

    def images(self):
        return self.images.all()

    def __str__(self):
        return self.name

    @staticmethod
    def generate_unique_book_token():
        """Generate a unique token for this product (64 hex chars)."""
        while True:
            token = uuid.uuid4().hex + uuid.uuid4().hex
            if not Product.objects.filter(book_token=token).exists():
                return token

    def save(self, *args, **kwargs):
        # Always (re)generate token on create and update.
        self.book_token = self.generate_unique_book_token()

        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            # Force persistence of regenerated token even when callers restrict update_fields.
            kwargs['update_fields'] = set(update_fields) | {'book_token'}

        # Validate unique product name per subject, teacher, and year
        self.validate_unique_product_name()
        
        # Save first to get the ID if this is a new product
        is_new = not self.pk
        super().save(*args, **kwargs)
        
        # Generate product_number after saving to ensure we have an ID
        if is_new and not self.product_number:
            self.product_number = f"{settings.ACTIVE_SITE_NAME}-{self.id}"
            # Update only the product_number field to avoid infinite recursion
            Product.objects.filter(pk=self.pk).update(product_number=self.product_number)
    
    def validate_unique_product_name(self):
        """Ensure product name is unique per subject, teacher, and year combination"""
        from django.core.exceptions import ValidationError
        
        # Build the query to check for duplicates
        query = Product.objects.filter(
            name=self.name,
            subject=self.subject,
            teacher=self.teacher,
            year=self.year
        )
        
        # Exclude current instance if updating
        if self.pk:
            query = query.exclude(pk=self.pk)
        
        # Check if duplicate exists
        if query.exists():
            error_parts = []
            if self.subject:
                error_parts.append(f"subject '{self.subject.name}'")
            if self.teacher:
                error_parts.append(f"teacher '{self.teacher.name}'")
            if self.year:
                error_parts.append(f"year '{self.get_year_display()}'")
            
            error_msg = f"A product with name '{self.name}' already exists for {', '.join(error_parts) if error_parts else 'this combination'}."
            raise ValidationError({'name': error_msg})

    class Meta:
        ordering = ['-date_added']


class BookPublishRequest(models.Model):
    name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=30, db_index=True)
    bio = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=20,
        choices=BOOK_PUBLISH_REQUEST_STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    notes = models.TextField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checked_book_publish_requests'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.phone_number}"
        
class PackageProduct(models.Model):
    """Model to store the relationship between package products and their related book products."""
    package_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='package_products',
        limit_choices_to={'type': 'package'},
        help_text="The package product"
    )
    related_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='in_packages',
        limit_choices_to={'type': 'book'},
        help_text="The book product included in the package"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ['package_product', 'related_product']
        verbose_name = 'Package Product'
        verbose_name_plural = 'Package Products'

    def __str__(self):
        return f"{self.package_product.name} -> {self.related_product.name}"

    def clean(self):
        """Validate that package_product is a package and related_product is a book."""
        if self.package_product and self.package_product.type != 'package':
            raise ValidationError({'package_product': 'Must be a package type product.'})
        if self.related_product and self.related_product.type != 'book':
            raise ValidationError({'related_product': 'Must be a book type product.'})
        if self.package_product and self.related_product and self.package_product.id == self.related_product.id:
            raise ValidationError('A product cannot be related to itself.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class SpecialProduct(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='special_products'
    )
    special_image = models.ImageField(
        upload_to='special_products/',
        max_length=512,
        null=True,
        blank=True
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Ordering priority (higher numbers come first)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Show this special product"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order', '-created_at']
        verbose_name = 'Special Product'
        verbose_name_plural = 'Special Products'

    def __str__(self):
        return f"Special: {self.product.name}"
    
class BestProduct(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='best_products'
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Ordering priority (higher numbers come first)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Show this product"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order', '-created_at']


    def __str__(self):
        return self.product.name

class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='product_images/')
    created_at = models.DateTimeField(default=timezone.now)  

    class Meta:
        ordering = ['-created_at']  

    def __str__(self):
        return f"Image for {self.product.name}"

class PillItem(models.Model):
    pill = models.ForeignKey('Pill', on_delete=models.CASCADE, null=True, blank=True, related_name='pill_items')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pill_items', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='pill_items')
    status = models.CharField(choices=PILL_STATUS_CHOICES, max_length=2, null=True, blank=True)
    date_added = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    price_at_sale = models.FloatField(null=True, blank=True)
    date_sold = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-date_added']
        unique_together = ['user', 'product', 'status', 'pill']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['date_sold']),
            models.Index(fields=['product', 'status']),
        ]

    def save(self, *args, **kwargs):
        # Set date_sold when status changes to 'paid' or 'done'
        if self.status == 'p' and not self.date_sold:
            self.date_sold = timezone.now()
            
        # Set prices if not already set
        if self.status == 'p' and not self.price_at_sale:
            self.price_at_sale = self.product.discounted_price()
            
        super().save(*args, **kwargs)

class Pill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pills')
    items = models.ManyToManyField(PillItem, related_name='pills')
    status = models.CharField(choices=PILL_STATUS_CHOICES, max_length=2, default='i')
    date_added = models.DateTimeField(auto_now_add=True)
    coupon = models.ForeignKey('CouponDiscount', on_delete=models.SET_NULL, null=True, blank=True, related_name='pills')
    coupon_discount = models.FloatField(default=0.0)  # Stores discount amount
    pill_number = models.CharField(max_length=20, editable=False, unique=True, default=generate_pill_number)
    
    # Shake-out fields (replacing Fawaterak)
    shakeout_invoice_id = models.CharField(max_length=255, null=True, blank=True, help_text="Shake-out invoice ID")
    shakeout_invoice_ref = models.CharField(max_length=255, null=True, blank=True, help_text="Shake-out invoice reference")
    shakeout_data = models.JSONField(null=True, blank=True, help_text="Shake-out invoice response data")
    shakeout_created_at = models.DateTimeField(null=True, blank=True, help_text="When the Shake-out invoice was created")
    
    # EasyPay fields
    easypay_invoice_uid = models.CharField(max_length=255, null=True, blank=True, help_text="EasyPay invoice UID")
    easypay_invoice_sequence = models.CharField(max_length=255, null=True, blank=True, help_text="EasyPay invoice sequence")
    easypay_fawry_ref = models.CharField(max_length=255, null=True, blank=True, help_text="EasyPay Fawry reference")
    easypay_data = models.JSONField(null=True, blank=True, help_text="EasyPay invoice response data")
    easypay_created_at = models.DateTimeField(null=True, blank=True, help_text="When the EasyPay invoice was created")
    
    # Payment gateway tracking
    payment_gateway = models.CharField(
        max_length=20,
        choices=PAYMENT_GATEWAY_CHOICES,
        null=True,
        blank=True,
        help_text="Which payment gateway was used for this pill"
    )

    # Gift codes assigned to this pill after a successful payment.
    code = models.JSONField(
        default=list,
        blank=True,
        help_text="Gift codes assigned to the pill once the payment is confirmed.",
    )

    def save(self, *args, **kwargs):
        if not self.pill_number:
            self.pill_number = generate_pill_number()

        is_new = not self.pk
        previous_status = None
        if not is_new:
            previous_status = Pill.objects.filter(pk=self.pk).values_list('status', flat=True).first()

        super().save(*args, **kwargs)

        # For new orders, sync status to items
        if is_new:
            for item in self.items.all():
                item.status = self.status
                if self.status == 'p' and not item.date_sold:
                    item.date_sold = timezone.now()
                if self.status == 'p' and not item.price_at_sale:
                    item.price_at_sale = item.product.discounted_price()
                item.save()

        # When pill status becomes 'p', update all pill items to 'p' as well
        if self.status == 'p' and (is_new or previous_status != 'p'):
            for item in self.items.all():
                item.status = 'p'
                if not item.date_sold:
                    item.date_sold = timezone.now()
                if not item.price_at_sale:
                    item.price_at_sale = item.product.discounted_price()
                item.save(update_fields=['status', 'date_sold', 'price_at_sale'])
            self.grant_purchased_books()

    def items_subtotal(self):
        """Return the subtotal for the pill using current discounted product prices."""
        total = 0.0
        items = self._items_for_total()
        for item in items:
            product = getattr(item, 'product', None)
            if not product:
                continue
            price = self._discounted_product_price(product)
            if price is None:
                price = product.price or 0.0
            total += float(price)
        return total

    def _items_for_total(self):
        prefetched_items = getattr(self, '_prefetched_objects_cache', {}).get('items')
        if prefetched_items is not None:
            return prefetched_items

        return self.items.select_related(
            'product',
            'product__subject',
            'product__teacher',
            'product__teacher__user',
        ).prefetch_related(
            Prefetch(
                'product__discounts',
                queryset=Discount.objects.filter(
                    is_active=True,
                    discount_start__lte=timezone.now(),
                    discount_end__gte=timezone.now(),
                ).order_by('-discount', '-discount_end'),
                to_attr='prefetched_active_discounts',
            )
        ).all()

    def _discounted_product_price(self, product):
        prefetched_discounts = getattr(product, 'prefetched_active_discounts', None)
        if prefetched_discounts is not None:
            discount = prefetched_discounts[0] if prefetched_discounts else None
            if discount:
                return product.price * (1 - discount.discount / 100)
            return product.price

        return product.discounted_price()

    def final_price(self):
        subtotal = self.items_subtotal()
        discount = float(self.coupon_discount or 0.0)
        return round(max(0.0, float(subtotal) - discount), 2)

    def check_all_items_availability(self):
        """Digital products are always available, so mark everything as in stock."""
        total_items = self.items.count()
        return {
            'all_available': True,
            'problem_items': [],
            'total_items': total_items,
            'problem_items_count': 0
        }

    def grant_purchased_books(self, purchase_method: str = 'user_paid'):
        from .models import PurchasedBook

        items = self.items.select_related('product').order_by('id')
        pill_codes = []
        for item in items:
            product = getattr(item, 'product', None)
            if not product:
                continue

            purchased_book = PurchasedBook.objects.filter(
                user=self.user,
                pill=self,
                product=product,
            ).first()
            assigned_code = purchased_book.code if purchased_book and purchased_book.code else None

            if purchase_method == 'user_paid' and not assigned_code:
                assigned_code = self._consume_gift_code(product)

            defaults = {
                'product_name': product.name,
                'pill_item': item,
                'purchase_method': purchase_method,
            }
            if assigned_code:
                defaults['code'] = assigned_code

            # Create PurchasedBook for the product (book or package)
            purchased_book, _ = PurchasedBook.objects.update_or_create(
                user=self.user,
                pill=self,
                product=product,
                defaults=defaults,
            )

            if purchased_book.code:
                pill_codes.append(purchased_book.code)

        self._sync_code_list(pill_codes)

    def send_payment_notification(self):
        """Notify the user that payment succeeded. Sends SMS to user.username (phone number) with deeplink."""
        from django.urls import reverse

        # Use username as phone number
        phone = self.user.username
        if not phone:
            logger.info("No username/phone on file for user %s; skipping payment notification.", self.user_id)
            return

        try:
            # Build deeplink URL
            deeplink_path = reverse('products:deeplink', args=['mybooks'])
            # deeplink_url = f"{settings.SITE_URL}{deeplink_path}"
            deeplink_url = settings.DEEPLINK_URL

            # Prepare SMS message
            message = (
                f"الدفع تم بنجاح\n\n"
                f"لعرض كتبك\n"
                f"{deeplink_url}"
            )

            # If gift codes were assigned to this pill, append them to the SMS body.
            gift_codes = self._code_list()
            if gift_codes:
                gift_code_lines = "\n".join(
                    f"{index}. {code}"
                    for index, code in enumerate(gift_codes, start=1)
                )
                message = f"{message}\n\nأكواد الهدية:\n{gift_code_lines}"

            response = send_beon_sms(
                phone_numbers=phone,
                message=message
            )

            if response['success']:
                logger.info("Payment notification sent to %s for pill %s", phone, self.pill_number)
            else:
                logger.warning("Failed to send payment notification for pill %s: %s", self.pill_number, response.get('error'))

        except Exception as exc:  # pragma: no cover - best effort notification
            logger.warning("Failed to send payment notification for pill %s: %s", self.pill_number, exc)

    def _consume_gift_code(self, product):
        """Atomically pick the first active GiftCode for a product and return its code.

        Returns ``None`` when there are no active GiftCode records for this product.
        """
        if not product:
            return None

        try:
            with transaction.atomic():
                gift_code = (
                    GiftCode.objects
                    .select_for_update(skip_locked=True)
                    .filter(product=product, is_active=True)
                    .order_by('id')
                    .first()
                )
                if not gift_code:
                    return None

                gift_code.is_active = False
                gift_code.save(update_fields=['is_active'])
                return gift_code.code
        except Exception:
            # ``select_for_update`` is not supported on all databases (e.g. SQLite);
            # fall back to a plain lookup.
            gift_code = (
                GiftCode.objects
                .filter(product=product, is_active=True)
                .order_by('id')
                .first()
            )

        if not gift_code:
            return None

        updated = GiftCode.objects.filter(pk=gift_code.pk, is_active=True).update(is_active=False)
        if not updated:
            return None
        return gift_code.code

    def _code_list(self):
        if isinstance(self.code, list):
            return [str(code) for code in self.code if code]
        if self.code:
            return [str(self.code)]
        return []

    def _sync_code_list(self, codes):
        codes = [str(code) for code in codes if code]
        if self.pk and self._code_list() != codes:
            self.code = codes
            Pill.objects.filter(pk=self.pk).update(code=codes)

    @property
    def shakeout_payment_url(self):
        if self.shakeout_data:
            return self.shakeout_data.get('payment_url') or self.shakeout_data.get('url')
        return None

    @property
    def easypay_payment_url(self):
        if self.easypay_data:
            return self.easypay_data.get('payment_url')
        return None

    def is_easypay_invoice_expired(self):
        """EasyPay invoices don't expire for digital delivery, treat them as always fresh."""
        return False

    def is_shakeout_invoice_expired(self):
        """Shakeout invoices are also considered valid unless deleted; default to False."""
        return False

    class Meta:
        verbose_name_plural = 'Bills'
        ordering = ['-date_added']
        indexes = [
            models.Index(fields=['-date_added']),  # Primary ordering
            models.Index(fields=['status']),       # Status filtering
            models.Index(fields=['pill_number']),  # Unique lookups
            models.Index(fields=['user_id']),      # User filtering
            models.Index(fields=['date_added', 'status']),  # Composite for common filters
        ]

    def __str__(self):
        return f"Pill ID: {self.id} - Status: {self.get_status_display()} - Date: {self.date_added}"

class CouponDiscount(models.Model):
    coupon = models.CharField(max_length=100, blank=True, null=True, editable=False)
    discount_value = models.FloatField(null=True, blank=True)
    coupon_start = models.DateTimeField(null=True, blank=True)
    coupon_end = models.DateTimeField(null=True, blank=True)
    available_use_times = models.PositiveIntegerField(default=1)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    min_order_value = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        if not self.coupon:
            self.coupon = create_random_coupon()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.coupon

    class Meta:
        ordering = ['-created_at']

class Discount(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='discounts')
    discount = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    discount_start = models.DateTimeField()
    discount_end = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = f"Product: {self.product.name}" if self.product else "No Product"
        return f"{self.discount}% discount on {target}"

    def clean(self):
        if not self.product:
            raise ValidationError("Product must be set")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_currently_active(self):
        now = timezone.now()
        return self.is_active and self.discount_start <= now <= self.discount_end

 

class LovedProduct(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='loved_products',
        null=True,
        blank=True
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'product']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} loved by {self.user.username if self.user else 'anonymous'}"


class PurchasedBook(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchased_books')
    pill = models.ForeignKey(Pill, on_delete=models.CASCADE, related_name='purchased_books', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='purchased_books')
    pill_item = models.ForeignKey(PillItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchased_books')
    product_name = models.CharField(max_length=255, blank=True)
    code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Gift code selected for this purchased product.",
    )
    price_at_sale = models.FloatField(null=True, blank=True, help_text="Price at the time of purchase/assignment")
    purchase_method = models.CharField(
        max_length=20,
        choices=PURCHASE_METHOD_CHOICES,
        default='user_paid',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Auto-fill product_name from product if not provided
        if not self.product_name and self.product:
            self.product_name = self.product.name
        
        # Auto-fill price_at_sale if not provided
        if self.price_at_sale is None:
            if self.pill_item and self.pill_item.price_at_sale:
                # Use price from pill_item if available
                self.price_at_sale = self.pill_item.price_at_sale
            elif self.product:
                # Otherwise use current product price (discounted if applicable)
                self.price_at_sale = self.product.discounted_price() or self.product.price
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} - {self.user}"


def prepare_whatsapp_message(phone_number, pill):
    print(f"Preparing SMS message for phone number: {phone_number}")
    message = (
        f"مرحباً {pill.user.username}،\n\n"
        f"تم استلام طلبك بنجاح.\n\n"
        f"رقم الطلب: {pill.pill_number}\n"
    )
    response = send_beon_sms(
        phone_numbers=phone_number,
        message=message
    )
    return response


def generate_promo_code():
    """Generate a unique 10-digit numeric promo code (single)."""
    while True:
        code = ''.join(random.choices(string.digits, k=10))
        if not PromoCode.objects.filter(code=code).exists():
            return code


def generate_promo_codes_bulk(count):
    """Generate `count` unique 10-digit numeric promo codes without DB collisions."""
    existing = set(PromoCode.objects.values_list('code', flat=True))
    codes = set()
    while len(codes) < count:
        candidate = ''.join(random.choices(string.digits, k=10))
        if candidate not in existing and candidate not in codes:
            codes.add(candidate)
    return list(codes)


class PromoCode(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True)
    title = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        db_index=True,
        help_text="Batch label assigned at bulk-create time. All codes in the same batch share the same title.",
    )
    book = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='promo_codes',
        null=True,
        blank=True,
        help_text="The book this code grants access to. Null = general code (valid for any book).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    valid_from = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of validity window. Leave blank for no start restriction.",
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of validity window. Leave blank for no end restriction.",
    )
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='redeemed_promo_codes',
    )
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_promo_codes',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Promo Code'
        verbose_name_plural = 'Promo Codes'

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_promo_code()
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """Check whether the code is currently usable."""
        now = timezone.now()
        if not self.is_active:
            return False
        if self.is_used:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True


class GiftCode(models.Model):
    """Pool of product gift codes that get assigned once a matching pill is paid."""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='gift_codes',
        null=True,
        blank=False,
        help_text="Product this gift code belongs to.",
    )
    code = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique gift code that will be assigned to a paid pill for this product.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="When true, this code is still available to be assigned to a pill.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Gift Code'
        verbose_name_plural = 'Gift Codes'

    def __str__(self):
        return self.code

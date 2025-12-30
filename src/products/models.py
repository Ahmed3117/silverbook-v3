import random
import string
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from products.utils import send_whatsapp_message
from accounts.models import YEAR_CHOICES, User
from core import settings
from django.utils import timezone
from django.utils.html import format_html
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
]

PAYMENT_GATEWAY_CHOICES = [
    ('easypay', 'EasyPay'),
    ('shakeout', 'Shake-out'),
]

PRODUCT_TYPE_CHOICES = [
    ('book', 'Book'),
    ('package', 'Package'),
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

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)  
    class Meta:
        ordering = ['-created_at']  

    def __str__(self):
        return self.name

class SubCategory(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories')
    created_at = models.DateTimeField(default=timezone.now)  

    class Meta:
        ordering = ['-created_at']  
        verbose_name_plural = 'Sub Categories'

    def __str__(self):
        return f"{self.category.name} - {self.name}"

class Subject(models.Model):
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name
    
class Teacher(models.Model):
    name = models.CharField(max_length=150)
    bio = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='teachers/', null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teachers')
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
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name='products')
    sub_category = models.ForeignKey(SubCategory, on_delete=models.CASCADE, null=True, blank=True, related_name='products')
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
    
    # Metadata
    page_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of pages in the PDF"
    )
    file_size_mb = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="File size in MB"
    )
    language = models.CharField(
        max_length=2,
        choices=[('ar', 'Arabic'), ('en', 'English')],
        default='ar'
    )
    is_available = models.BooleanField(
        default=True,
        help_text="Whether this digital book is available for purchase"
    )
    
    def get_current_discount(self):
        """Returns the best active discount (either product or category level)"""
        now = timezone.now()
        product_discount = self.discounts.filter(
            is_active=True,
            discount_start__lte=now,
            discount_end__gte=now
        ).order_by('-discount').first()

        category_discount = None
        if self.category:
            category_discount = self.category.discounts.filter(
                is_active=True,
                discount_start__lte=now,
                discount_end__gte=now
            ).order_by('-discount').first()

        if product_discount and category_discount:
            return max(product_discount, category_discount, key=lambda d: d.discount)
        return product_discount or category_discount

    def price_after_product_discount(self):
        last_product_discount = self.discounts.last()
        if last_product_discount:
            return self.price - ((last_product_discount.discount / 100) * self.price)
        return self.price

    def price_after_category_discount(self):
        if self.category:  
            last_category_discount = self.category.discounts.last()
            if last_category_discount:
                return self.price - ((last_category_discount.discount / 100) * self.price)
        return self.price

    def discounted_price(self):
        discount = self.get_current_discount()
        if discount:
            return self.price * (1 - discount.discount / 100)
        return self.price

    def has_discount(self):
        return self.get_current_discount() is not None

    def main_image(self):
        """Get the main product image from ProductImage"""
        images = self.images.all()
        if images.exists():
            return random.choice(images).image
        return None

    def images(self):
        return self.images.all()

    def number_of_ratings(self):
        return self.ratings.count()

    def average_rating(self):
        ratings = self.ratings.all()
        if ratings.exists():
            return round(sum(rating.star_number for rating in ratings) / ratings.count(), 1)
        return 0.0

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
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

class ProductDescription(models.Model):
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='descriptions'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = 'Product Description'
        verbose_name_plural = 'Product Descriptions'

    def __str__(self):
        return f"{self.title} - {self.product.name}"

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
        for item in self.items.select_related('product').all():
            product = getattr(item, 'product', None)
            if not product:
                continue
            price = product.discounted_price()
            if price is None:
                price = product.price or 0.0
            total += float(price)
        return total

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

    def grant_purchased_books(self):
        from .models import PurchasedBook

        items = self.items.select_related('product').all()
        for item in items:
            product = getattr(item, 'product', None)
            if not product:
                continue

            # Create PurchasedBook for the product (book or package)
            PurchasedBook.objects.update_or_create(
                user=self.user,
                pill=self,
                product=product,
                defaults={
                    'product_name': product.name,
                    'pill_item': item
                }
            )

    def send_payment_notification(self):
        """Notify the user that payment succeeded. Currently sends WhatsApp if parent_phone exists."""
        phone = getattr(self.user, 'parent_phone', None)
        if not phone:
            logger.info("No parent_phone on file for user %s; skipping payment notification.", self.user_id)
            return

        try:
            prepare_whatsapp_message(phone, self)
        except Exception as exc:  # pragma: no cover - best effort notification
            logger.warning("Failed to send payment notification for pill %s: %s", self.pill_number, exc)

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

class Rating(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='ratings'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    star_number = models.IntegerField()
    review = models.CharField(max_length=300, default="No review comment")
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.star_number} stars for {self.product.name} by {self.user.username}"

    def star_ranges(self):
        return range(int(self.star_number)), range(5 - int(self.star_number))

    class Meta:
        ordering = ['-date_added']
        unique_together = ('product', 'user')

class Discount(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='discounts')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name='discounts')
    discount = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    discount_start = models.DateTimeField()
    discount_end = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = f"Product: {self.product.name}" if self.product else f"Category: {self.category.name}"
        return f"{self.discount}% discount on {target}"

    def clean(self):
        if not self.product and not self.category:
            raise ValidationError("Either product or category must be set")
        if self.product and self.category:
            raise ValidationError("Cannot set both product and category")

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
    price_at_sale = models.FloatField(null=True, blank=True, help_text="Price at the time of purchase/assignment")
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
    print(f"Preparing WhatsApp message for phone number: {phone_number}")
    message = (
        f"مرحباً {pill.user.username}،\n\n"
        f"تم استلام طلبك بنجاح.\n\n"
        f"رقم الطلب: {pill.pill_number}\n"
    )
    send_whatsapp_message(
        phone_number=phone_number,
        message=message
    )

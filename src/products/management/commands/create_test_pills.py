"""
Create test pills matching the failed pills structure from production
Usage: python manage.py create_test_pills
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from products.models import (
    Pill, PillItem, PillAddress, User, Product, 
    GOVERNMENT_CHOICES, PAYMENT_CHOICES
)
from decimal import Decimal


class Command(BaseCommand):
    help = 'Create test pills matching failed pills structure from production'

    def handle(self, *args, **options):
        # Get user and product
        try:
            user = User.objects.get(id=2)
            self.stdout.write(self.style.SUCCESS(f'✅ Found user: {user.username} (ID: {user.id})'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ User with ID 2 not found'))
            return

        try:
            pill_item = PillItem.objects.get(id=33)
            product = pill_item.product
            self.stdout.write(self.style.SUCCESS(f'✅ Found product: {product.name} (ID: {product.id})'))
        except PillItem.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ PillItem with ID 33 not found'))
            return

        # Test data matching the failed pills from Excel
        test_pills_data = [
            {
                'customer_name': 'سلمى محمد',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'قرية العصافرة مركز المطرية دقهلية الطريق الزراعي شارع عزبة ناصر أمام صيدلية الدكتورة فايقة بحيري',
                'city': 'المنصورة',
                'government': 'da',  # Dakahleya
                'quantity': 1,
            },
            {
                'customer_name': 'ميار ياسر',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': '٣٨_شارع جبريل سلامه_عزبه الصعايده',
                'city': 'امبابة',
                'government': 'gz',  # Giza
                'quantity': 2,
            },
            {
                'customer_name': 'جني محمد',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'الشيخ ذايد _عماره 168',
                'city': 'جمصة',
                'government': 'da',  # Dakahleya
                'quantity': 1,
            },
            {
                'customer_name': 'Mohesen Ghazy',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'اخر فيصل كفر غطاطي شارع الترعه أمام سوبر ماركت الدربي',
                'city': 'كفر غطاطي',
                'government': 'gz',  # Giza
                'quantity': 1,
            },
            {
                'customer_name': 'حنان سعد',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'القاهره التجمع التالت القطاميه مساكن القاهره عماره خمسه شقه ثمانيه',
                'city': 'القطامية',
                'government': 'ca',  # Cairo
                'quantity': 1,
            },
            {
                'customer_name': 'جنا - سعيد',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'email': 'test@gmail.com',
                'address': 'شارع مسجد الرحمن متفرع من نصر نصار امبابه الجيزه',
                'city': 'امبابة',
                'government': 'gz',  # Giza
                'quantity': 2,
            },
            {
                'customer_name': 'منة عادل',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'الهانوفيل شارع ابراهيم العوامي المتفرع من شارع رضوان بجوار مسدج عمر بن عبد العزيز',
                'city': 'العجمي',
                'government': 'al',  # Alexandria
                'quantity': 1,
            },
            {
                'customer_name': 'sama islam',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'شارع احمد رجب عزبة النخل الغربية',
                'city': 'عزبة النخل',
                'government': 'ca',  # Cairo
                'quantity': 1,
            },
            {
                'customer_name': 'ملك عريبي',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'قرية العطف مركز الواسطي أمام مسجد أحمد حسن',
                'city': 'الواسطى',
                'government': 'bs',  # Bani-Sweif
                'quantity': 1,
            },
            {
                'customer_name': 'حازم ابراهيم',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'زقاق عبد الفتاح بجوار الباشا مول( اسواق البركة حاليا)',
                'city': 'بكوس',
                'government': 'al',  # Alexandria
                'quantity': 1,
            },
            {
                'customer_name': 'ملك عريبي',
                'phone1': '01012345678',
                'phone2': '01512345678',
                'address': 'قرية العطف مركز الواسطي',
                'city': 'الواسطى',
                'government': 'bs',  # Bani-Sweif
                'quantity': 1,
            },
        ]

        created_pills = []
        
        for idx, pill_data in enumerate(test_pills_data, 1):
            try:
                # Create pill
                pill = Pill.objects.create(
                    user=user,
                    status='i',  # Initial status
                    paid=False,  # Not paid yet
                )
                
                # Create pill item using the existing product
                new_pill_item = PillItem.objects.create(
                    pill=pill,
                    user=user,
                    product=product,
                    quantity=pill_data['quantity'],
                    size=pill_item.size,
                    color=pill_item.color,
                    status='i',
                )
                
                # Add item to pill
                pill.items.add(new_pill_item)
                
                # Create pill address
                pill_address = PillAddress.objects.create(
                    pill=pill,
                    name=pill_data['customer_name'],
                    email=pill_data.get('email', ''),
                    phone=pill_data['phone1'],
                    address=pill_data['address'],
                    government=pill_data['government'],
                    city=pill_data['city'],
                    pay_method='c',  # Cash on delivery
                )
                
                # Update user phone numbers if not set
                if not user.phone:
                    user.phone = pill_data['phone2']
                    user.save(update_fields=['phone'])
                
                created_pills.append({
                    'pill_number': pill.pill_number,
                    'customer': pill_data['customer_name'],
                    'government': pill_data['government'],
                    'city': pill_data['city'],
                    'quantity': pill_data['quantity'],
                })
                
                self.stdout.write(self.style.SUCCESS(
                    f'✅ Created pill #{idx}: {pill.pill_number} - {pill_data["customer_name"]} '
                    f'({pill_data["government"]} - {pill_data["city"]})'
                ))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'❌ Failed to create pill #{idx}: {str(e)}'
                ))
                continue
        
        # Summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS(f'\n✅ Created {len(created_pills)} test pills\n'))
        self.stdout.write('=' * 80)
        
        # Display created pills
        self.stdout.write('\n📋 Created Pills Summary:\n')
        for i, pill in enumerate(created_pills, 1):
            gov_name = dict(GOVERNMENT_CHOICES).get(pill['government'], pill['government'])
            self.stdout.write(
                f"{i}. Pill: {pill['pill_number']} | "
                f"Customer: {pill['customer']} | "
                f"Gov: {gov_name} ({pill['government']}) | "
                f"City: {pill['city']} | "
                f"Qty: {pill['quantity']}"
            )
        
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('\n✅ All test pills created successfully!\n'))
        self.stdout.write('=' * 80)
        self.stdout.write('\n📝 Next Steps:')
        self.stdout.write('1. Go to Django Admin → Pills')
        self.stdout.write('2. Filter for status = "Initial" (these are the test pills)')
        self.stdout.write('3. Mark them as paid (this will trigger Khazenly order creation)')
        self.stdout.write('4. Check logs for any validation errors')
        self.stdout.write('\n' + '=' * 80 + '\n')

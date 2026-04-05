from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0010_product_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='promocode',
            name='title',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Batch label assigned at bulk-create time. All codes in the same batch share the same title.',
                max_length=200,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='promocode',
            name='book',
            field=models.ForeignKey(
                blank=True,
                help_text='The book this code grants access to. Null = general code (valid for any book).',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='promo_codes',
                to='products.product',
            ),
        ),
    ]

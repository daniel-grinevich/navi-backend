# Generated by Django 5.1.4 on 2024-12-27 22:05

import django.core.validators
import django.db.models.deletion
import imagekit.models.fields
import navi_backend.core.validators
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Option',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(db_index=True, help_text='Unqiue name of option', max_length=50, unique=True, verbose_name='Name')),
                ('slug', models.SlugField(help_text='URL-friendly version of name', max_length=70, unique=True, verbose_name='Slug')),
                ('price', models.DecimalField(decimal_places=2, help_text='Price of option in dollars (between $99999-$0)', max_digits=8, validators=[django.core.validators.MaxValueValidator(Decimal('99999.990000000005238689482212066650390625')), django.core.validators.MinValueValidator(Decimal('0.01000000000000000020816681711721685132943093776702880859375'))], verbose_name='Price')),
                ('description', models.CharField(help_text='Short description of option', max_length=100, verbose_name='Description')),
                ('body', models.TextField(help_text='Detailed descriptionof option', verbose_name='Body')),
                ('status', models.CharField(choices=[('A', 'Active'), ('I', 'Inactive'), ('D', 'Draft'), ('R', 'Archived')], db_index=True, default='A', help_text='Option availability', max_length=1, verbose_name='Status')),
                ('selected_count', models.PositiveIntegerField(default=0, editable=False, help_text='Count of how many times option was chosen', verbose_name='Selected count')),
                ('version', models.PositiveIntegerField(default=1, editable=False, help_text='Internal version tracking', verbose_name='Version')),
                ('is_deleted', models.BooleanField(default=False, help_text='soft delete flag', verbose_name='deleted')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='deleted at')),
                ('last_modified_ip', models.GenericIPAddressField(editable=False, null=True, verbose_name='last modified IP')),
                ('last_modified_user_agent', models.CharField(editable=False, max_length=200, null=True, verbose_name='last modified user agent')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(db_index=True, help_text='Unique name of the product', max_length=50, unique=True, verbose_name='Name')),
                ('slug', models.SlugField(help_text='URL-friendly version of the name', max_length=100, unique=True, verbose_name='Slug')),
                ('price', models.DecimalField(decimal_places=2, help_text='Product price in dollars max $99,999.99', max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0.01')), django.core.validators.MaxValueValidator(Decimal('99999.99'))])),
                ('description', models.CharField(help_text='Short description for product listings', max_length=100, verbose_name='Description')),
                ('body', models.TextField(help_text='Detailed product description', verbose_name='Body')),
                ('status', models.CharField(choices=[('A', 'Active'), ('I', 'Inactive'), ('D', 'Draft'), ('R', 'Archived')], db_index=True, default='A', help_text='Product availability status', max_length=1, verbose_name='Status')),
                ('image', imagekit.models.fields.ProcessedImageField(help_text='Product image (max 5MB, JPEG/PNG)', upload_to='product_images/%Y/%m/', validators=[navi_backend.core.validators.validate_image_size, navi_backend.core.validators.validate_image_extension], verbose_name='Image')),
                ('is_featured', models.BooleanField(db_index=True, default=False, verbose_name='featured')),
                ('view_count', models.PositiveIntegerField(default=0, editable=False, help_text='View count for product', verbose_name='View count')),
                ('version', models.PositiveIntegerField(default=1, editable=False, help_text='Internal version tracking', verbose_name='Version')),
                ('is_deleted', models.BooleanField(default=False, help_text='Soft delete flag', verbose_name='deleted')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='deleted at')),
                ('last_modified_ip', models.GenericIPAddressField(editable=False, null=True, verbose_name='last modified IP')),
                ('last_modified_user_agent', models.CharField(editable=False, max_length=200, null=True, verbose_name='last modified user agent')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Product',
                'verbose_name_plural': 'Products',
                'ordering': ['name'],
                'permissions': [('can_change_status', 'Can change product status'), ('can_feature_product', 'Can mark product as featured'), ('can_view_deleted', 'Can view deleted products')],
            },
        ),
        migrations.CreateModel(
            name='OptionSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=50, unique=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('options', models.ManyToManyField(related_name='option_sets', to='fakeapi.option')),
                ('updated_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_updated', to=settings.AUTH_USER_MODEL)),
                ('products', models.ManyToManyField(related_name='option_sets', to='fakeapi.product')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddIndex(
            model_name='option',
            index=models.Index(fields=['name'], name='fakeapi_opt_name_512b43_idx'),
        ),
        migrations.AddIndex(
            model_name='option',
            index=models.Index(fields=['slug'], name='fakeapi_opt_slug_62ac49_idx'),
        ),
        migrations.AddIndex(
            model_name='option',
            index=models.Index(fields=['status'], name='fakeapi_opt_status_c148f3_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['name'], name='fakeapi_pro_name_a68f8c_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['price'], name='fakeapi_pro_price_3e22cb_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['status'], name='fakeapi_pro_status_444c77_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['created_at'], name='fakeapi_pro_created_468a90_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['-view_count'], name='fakeapi_pro_view_co_72d5d6_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_deleted'], name='fakeapi_pro_is_dele_568156_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_featured', 'status'], name='fakeapi_pro_is_feat_9585dd_idx'),
        ),
    ]

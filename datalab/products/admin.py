from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'price', 'quantity', 'category','tx_date')
    list_filter = ('category','tx_date')
    search_fields = ('sku','name')
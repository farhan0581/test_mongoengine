# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from testing.models import ProductQuote
from django_mongoengine import mongo_admin

@mongo_admin.register(ProductQuote)
class ProductQuoteAdmin(mongo_admin.DocumentAdmin):
    list_display = ('productLine', 'brandName', 'productName', 'quote_price',
    				'input_params', 'tagCategory', 'device', 'create_date')
    actions = None
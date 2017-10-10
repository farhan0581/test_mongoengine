# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import datetime
from django_mongoengine import Document, EmbeddedDocument
from django_mongoengine.fields import StringField, DateTimeField, IntField

class ProductQuote(Document):
    # id = StringField(max_length=255, verbose_name="id", primary_key=True)
    input_params = StringField(max_length=255)
    quote_price = IntField()
    # create_date = DateTimeField(default=datetime.datetime.now)
    create_date = StringField(max_length=255)
    exp_id = IntField()
    deviceF = StringField(max_length=255)
    e_params = StringField(max_length=255)
    productId = IntField()
    brandId = IntField()
    productName = StringField(max_length=255)
    brandName = StringField(max_length=255)
    _class = StringField(max_length=255)
    productLine = StringField(max_length=255)
    ip_city = StringField(max_length=255)
    ip = StringField(max_length=255)
    input_params_map = StringField(max_length=255)
    tagCategory = StringField(max_length=255)
    device = StringField(max_length=255)
    # _id = StringField(max_length=255, verbose_name="_id", primary_key=True)
    tagExpId = IntField()
    tagProduct = StringField(max_length=255)
    e_params_map = StringField(max_length=255)

    meta = {
        'collection': 'product_quote'
    }
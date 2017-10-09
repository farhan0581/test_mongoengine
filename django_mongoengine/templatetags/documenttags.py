from django.template import Library
from django.db.models.fields import FieldDoesNotExist

from django_mongoengine.forms.utils import patch_document
from django_mongoengine.mongo_admin.util import label_for_field

import datetime
import decimal
from collections import defaultdict

from django.contrib.auth import get_permission_codename
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.constants import LOOKUP_SEP
from django.db.models.deletion import Collector
from django.db.models.sql.constants import QUERY_TERMS
from django.forms.utils import pretty_name
from django.urls import NoReverseMatch, reverse
from django.utils import formats, six, timezone
from django.utils.encoding import force_str, force_text, smart_text
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import (
    override as translation_override, ungettext,
)
from django.core.exceptions import ObjectDoesNotExist
from django.urls import NoReverseMatch
from django.contrib.admin.views.main import (
    ALL_VAR, ORDER_VAR, PAGE_VAR, SEARCH_VAR,
)
from django.utils.safestring import mark_safe
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters

register = Library()

def lookup_field(name, obj, model_admin=None):
    opts = obj._meta
    try:
        f = _get_non_gfk_field(opts, name)
    except (FieldDoesNotExist, FieldIsAForeignKeyColumnName):
        # For non-field values, the value is either a method, property or
        # returned via a callable.
        if callable(name):
            attr = name
            value = attr(obj)
        elif (model_admin is not None and
                hasattr(model_admin, name) and
                not name == '__str__' and
                not name == '__unicode__'):
            attr = getattr(model_admin, name)
            value = attr(obj)
        else:
            attr = getattr(obj, name)
            if callable(attr):
                value = attr()
            else:
                value = attr
        f = None
    else:
        attr = None
        value = getattr(obj, name)
    return f, attr, value

def items_for_result(cl, result, form):
    """
    Generates the actual list of data.
    """

    def link_in_col(is_first, field_name, cl):
        if cl.list_display_links is None:
            return False
        if is_first and not cl.list_display_links:
            return True
        return field_name in cl.list_display_links

    first = True
    pk = cl.lookup_opts.pk.attname
    for field_index, field_name in enumerate(cl.list_display):
        empty_value_display = cl.model_admin.get_empty_value_display()
        row_classes = ['field-%s' % _coerce_field_name(field_name, field_index)]
        try:
            f, attr, value = lookup_field(field_name, result, cl.model_admin)
        except ObjectDoesNotExist:
            result_repr = empty_value_display
        else:
            empty_value_display = getattr(attr, 'empty_value_display', empty_value_display)
            if f is None or f.auto_created:
                if field_name == 'action_checkbox':
                    row_classes = ['action-checkbox']
                allow_tags = getattr(attr, 'allow_tags', False)
                boolean = getattr(attr, 'boolean', False)
                result_repr = display_for_value(value, empty_value_display, boolean)
                if allow_tags:
                    warnings.warn(
                        "Deprecated allow_tags attribute used on field {}. "
                        "Use django.utils.html.format_html(), format_html_join(), "
                        "or django.utils.safestring.mark_safe() instead.".format(field_name),
                        RemovedInDjango20Warning
                    )
                    result_repr = mark_safe(result_repr)
                if isinstance(value, (datetime.date, datetime.time)):
                    row_classes.append('nowrap')
            else:
                if hasattr(f, 'remote_field'):
                    if isinstance(f.remote_field, models.ManyToOneRel):
                        field_val = getattr(result, f.name)
                        if field_val is None:
                            result_repr = empty_value_display
                        else:
                            result_repr = field_val
                    else:
                        result_repr = display_for_field(value, f, empty_value_display)
                else:
                    result_repr = getattr(result, f.name)
                
                if isinstance(f, (models.DateField, models.TimeField, models.ForeignKey)):
                    row_classes.append('nowrap')
        
        if force_text(result_repr) == '':
            result_repr = mark_safe('&nbsp;')
        
        row_class = mark_safe(' class="%s"' % ' '.join(row_classes))
        # If list_display_links not defined, add the link tag to the first field
        if link_in_col(first, field_name, cl):
            table_tag = 'th' if first else 'td'
            first = False

            # Display link to the result's change_view if the url exists, else
            # display just the result's representation.
            try:
                url = cl.url_for_result(result)
            except NoReverseMatch:
                link_or_text = result_repr
            else:
                url = add_preserved_filters({'preserved_filters': cl.preserved_filters, 'opts': cl.opts}, url)
                # Convert the pk to something that can be used in Javascript.
                # Problem cases are long ints (23L) and non-ASCII strings.
                if cl.to_field:
                    attr = str(cl.to_field)
                else:
                    attr = pk
                value = result.serializable_value(attr)
                link_or_text = format_html(
                    '<a href="{}"{}>{}</a>',
                    url,
                    format_html(
                        ' data-popup-opener="{}"', value
                    ) if cl.is_popup else '',
                    result_repr)

            yield format_html('<{}{}>{}</{}>',
                              table_tag,
                              row_class,
                              link_or_text,
                              table_tag)
        else:
            # By default the fields come from ModelAdmin.list_editable, but if we pull
            # the fields out of the form instead of list_editable custom admins
            # can provide fields on a per request basis
            if (form and field_name in form.fields and not (
                    field_name == cl.model._meta.pk.name and
                    form[cl.model._meta.pk.name].is_hidden)):
                bf = form[field_name]
                result_repr = mark_safe(force_text(bf.errors) + force_text(bf))
            yield format_html('<td{}>{}</td>', row_class, result_repr)
    if form and not form[cl.model._meta.pk.name].is_hidden:
        yield format_html('<td>{}</td>', force_text(form[cl.model._meta.pk.name]))


class ResultList(list):
    # Wrapper class used to return items in a list_editable
    # changelist, annotated with the form object for error
    # reporting purposes. Needed to maintain backwards
    # compatibility with existing admin templates.
    def __init__(self, form, *items):
        self.form = form
        super(ResultList, self).__init__(*items)


def result_hidden_fields(cl):
    if cl.formset:
        for res, form in zip(cl.result_list, cl.formset.forms):
            if form[cl.model._meta.pk.name].is_hidden:
                yield mark_safe(force_text(form[cl.model._meta.pk.name]))

class FieldIsAForeignKeyColumnName(Exception):
    """A field is a foreign key attname, i.e. <FK>_id."""
    pass

def _coerce_field_name(field_name, field_index):
    """
    Coerce a field_name (which may be a callable) to a string.
    """
    if callable(field_name):
        if field_name.__name__ == '<lambda>':
            return 'lambda' + str(field_index)
        else:
            return field_name.__name__
    return field_name

def _get_non_gfk_field(opts, name):
    """
    For historical reasons, the admin app relies on GenericForeignKeys as being
    "not found" by get_field(). This could likely be cleaned up.

    Reverse relations should also be excluded as these aren't attributes of the
    model (rather something like `foo_set`).
    """
    field = opts.get_field(name)
    if hasattr(field, 'is_relation'):
        if (field.is_relation and
                # Generic foreign keys OR reverse relations
                ((field.many_to_one and not field.related_model) or field.one_to_many)):
            raise FieldDoesNotExist()

    # Avoid coercing <FK>_id fields to FK
        if field.is_relation and not field.many_to_many and hasattr(field, 'attname') and field.attname == name:
            raise FieldIsAForeignKeyColumnName()
    return field


def result_headers(cl):
    """
    Generates the list column headers.
    """
    ordering_field_columns = cl.get_ordering_field_columns()
    for i, field_name in enumerate(cl.list_display):
        text, attr = label_for_field(
            field_name, cl.model,
            model_admin=cl.model_admin,
            return_attr=True
        )
        if attr:
            field_name = _coerce_field_name(field_name, i)
            # Potentially not sortable

            # if the field is the action checkbox: no sorting and special class
            if field_name == 'action_checkbox':
                yield {
                    "text": text,
                    "class_attrib": mark_safe(' class="action-checkbox-column"'),
                    "sortable": False,
                }
                continue

            admin_order_field = getattr(attr, "admin_order_field", None)
            if not admin_order_field:
                # Not sortable
                yield {
                    "text": text,
                    "class_attrib": format_html(' class="column-{}"', field_name),
                    "sortable": False,
                }
                continue

        # OK, it is sortable if we got this far
        th_classes = ['sortable', 'column-{}'.format(field_name)]
        order_type = ''
        new_order_type = 'asc'
        sort_priority = 0
        sorted = False
        # Is it currently being sorted on?
        if i in ordering_field_columns:
            sorted = True
            order_type = ordering_field_columns.get(i).lower()
            sort_priority = list(ordering_field_columns).index(i) + 1
            th_classes.append('sorted %sending' % order_type)
            new_order_type = {'asc': 'desc', 'desc': 'asc'}[order_type]

        # build new ordering param
        o_list_primary = []  # URL for making this field the primary sort
        o_list_remove = []  # URL for removing this field from sort
        o_list_toggle = []  # URL for toggling order type for this field

        def make_qs_param(t, n):
            return ('-' if t == 'desc' else '') + str(n)

        for j, ot in ordering_field_columns.items():
            if j == i:  # Same column
                param = make_qs_param(new_order_type, j)
                # We want clicking on this header to bring the ordering to the
                # front
                o_list_primary.insert(0, param)
                o_list_toggle.append(param)
                # o_list_remove - omit
            else:
                param = make_qs_param(ot, j)
                o_list_primary.append(param)
                o_list_toggle.append(param)
                o_list_remove.append(param)

        if i not in ordering_field_columns:
            o_list_primary.insert(0, make_qs_param(new_order_type, i))

        yield {
            "text": text,
            "sortable": True,
            "sorted": sorted,
            "ascending": order_type == "asc",
            "sort_priority": sort_priority,
            "url_primary": cl.get_query_string({ORDER_VAR: '.'.join(o_list_primary)}),
            "url_remove": cl.get_query_string({ORDER_VAR: '.'.join(o_list_remove)}),
            "url_toggle": cl.get_query_string({ORDER_VAR: '.'.join(o_list_toggle)}),
            "class_attrib": format_html(' class="{}"', ' '.join(th_classes)) if th_classes else '',
        }

def serializable_value(self, field_name):
    """
    Returns the value of the field name for this instance. If the field is
    a foreign key, returns the id value, instead of the object. If there's
    no Field object with this name on the model, the model attribute's
    value is returned directly.

    Used to serialize a field's value (in the serializer, or form output,
    for example). Normally, you would just access the attribute directly
    and not use this method.
    """
    try:
        field = self._meta.get_field_by_name(field_name)[0]
    except FieldDoesNotExist:
        return getattr(self, field_name)
    return getattr(self, field.name)

def results(cl):
    """
    Just like the one from Django. Only we add a serializable_value method to
    the document, because Django expects it and mongoengine doesn't have it.
    """
    if cl.formset:
        for res, form in zip(cl.result_list, cl.formset.forms):
            patch_document(serializable_value, res)
            yield ResultList(form, items_for_result(cl, res, form))
    else:
        for res in cl.result_list:
            patch_document(serializable_value, res)
            yield ResultList(None, items_for_result(cl, res, None))

def document_result_list(cl):
    """
    Displays the headers and data list together
    """
    headers = list(result_headers(cl))
    try:
        num_sorted_fields = 0
        for h in headers:
            if h['sortable'] and h['sorted']:
                num_sorted_fields += 1
    except KeyError:
        pass

    return {'cl': cl,
            'result_hidden_fields': list(result_hidden_fields(cl)),
            'result_headers': headers,
            'num_sorted_fields': num_sorted_fields,
            'results': list(results(cl))}
result_list = register.inclusion_tag("admin/change_list_results.html")(document_result_list)

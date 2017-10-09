from django.contrib.admin import sites
from django.utils.text import capfirst
# from contextlib import suppress
from django.apps import apps
from mongoengine.base import TopLevelDocumentMetaclass
from django.urls import NoReverseMatch, reverse
from django_mongoengine.mongo_admin.options import DocumentAdmin
from django_mongoengine.forms.document_options import DocumentMetaWrapper
#from django_mongoengine.mongo_admin import actions

system_check_errors = []

class AdminSite(sites.AdminSite):
    index_template = "mongo_admin/index.html"

    def register(self, model_or_iterable, admin_class=None, **options):

        if isinstance(model_or_iterable, TopLevelDocumentMetaclass) and not admin_class:
            admin_class = DocumentAdmin

        if isinstance(model_or_iterable, TopLevelDocumentMetaclass):
            model_or_iterable._meta = DocumentMetaWrapper(model_or_iterable)
            model_or_iterable = [model_or_iterable]

        super(AdminSite, self).register(model_or_iterable, admin_class, **options)

    def unregister(self, model_or_iterable):
        if isinstance(model_or_iterable, TopLevelDocumentMetaclass):
            model_or_iterable = [model_or_iterable]

        super(AdminSite, self).unregister(model_or_iterable)

    def _build_app_dict(self, request, label=None):
        """
        Build the app dictionary. The optional `label` parameter filters models
        of a specific app.
        """
        app_dict = {}

        if label:
            models = {
                m: m_a for m, m_a in self._registry.items()
                if m._meta.app_label == label
            }
        else:
            models = self._registry

        for model, model_admin in models.items():
            app_label = model._meta.app_label
            # print model._meta
            has_module_perms = model_admin.has_module_permission(request)
            if not has_module_perms:
                continue

            perms = model_admin.get_model_perms(request)

            # Check whether user has any perm for this module.
            # If so, add the module to the model_list.
            if True not in perms.values():
                continue

            info = (app_label, model._meta.model_name)
            model_dict = {
                'name': capfirst(model._meta.verbose_name_plural),
                'object_name': model._meta.object_name,
                'perms': perms,
            }
            if perms.get('change'):
                try:
                    model_dict['admin_url'] = reverse('admin:%s_%s_changelist' % info, current_app=self.name)
                except NoReverseMatch:
                    return 'ERROR'
            if perms.get('add'):
                try:
                    model_dict['add_url'] = reverse('admin:%s_%s_add' % info, current_app=self.name)
                except NoReverseMatch:
                    return 'ERROR 2'

            if app_label in app_dict:
                app_dict[app_label]['models'].append(model_dict)
            else:
                app_dict[app_label] = {
                    'name': apps.get_app_config(app_label).verbose_name,
                    'app_label': app_label,
                    'app_url': reverse(
                        'admin:app_list',
                        kwargs={'app_label': app_label},
                        current_app=self.name,
                    ),
                    'has_module_perms': has_module_perms,
                    'models': [model_dict],
                }

        if label:
            return app_dict.get(label)
        return app_dict

# This global object represents the default admin site, for the common case.
# You can instantiate AdminSite in your own code to create a custom admin site.
site = AdminSite(name="mongoadmin")

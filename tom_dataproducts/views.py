from urllib.parse import urlparse
from io import StringIO

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.management import call_command
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.safestring import mark_safe
from django.views.generic import View, ListView
from django.views.generic.base import RedirectView
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView, DeleteView
from django.views.generic.edit import CreateView
from django_filters.views import FilterView
from guardian.shortcuts import get_objects_for_user

from .models import DataProduct, DataProductGroup, ReducedDatum
from .exceptions import InvalidFileFormatException
from .forms import AddProductToGroupForm, DataProductUploadForm
from .filters import DataProductFilter
from .data_processor import run_data_processor
from tom_observations.models import ObservationRecord
from tom_observations.facility import get_service_class
from tom_common.hooks import run_hook
from tom_common.hints import add_hint


class DataProductSaveView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        service_class = get_service_class(request.POST['facility'])
        observation_record = ObservationRecord.objects.get(pk=kwargs['pk'])
        products = request.POST.getlist('products')
        if not products:
            messages.warning(request, 'No products were saved, please select at least one dataproduct')
        elif products[0] == 'ALL':
            products = service_class().save_data_products(observation_record)
            messages.success(request, 'Saved all available data products')
        else:
            for product in products:
                products = service_class().save_data_products(
                    observation_record,
                    product
                )
                messages.success(
                    request,
                    'Successfully saved: {0}'.format('\n'.join(
                        [str(p) for p in products]
                    ))
                )
        return redirect(reverse(
            'tom_observations:detail',
            kwargs={'pk': observation_record.id})
        )


class DataProductUploadView(LoginRequiredMixin, FormView):
    form_class = DataProductUploadForm

    # def get_form_class(self):
    #     pass

    def form_valid(self, form):
        target = form.cleaned_data['target']
        if not target:
            observation_record = form.cleaned_data['observation_record']
            target = observation_record.target
        else:
            observation_record = None
        dp_type = form.cleaned_data['data_product_type']
        data_product_files = self.request.FILES.getlist('files')
        successful_uploads = []
        for f in data_product_files:
            dp = DataProduct(
                target=target,
                observation_record=observation_record,
                data=f,
                product_id=None,
                data_product_type=dp_type
            )
            dp.save()
            try:
                run_hook('data_product_post_upload', dp)
                run_data_processor(dp)
                successful_uploads.append(str(dp))
            except InvalidFileFormatException as iffe:
                ReducedDatum.objects.filter(data_product=dp).delete()
                dp.delete()
                messages.error(
                    self.request,
                    'File format invalid for file {0} -- error was {1}'.format(str(dp), iffe)
                )
            except Exception:
                ReducedDatum.objects.filter(data_product=dp).delete()
                dp.delete()
                messages.error(self.request, 'There was a problem processing your file: {0}'.format(str(dp)))
        if successful_uploads:
            messages.success(
                self.request,
                'Successfully uploaded: {0}'.format('\n'.join([p for p in successful_uploads]))
            )

        return redirect(form.cleaned_data.get('referrer', '/'))

    def form_invalid(self, form):
        # TODO: Format error messages in a more human-readable way
        messages.error(self.request, 'There was a problem uploading your file: {}'.format(form.errors.as_json()))
        return redirect(form.cleaned_data.get('referrer', '/'))


class DataProductDeleteView(LoginRequiredMixin, DeleteView):
    model = DataProduct
    success_url = reverse_lazy('home')

    def get_success_url(self):
        referer = self.request.GET.get('next', None)
        referer = urlparse(referer).path if referer else '/'
        return referer

    def delete(self, request, *args, **kwargs):
        ReducedDatum.objects.filter(data_product=self.get_object()).delete()
        self.get_object().data.delete()
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['next'] = self.request.META.get('HTTP_REFERER', '/')
        return context


class DataProductListView(FilterView):
    model = DataProduct
    template_name = 'tom_dataproducts/dataproduct_list.html'
    paginate_by = 25
    filterset_class = DataProductFilter
    strict = False

    def get_queryset(self):
        return super().get_queryset().filter(
            target__in=get_objects_for_user(self.request.user, 'tom_targets.view_target')
        )

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['product_groups'] = DataProductGroup.objects.all()
        return context


class DataProductFeatureView(View):
    def get(self, request, *args, **kwargs):
        product_id = kwargs.get('pk', None)
        product = DataProduct.objects.get(pk=product_id)
        try:
            current_featured = DataProduct.objects.filter(
                featured=True,
                data_product_type=product.data_product_type,
                target=product.target
            )
            for featured_image in current_featured:
                featured_image.featured = False
                featured_image.save()
                featured_image_cache_key = make_template_fragment_key(
                    'featured_image',
                    str(featured_image.target.id)
                )
                cache.delete(featured_image_cache_key)
        except DataProduct.DoesNotExist:
            pass
        product.featured = True
        product.save()
        return redirect(reverse(
            'tom_targets:detail',
            kwargs={'pk': request.GET.get('target_id')})
        )


class DataProductGroupDetailView(DetailView):
    model = DataProductGroup

    def post(self, request, *args, **kwargs):
        group = self.get_object()
        for product in request.POST.getlist('products'):
            group.dataproduct_set.remove(DataProduct.objects.get(pk=product))
        group.save()
        return redirect(reverse(
            'tom_dataproducts:group-detail',
            kwargs={'pk': group.id})
        )


class DataProductGroupListView(ListView):
    model = DataProductGroup


class DataProductGroupCreateView(LoginRequiredMixin, CreateView):
    model = DataProductGroup
    success_url = reverse_lazy('tom_dataproducts:group-list')
    fields = ['name']


class DataProductGroupDeleteView(LoginRequiredMixin, DeleteView):
    success_url = reverse_lazy('tom_dataproducts:group-list')
    model = DataProductGroup


class DataProductGroupDataView(LoginRequiredMixin, FormView):
    form_class = AddProductToGroupForm
    template_name = 'tom_dataproducts/add_product_to_group.html'

    def form_valid(self, form):
        group = form.cleaned_data['group']
        group.dataproduct_set.add(*form.cleaned_data['products'])
        group.save()
        return redirect(reverse(
            'tom_dataproducts:group-detail',
            kwargs={'pk': group.id})
        )


class UpdateReducedDataView(LoginRequiredMixin, RedirectView):
    def get(self, request, *args, **kwargs):
        target_id = request.GET.get('target_id', None)
        out = StringIO()
        if target_id:
            call_command('updatereduceddata', target_id=target_id, stdout=out)
        else:
            call_command('updatereduceddata', stdout=out)
        messages.info(request, out.getvalue())
        add_hint(request, mark_safe(
                          'Did you know updating observation statuses can be automated? Learn how in '
                          '<a href=https://tom-toolkit.readthedocs.io/en/stable/customization/automation.html>'
                          'the docs.</a>'))
        return HttpResponseRedirect(self.get_redirect_url(*args, **kwargs))

    def get_redirect_url(self):
        referer = self.request.META.get('HTTP_REFERER', '/')
        return referer

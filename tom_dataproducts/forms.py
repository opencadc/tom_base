from crispy_forms.bootstrap import Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Submit
from django import forms
from django.conf import settings
from django.urls import reverse

from tom_dataproducts.models import DataProductGroup, DataProduct
from tom_observations.models import ObservationRecord
from tom_observations.facility import get_service_classes
from tom_targets.models import Target


class AddProductToGroupForm(forms.Form):
    products = forms.ModelMultipleChoiceField(
        DataProduct.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )
    group = forms.ModelChoiceField(DataProductGroup.objects.all())


class BaseDataProductUploadForm(forms.Form):
    observation_record = forms.ModelChoiceField(
        ObservationRecord.objects.all(),
        widget=forms.HiddenInput(),
        required=False
    )
    target = forms.ModelChoiceField(
        Target.objects.all(),
        widget=forms.HiddenInput(),
        required=False
    )
    files = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={'multiple': True}
        )
    )
    data_product_type = forms.ChoiceField(
        choices=[(v, k) for k, v in settings.DATA_PRODUCT_TYPES.items()],
        widget=forms.HiddenInput(),
        required=False
    )
    referrer = forms.CharField(
        widget=forms.HiddenInput()
    )


class DataProductUploadForm(BaseDataProductUploadForm):
    other_type = forms.ChoiceField(
        choices=[(v, k) for k, v in settings.DATA_PRODUCT_TYPES.items() if k not in ['photometry', 'spectroscopy']],
        widget=forms.RadioSelect(),
        required=False
    )
    observation_date = forms.DateTimeField(required=False)
    facility = forms.ChoiceField(
        choices=[(None, '---------')] + [(v, v) for k, v in get_service_classes().items()], required=False
    )

    def __init__(self, *args, **kwargs):
        print([(v, k) for k, v in settings.DATA_PRODUCT_TYPES.items()])
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.add_input(Submit('submit', 'Upload'))
        # self.helper.form_action = reverse('tom_dataproducts:upload')
        self.helper.layout = Layout(
            'observation_record',
            'target',
            'referrer',
            'data_product_type',
            Div('files'),
            TabHolder(
                Tab('Photometry'),
                Tab('Spectroscopy', 'observation_date', 'facility'),
                Tab('Other', 'other_type'),
                css_id='data_upload_tabs'
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        print(cleaned_data)

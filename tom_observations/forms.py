from django import forms
from django.urls import reverse
from crispy_forms.helper import FormHelper
from crispy_forms.layout import ButtonHolder, Column, Layout, Row, Submit, Div

from tom_observations.facility import get_service_classes


def facility_choices():
    return [(k, k) for k in get_service_classes().keys()]

# camera fields of view in arcmin
camera_fovs = ((26.0, "SINISTRO - 26'"),
               (9.3, "MuSCAT3 - 9.3'"),
               (29.0, "SBIG 0.4m - 29'"),
               (15.8, "SBIG 1.0m - 15.8'"),
               (5.0, "Merope - 5'"),
               (5.5, "GMOS - 5.5'"))

class AddExistingObservationForm(forms.Form):
    """
    This form is used for adding existing API-based observations to a Target object.
    """
    target_id = forms.IntegerField(required=True, widget=forms.HiddenInput())
    facility = forms.ChoiceField(required=True, choices=facility_choices, label=False)
    observation_id = forms.CharField(required=True, label=False,
                                     widget=forms.TextInput(attrs={'placeholder': 'Observation ID'}))
    confirm = forms.BooleanField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_action = reverse('tom_observations:add-existing')
        self.helper.layout = Layout(
            'target_id',
            'confirm',
            Row(
                Column(
                    'facility'
                ),
                Column(
                    'observation_id'
                ),
                Column(
                    ButtonHolder(
                        Submit('submit', 'Add Existing Observation')
                    )
                )
            )
        )


class UpdateObservationId(forms.Form):
    """
    This form is used for updating the observation ID on an ObservationRecord object.
    """
    obsr_id = forms.IntegerField(required=True, widget=forms.HiddenInput())
    observation_id = forms.CharField(required=True, label=False,
                                     widget=forms.TextInput(attrs={'placeholder': 'Observation ID'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_action = reverse('tom_observations:update', kwargs={'pk': self.initial.get('obsr_id')})
        self.helper.layout = Layout(
            'obsr_id',
            Row(
                Column(
                    'observation_id'
                ),
                Column(
                    ButtonHolder(
                        Submit('submit', 'Update Observation Id')
                    ),
                )
            )
        )


class TileForm(forms.Form):
    instrument = forms.ChoiceField(required=True, label='Instrument', choices=camera_fovs)
    field_overlap = forms.DecimalField(required=True, label='Field Overlap', initial=0.3)
    min_fill_fraction = forms.DecimalField(required=True, label='Minimum Fill Fraction', initial=0.5)
    shimmy_factor = forms.DecimalField(required=True, label='Shimmy Factor', initial=0.0)
    ra_uncertainty = forms.DecimalField(required=False, label='R.A. Uncertainty (")')
    dec_uncertainty = forms.DecimalField(required=False, label='Dec. Uncertainty (")')
    selected_date = forms.DateTimeField(required=False, label='Date', widget=forms.TextInput(attrs={'type': 'date'}))
    selected_time = forms.TimeField(required=False, label='Time', widget=forms.TextInput(attrs={'type': 'time'}))

    def clean(self):
        cleaned_data = super().clean()
        field_overlap = cleaned_data.get('field_overlap')
        min_fill_fraction = cleaned_data.get('min_fill_fraction')
        target = self.data.get('target')
        instrument = cleaned_data.get('instrument')


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            self.layout(),
        )

    def layout(self):
        return Div(
                    Row(
                        Column('field_overlap', css_class='col'),
                        Column('instrument', css_class='col'),
                        ),
                    Row(
                        Column('min_fill_fraction', css_class='col'),
                        Column('shimmy_factor', css_class='col'),
                        ),
                    Row(
                        Column('ra_uncertainty', css_class='col'),
                        Column('dec_uncertainty', css_class='col'),
                        ),
                    Row(
                        Column('selected_date'),
                        Column('selected_time'),
                        ),
                    ButtonHolder(
                        Submit('submit', 'Tile')
                    ),
                )

from django import forms
from astropy.coordinates import Angle
from astropy import units as u
from astropy.time import Time
from django.forms import ValidationError, inlineformset_factory
from django.conf import settings
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm, get_groups_with_perms, remove_perm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Div

import datetime
import json
import numpy as np

from .models import (
    Target, TargetExtra, TargetName, SIDEREAL_FIELDS, NON_SIDEREAL_FIELDS, REQUIRED_SIDEREAL_FIELDS,
    REQUIRED_NON_SIDEREAL_FIELDS, REQUIRED_NON_SIDEREAL_FIELDS_PER_SCHEME
)


def extra_field_to_form_field(field_type):
    if field_type == 'number':
        return forms.FloatField(required=False)
    elif field_type == 'boolean':
        return forms.BooleanField(required=False)
    elif field_type == 'datetime':
        return forms.DateTimeField(required=False)
    elif field_type == 'string':
        return forms.CharField(required=False, widget=forms.Textarea)
    else:
        raise ValueError(
            'Invalid field type {}. Field type must be one of: number, boolean, datetime string'.format(field_type)
        )


class CoordinateField(forms.CharField):
    def __init__(self, *args, **kwargs):
        c_type = kwargs.pop('c_type')
        self.c_type = c_type
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        try:
            a = float(value)
            return a
        except ValueError:
            try:
                if self.c_type == 'ra':
                    a = Angle(value, unit=u.hourangle)
                else:
                    a = Angle(value, unit=u.degree)
                return a.to(u.degree).value
            except Exception:
                raise ValidationError('Invalid format. Please use sexigesimal or degrees')


class TargetForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(Group.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_fields = {}
        for extra_field in settings.EXTRA_FIELDS:
            # Add extra fields to the form
            field_name = extra_field['name']
            self.extra_fields[field_name] = extra_field_to_form_field(extra_field['type'])
            # Populate them with initial values if this is an update
            if kwargs['instance']:
                te = TargetExtra.objects.filter(target=kwargs['instance'], key=field_name)
                if te.exists():
                    self.extra_fields[field_name].initial = te.first().typed_value(extra_field['type'])

            self.fields.update(self.extra_fields)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            for field in settings.EXTRA_FIELDS:
                if self.cleaned_data.get(field['name']) is not None:
                    TargetExtra.objects.update_or_create(
                            target=instance,
                            key=field['name'],
                            defaults={'value': self.cleaned_data[field['name']]}
                    )
            # Save groups for this target
            for group in self.cleaned_data['groups']:
                assign_perm('tom_targets.view_target', group, instance)
                assign_perm('tom_targets.change_target', group, instance)
                assign_perm('tom_targets.delete_target', group, instance)
            for group in get_groups_with_perms(instance):
                if group not in self.cleaned_data['groups']:
                    remove_perm('tom_targets.view_target', group, instance)
                    remove_perm('tom_targets.change_target', group, instance)
                    remove_perm('tom_targets.delete_target', group, instance)

        return instance

    class Meta:
        abstract = True
        model = Target
        fields = '__all__'
        widgets = {'type': forms.HiddenInput()}


class SiderealTargetCreateForm(TargetForm):
    ra = CoordinateField(required=True, label='Right Ascension', c_type='ra',
                         help_text='Right Ascension, in decimal degrees or sexagesimal hours. See '
                                   'https://docs.astropy.org/en/stable/api/astropy.coordinates.Angle.html for '
                                   'supported sexagesimal inputs.')
    dec = CoordinateField(required=True, label='Declination', c_type='dec',
                          help_text='Declination, in decimal or sexagesimal degrees. See '
                                    ' https://docs.astropy.org/en/stable/api/astropy.coordinates.Angle.html for '
                                    'supported sexagesimal inputs.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in REQUIRED_SIDEREAL_FIELDS:
            self.fields[field].required = True

    class Meta(TargetForm.Meta):
        fields = SIDEREAL_FIELDS


class NonSiderealTargetCreateForm(TargetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in REQUIRED_NON_SIDEREAL_FIELDS:
            self.fields[field].required = True

    def clean(self):
        """
        Look at the 'scheme' field and check the fields required for the
        specified field have been given
        """
        cleaned_data = super().clean()
        scheme = cleaned_data['scheme']  # scheme is a required field, so this should be safe
        required_fields = REQUIRED_NON_SIDEREAL_FIELDS_PER_SCHEME[scheme]

        for field in required_fields:
            if not cleaned_data.get(field):
                # Get verbose names of required fields
                field_names = [
                    "'" + Target._meta.get_field(f).verbose_name + "'"
                    for f in required_fields
                ]
                scheme_name = dict(Target.TARGET_SCHEMES)[scheme]
                raise ValidationError(
                    "Scheme '{}' requires fields {}".format(scheme_name, ', '.join(field_names))
                )

    class Meta(TargetForm.Meta):
        fields = NON_SIDEREAL_FIELDS


class TargetVisibilityForm(forms.Form):
    start_time = forms.DateTimeField(required=True, label='Start Time', widget=forms.TextInput(attrs={'type': 'date'}))
    end_time = forms.DateTimeField(required=True, label='End Time', widget=forms.TextInput(attrs={'type': 'date'}))
    airmass = forms.DecimalField(required=False, label='Maximum Airmass')

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        target = self.data['target']
        if end_time < start_time:
            raise forms.ValidationError('Start time must be before end time')
        if target.type == 'NON_SIDEREAL':
            raise forms.ValidationError('Airmass plotting is only supported for sidereal targets')

class AladinNonSiderealForm(forms.Form):
    selected_date = forms.DateTimeField(required=True, label='Date (UTC)', widget=forms.TextInput(attrs={'type': 'date'}), initial=datetime.date.today)
    selected_time = forms.TimeField(required=True, label='Start Time (UTC)', widget=forms.TextInput(attrs={'type': 'time'}), initial=datetime.datetime.now().strftime("%H:%M"))
    duration = forms.DecimalField(required=True, label='Duration (hrs)', initial=24.0*7)
    facility = forms.CharField(required=False, label='facility', widget=forms.HiddenInput())
    target_id = forms.CharField(required=False, label='target_id', widget=forms.HiddenInput())

    def clean(self):
        cleaned_data = super().clean()
        selected_date = cleaned_data.get('selected_date')
        selected_time = cleaned_data.get('selected_time')
        duration = cleaned_data.get('duration')
        target = self.data['target']
        target_id = target.id

        if self.data['target'].scheme == 'EPHEMERIS':
            t = Time(selected_date.strftime("%Y-%m-%dT")+selected_time.strftime("%H:%M:00.0"))

            eph_json = json.loads(self.data['target'].eph_json)
            keys = list(eph_json.keys())
            mjd = []
            for i in eph_json[keys[0]]:
                mjd.append(i['t'])
            mjd = np.array(mjd, dtype='float64')
            min_mjd, max_mjd = np.min(mjd), np.max(mjd)

            if t.mjd < min_mjd or t.mjd > max_mjd:
                raise ValidationError('The selected date must be between {} and {} utc.'.format(Time(min_mjd, format='mjd').isot, Time(max_mjd, format='mjd').isot))


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(Column('selected_date'), Column('selected_time'), Column('target_id'), Column('facility'))
        )



TargetExtraFormset = inlineformset_factory(Target, TargetExtra, fields=('key', 'value'),
                                           widgets={'value': forms.TextInput()})
TargetNamesFormset = inlineformset_factory(Target, TargetName, fields=('name',), validate_min=False, can_delete=True,
                                           extra=3)

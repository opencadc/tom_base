from lxml import etree

from django import forms
from django.conf import settings
from crispy_forms.layout import Layout, Div
from suds.client import Client

from tom_observations.facility import GenericObservationForm, GenericObservationFacility
from tom_targets.models import Target

# Determine settings for this module
try:
    LT_SETTINGS = settings.FACILITIES['LT']
except (AttributeError, KeyError):
    LT_SETTINGS = {
        'proposal': '',
        'username': '',
        'password': ''
    }


class LTObservationForm(GenericObservationForm):
    project = forms.CharField()
    priority = forms.IntegerField()
    start = forms.CharField(widget=forms.TextInput(attrs={'type': 'date'}))
    end = forms.CharField(widget=forms.TextInput(attrs={'type': 'date'}))
    device = forms.ChoiceField(choices=[('IO:O', 'IO:O')])
    device_type = forms.ChoiceField(choices=[('camera', 'Camera')])
    filter = forms.ChoiceField(choices=[('G', 'G'), ('Z', 'Z')])
    binning = forms.ChoiceField(choices=[('2x2', '2x2')])
    exp_count = forms.IntegerField(min_value=1)
    exp_time = forms.FloatField(min_value=0.1)

    def _build_project(self):
        project = etree.Element('Project', ProjectId=LT_SETTINGS['proposal'])
        contact = etree.SubElement(project, 'Contact')
        etree.SubElement(contact, 'Username').text = LT_SETTINGS['username']
        etree.SubElement(contact, 'Name').text = ''
        
        return project

    def _build_schedule(self):
        target_to_observe = Target.objects.get(pk=self.cleaned_data['target_id'])
        schedule = etree.Element('Schedule')

        target = etree.SubElement(schedule, 'Target', name=target_to_observe.name)
        coordinates = etree.SubElement(target, 'Coordinates')
        ra = etree.SubElement(coordinates, 'RightAscension')
        etree.SubElement(ra, 'Hours').text = ''  # TODO: RA/Dec calculation
        etree.SubElement(ra, 'Minutes').text = ''
        etree.SubElement(ra, 'Seconds').text = ''
        etree.SubElement(ra, 'Offset', units='arcseconds').text = '0.0'
        dec = etree.SubElement(coordinates, 'Declination') 
        etree.SubElement(dec, 'Degrees').text = ''
        etree.SubElement(dec, 'Arcminutes').text = ''
        etree.SubElement(dec, 'Arcseconds').text = ''
        etree.SubElement(dec, 'Offset', units='arcseconds').text = '0.0'
        etree.SubElement(coordinates, 'Equinox').text = target_to_observe.epoch

        device = etree.SubElement(schedule, 
                                  'Device', 
                                  name=self.cleaned_data['device'], 
                                  type=self.cleaned_data['device_type'])
        etree.SubElement(device, 'SpectralRegion').text = 'optical'
        setup = etree.SubElement(device, 'Setup')
        etree.SubElement(setup, 'Filter', type=self.cleaned_data['filter'])
        detector = etree.SubElement(setup, 'Detector')
        binning = etree.SubElement(detector, 'Binning')
        etree.SubElement(binning, 'X', units='pixels').text = self.cleaned_data['binning'].split('x')[0]
        etree.SubElement(binning, 'Y', units='pixels').text = self.cleaned_data['binning'].split('x')[1]

        etree.SubElement(schedule, 'Priority').text = str(self.cleaned_data['priority'])
        
        exposure = etree.SubElement(schedule, 'Exposure', count=str(self.cleaned_data['exp_count']))
        etree.SubElement(exposure, 'Value', units='seconds').text = str(self.cleaned_data['exp_time'])

        date = etree.SubElement(schedule, 'DateTimeConstraint', type='include')
        etree.SubElement(date, 'DateTimeStart', system='UT', value=self.cleaned_data['start'])
        etree.SubElement(date, 'DateTimeEnd', system='UT', value=self.cleaned_data['end'])

        return schedule

    # TODO: write xml headers and write out to in-memory file
    def observation_payload(self):
        namespaces = {
            'xmlns': 'http://www.rtml.org/v3.1a',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        }
        payload = etree.Element('RTML', 
                             xmlns='http://www.rtml.org/v3.1a',
                             xsi='{http://www.rtml.org/v3.1a}http://www.w3.org/2001/XMLSchema-instance',
                             mode='request', 
                             uid='rtml://rtml-ioo-1566316274', 
                             version='3.1a',
                             schemaLocation='{http://www.w3.org/2001/XMLSchema-instance}http://www.rtml.org/v3.1a http://telescope.livjm.ac.uk/rtml/RTML-nightly.xsd',
                             nsmap=namespaces)
        payload.append(self._build_project())
        payload.append(self._build_schedule())
        return etree.tostring(payload, pretty_print=True)


class LTFacility(GenericObservationFacility):
    name = 'LT'
    observation_types = [('IMAGING', 'Imaging')]

    def get_form(self, observation_type):
        return LTObservationForm

    def submit_observation(self, observation_payload):
        headers = {
            'Username': LT_SETTINGS['username'],
            'Password': LT_SETTINGS['password']
        }
        url = '{0}://{1}:{2}/node_agent2/node_agent?wsdl'.format('http', '161.72.57.3', '8080')
        client = Client(url=url, headers=headers)
        client.service.handle_rtml(observation_payload)

    def validate_observation(self, observation_payload):
        return

    def get_observation_url(self, observation_id):
        return

    def get_terminal_observing_states(self):
        return

    def get_observing_sites(self):
        return

    def get_observation_status(self):
        return

    def data_products(self, observation_id, product_id=None):
        return
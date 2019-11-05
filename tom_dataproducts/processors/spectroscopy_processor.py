import mimetypes
import numpy as np

from astropy import units
from astropy.io import fits, ascii
from astropy.wcs import WCS
from django import forms
from specutils import Spectrum1D

from tom_dataproducts.data_processor import DataProcessor
from tom_dataproducts.exceptions import InvalidFileFormatException
from tom_dataproducts.forms import DataProductUploadForm
from tom_dataproducts.processors.data_serializers import SpectrumSerializer
from tom_observations.facility import get_service_class, get_service_classes


class SpectrumUploadForm(DataProductUploadForm):
    observation_date = forms.DateTimeField()
    facility = forms.ChoiceField(
        choices=[(None, '----------')] + [(k, k) for k in get_service_classes().keys()],
        required=True
    )

    def clean(self, *args, **kwargs):
        pass


class SpectroscopyProcessor(DataProcessor):
    name = 'Spectroscopy'
    form = SpectrumUploadForm

    DEFAULT_WAVELENGTH_UNITS = units.angstrom
    DEFAULT_FLUX_CONSTANT = units.erg / units.cm ** 2 / units.second / units.angstrom

    def process_data(self, data_product, **kwargs):
        """
        Routes a spectroscopy processing call to a method specific to a file-format, then serializes the returned data.

        :param data_product: Spectroscopic DataProduct which will be processed into the specified format for database
        ingestion
        :type data_product: DataProduct

        :returns: python list of 2-tuples, each with a timestamp and corresponding data
        :rtype: list
        """

        mimetype = mimetypes.guess_type(data_product.data.path)[0]
        if mimetype in self.FITS_MIMETYPES:
            spectrum, obs_date = self._process_spectrum_from_fits(data_product, **kwargs)
        elif mimetype in self.PLAINTEXT_MIMETYPES:
            spectrum, obs_date = self._process_spectrum_from_plaintext(data_product, **kwargs)
        else:
            raise InvalidFileFormatException('Unsupported file type')

        serialized_spectrum = SpectrumSerializer().serialize(spectrum)

        return [(obs_date, serialized_spectrum)]

    def _process_spectrum_from_fits(self, data_product, **kwargs):
        """
        Processes the data from a spectrum from a fits file into a Spectrum1D object, which can then be serialized and
        stored as a ReducedDatum for further processing or display. File is read using specutils as specified in the
        below documentation.
        # https://specutils.readthedocs.io/en/doc-testing/specutils/read_fits.html

        :param data_product: Spectroscopic DataProduct which will be processed into a Spectrum1D
        :type data_product: tom_dataproducts.models.DataProduct

        :returns: Spectrum1D object containing the data from the DataProduct
        :rtype: specutils.Spectrum1D

        :returns: Datetime of observation, if it is in the header and the file is from a supported facility, current
            datetime otherwise
        :rtype: AstroPy.Time
        """

        flux, header = fits.getdata(data_product.data.path, header=True)

        # Get observation facility. Try to get it from the form, then the FITS header.
        facility_name = kwargs.get('facility')
        if not facility_name:
            for facility_class in get_service_classes():
                facility = get_service_class(facility_class)()
                if facility.is_fits_facility(header):
                    break
            else:
                facility = None
        else:
            facility = get_service_class(facility_name)()

        # Get the observation date. Try to get it from the form, then the FITS header. If there is no observation date,
        # raise a ValidationError. If the observation date is obtained from the FITS header, attempt to convert it to
        # an Astropy.Time object first without a specified format, then try to use modified Julian date.
        date_obs = kwargs.get('observation_date')
        if not date_obs:
            if facility:
                date_obs = facility.get_date_obs(header)
            else:
                raise InvalidFileFormatException('Observation date must be specified in form or included in file.')

        date_obs = self._date_obs_to_astropy_time(date_obs)

        # Get the flux constant. Use the default one if no facility has been identified.
        flux_constant = self.DEFAULT_FLUX_CONSTANT
        if facility:
            flux_constant = facility.get_flux_constant()

        dim = len(flux.shape)
        if dim == 3:
            flux = flux[0, 0, :]
        elif flux.shape[0] == 2:
            flux = flux[0, :]
        header['CUNIT1'] = 'Angstrom'
        wcs = WCS(header=header)
        flux = flux * flux_constant

        spectrum = Spectrum1D(flux=flux, wcs=wcs)

        return spectrum, date_obs

    def _process_spectrum_from_plaintext(self, data_product, **kwargs):
        """
        Processes the data from a spectrum from a plaintext file into a Spectrum1D object, which can then be serialized
        and stored as a ReducedDatum for further processing or display. File is read using astropy as specified in
        the below documentation. The file is expected to be a multi-column delimited file, with headers for wavelength
        and flux. The file also requires comments containing, at minimum, 'DATE-OBS: [value]', where value is an
        Astropy Time module-readable date. It can optionally contain 'FACILITY: [value]', where the facility is a string
        matching the name of a valid facility in the TOM.
        # http://docs.astropy.org/en/stable/io/ascii/read.html

        Parameters
        ----------
        :param data_product: Spectroscopic DataProduct which will be processed into a Spectrum1D
        :type data_product: tom_dataproducts.models.DataProduct

        :returns: Spectrum1D object containing the data from the DataProduct
        :rtype: specutils.Spectrum1D

        :returns: Datetime of observation, if it is in the comments and the file is from a supported facility, current
            datetime otherwise
        :rtype: AstroPy.Time
        """

        data = ascii.read(data_product.data.path)
        if len(data) < 1:
            raise InvalidFileFormatException('Empty table or invalid file type')
        facility_name = kwargs.get('facility')
        date_obs = kwargs.get('observation_date')
        comments = data.meta.get('comments', [])

        for comment in comments:
            if not facility_name:
                if 'facility' in comment.lower():
                    facility_name = comment.split(':')[1].strip()
            if not date_obs:
                if 'date-obs' in comment.lower():
                    date_obs = comment.split(':')[1].strip()

        if date_obs:
            date_obs = self._date_obs_to_astropy_time(date_obs)
        else:
            raise InvalidFileFormatException('Observation date must be specified in form or included in file.')

        facility = get_service_class(facility_name)() if facility_name else None
        wavelength_units = facility.get_wavelength_units() if facility else self.DEFAULT_WAVELENGTH_UNITS
        flux_constant = facility.get_flux_constant() if facility else self.DEFAULT_FLUX_CONSTANT

        spectral_axis = np.array(data['wavelength']) * wavelength_units
        flux = np.array(data['flux']) * flux_constant
        spectrum = Spectrum1D(flux=flux, spectral_axis=spectral_axis)

        return spectrum, date_obs

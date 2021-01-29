from astropy.coordinates import get_sun, SkyCoord, Angle, AltAz
from astropy import units, coordinates
from astropy.time import Time
from astroplan import Observer, FixedTarget, time_grid_from_range
import numpy as np
from scipy import interpolate as interp
import json
import logging

from tom_observations import facility


logger = logging.getLogger(__name__)


def get_ellipse(a, b):
    ang = np.linspace(0, 2*np.pi, 200)
    return (a*np.cos(ang), b*np.sin(ang))

def get_astrom_uncert_ephemeris(target, selected_time):
    """
    Get the astrometric uncertainty of a EPHEMERIS target.
    """
    if target.type == target.NON_SIDEREAL:
        if target.scheme == 'EPHEMERIS':
            eph_json = json.loads(target.eph_json)
            sites = list(eph_json)

            mk = eph_json[sites[0]]

            ras = []
            decs = []
            dras = []
            ddecs = []
            mjds = []
            times = []
            for i, e in enumerate(mk):
                mjds.append(float(e['t']))
                ras.append(float(e['R']))
                decs.append(float(e['D']))
                dras.append(float(e['dR']))
                ddecs.append(float(e['dD']))

            mjds, ras, decs, dras, ddecs = np.array(mjds), np.array(ras), np.array(decs), np.array(dras), np.array(ddecs)

            fra = interp.interp1d(mjds, ras)
            fdec = interp.interp1d(mjds, decs)
            fdra = interp.interp1d(mjds, dras)
            fddec = interp.interp1d(mjds, ddecs)

            if selected_time == '':
                selected_mjd = Time.now().mjd
            else:
                selected_mjd = Time(selected_time).mjd
            try:
                out = (fra(selected_mjd),
                        fdec(selected_mjd),
                        fdra(selected_mjd),
                        fddec(selected_mjd))
                return out
            except:
                raise('Selected time outside ephemeris range.')

        raise Exception("Target type does not contain astrometric uncertainty information. Please specify.")
    else:
        raise Exception("Target type does not contain astrometric uncertainty information. Please specify.")

def get_radec_ephemeris(eph_json_single, start_time, end_time, interval, observing_facility, observing_site):
    observing_facility_class = facility.get_service_class(observing_facility)
    sites = observing_facility_class().get_observing_sites()
    observer = None
    for site_name in sites:
        obs_site = sites[site_name]
        if obs_site['sitecode'] == observing_site:

            observer = coordinates.EarthLocation(lat=obs_site.get('latitude')*units.deg,
                                                 lon=obs_site.get('longitude')*units.deg,
                                                 height=obs_site.get('elevation')*units.m)
    if observer is None:
        # this condition occurs if the facility being requested isn't in the site list provided.
        return (None, None, None, None, -1)
    ra = []
    dec = []
    mjd = []
    for i in range(len(eph_json_single)):
        ra.append(float(eph_json_single[i]['R']))
        dec.append(float(eph_json_single[i]['D']))
        mjd.append(float(eph_json_single[i]['t']))
    ra = np.array(ra)
    dec = np.array(dec)
    mjd = np.array(mjd)

    fra = interp.interp1d(mjd, ra)
    fdec = interp.interp1d(mjd, dec)

    start = Time(start_time)
    end = Time(end_time)

    time_range = time_grid_from_range(time_range=[start, end], time_resolution=interval*units.hour)
    tr_mjd = time_range.mjd

    airmasses = []
    sun_alts = []
    for i in range(len(tr_mjd)):
        c = SkyCoord(fra(time_range[i].mjd), fdec(time_range[i].mjd), frame="icrs", unit="deg")
        t = Time(tr_mjd[i], format='mjd')
        sun = coordinates.get_sun(t)
        altaz = c.transform_to(AltAz(obstime=t, location=observer))
        sun_altaz = sun.transform_to(AltAz(obstime=t, location=observer))
        airmass = altaz.secz
        airmasses.append(airmass)
        sun_alts.append(sun_altaz.alt.value)
    airmasses = np.array(airmasses)
    sun_alts = np.array(sun_alts)

    if np.min(tr_mjd) >= np.min(mjd) and np.max(tr_mjd) <= np.max(mjd):
        return (tr_mjd, fra(tr_mjd), fdec(tr_mjd), airmasses, sun_alts)
    else:
        return (None, None, None, None, -2)


def get_sidereal_visibility(target, start_time, end_time, interval, airmass_limit):
    """
    Uses astroplan to calculate the airmass for a sidereal target
    for each given interval between the start and end times.

    The resulting data omits any airmass above the provided limit (or
    default, if one is not provided), as well as any airmass calculated
    during the day (defined as between astronomical twilights).

    Important note: only works for sidereal targets! For non-sidereal visibility, see here:
    https://github.com/TOMToolkit/tom_nonsidereal_airmass

    :param start_time: start of the window for which to calculate the airmass
    :type start_time: datetime

    :param end_time: end of the window for which to calculate the airmass
    :type end_time: datetime

    :param interval: time interval, in minutes, at which to calculate airmass within the given window
    :type interval: int

    :param airmass_limit: maximum acceptable airmass for the resulting calculations
    :type airmass_limit: int

    :returns: A dictionary containing the airmass data for each site. The dict keys consist of the site name prepended
        with the observing facility. The values are the airmass data, structured as an array containing two arrays. The
        first array contains the set of datetimes used in the airmass calculations. The second array contains the
        corresponding set of airmasses calculated.
    :rtype: dict
    """

    if target.type != 'SIDEREAL':
        msg = '\033[1m\033[91mAirmass plotting is only supported for sidereal targets\033[0m'
        logger.info(msg)
        empty_visibility = {}
        return empty_visibility

    if end_time < start_time:
        raise Exception('Start must be before end')

    if airmass_limit is None:
        airmass_limit = 10

    body = FixedTarget(name=target.name, coord=SkyCoord(target.ra, target.dec, unit='deg'))

    visibility = {}
    sun, time_range = get_astroplan_sun_and_time(start_time, end_time, interval)
    for observing_facility in facility.get_service_classes():
        observing_facility_class = facility.get_service_class(observing_facility)
        sites = observing_facility_class().get_observing_sites()
        for site, site_details in sites.items():
            observer = Observer(longitude=site_details.get('longitude')*units.deg,
                                latitude=site_details.get('latitude')*units.deg,
                                elevation=site_details.get('elevation')*units.m)

            sun_alt = observer.altaz(time_range, sun).alt
            obj_airmass = observer.altaz(time_range, body).secz

            bad_indices = np.argwhere(
                (obj_airmass >= airmass_limit) |
                (obj_airmass <= 1) |
                (sun_alt > -18*units.deg)  # between astronomical twilights, i.e. sun is up
            )

            obj_airmass = [None if i in bad_indices else float(airmass) for i, airmass in enumerate(obj_airmass)]

            visibility[f'({observing_facility}) {site}'] = (time_range.datetime, obj_airmass)
    return visibility


def get_astroplan_sun_and_time(start_time, end_time, interval):
    """
    Uses astroplan's time_grid_from_range to generate
    an astropy Time object covering the time range.

    Uses astropy's get_sun to generate sun positions over
    that time range.

    If time range is small and interval is coarse, approximates
    the sun at a fixed position from the middle of the
    time range to speed up calculations.
    Since the sun moves ~4 minutes a day, this approximation
    happens when the number of days covered by the time range
    * 4 is less than the interval (in minutes) / 2.

    :param start_time: start of the window for which to calculate the airmass
    :type start_time: datetime

    :param end_time: end of the window for which to calculate the airmass
    :type end_time: datetime

    :param interval: time interval, in minutes, at which to calculate airmass within the given window
    :type interval: int

    :returns: ra/dec positions of the sun over the time range,
        time range between start_time and end_time at interval
    :rtype: astropy SkyCoord, astropy Time
    """

    start = Time(start_time)
    end = Time(end_time)

    time_range = time_grid_from_range(time_range=[start, end], time_resolution=interval*units.minute)

    number_of_days = end.mjd - start.mjd
    if number_of_days*4 < float(interval)/2:
        # Hack to speed up calculation by factor of ~3
        sun_coords = get_sun(time_range[int(len(time_range)/2)])
        sun = FixedTarget(name='sun', coord=SkyCoord(sun_coords.ra, sun_coords.dec, unit='deg'))
    else:
        sun = get_sun(time_range)

    return sun, time_range

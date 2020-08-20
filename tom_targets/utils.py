from django.db.models import Count

import csv
from .models import Target, TargetExtra, TargetName
from io import StringIO
import json

# this dictionary should contain as key entires text sufficient to uniquely
# identify the observatory name from the common English names used by JPL for
# that site. For example, Sunderland is probably unique enough to identify SAAO
# there may be a better way to handle this.
site_names = {'Mauna Kea': '568',
              'Haleakala': 'ogg',
              'McDonald': 'elp',
              'Tololo': 'lsc',
              'Teide': 'tfn',
              'Sutherland': 'cpt',
              'Wise': 'tlv',
              'Siding Spring': 'coj',
              }


# NOTE: This saves locally. To avoid this, create file buffer.
# referenced https://www.codingforentrepreneurs.com/blog/django-queryset-to-csv-files-datasets/
def export_targets(qs):
    """
    Exports all the specified targets into a csv file in folder csvTargetFiles
    NOTE: This saves locally. To avoid this, create file buffer.

    :param qs: List of targets to export
    :type qs: QuerySet

    :returns: String buffer of exported targets
    :rtype: StringIO
    """
    qs_pk = [data['id'] for data in qs]
    data_list = list(qs)
    target_fields = [field.name for field in Target._meta.get_fields()]
    target_extra_fields = list({field.key for field in TargetExtra.objects.filter(target__in=qs_pk)})
    # Gets the count of the target names for the target with the most aliases in the database
    # This is to construct enough row headers of format "name2, name3, name4, etc" for exporting aliases
    # The alias headers are then added to the set of fields for export
    aliases = TargetName.objects.filter(target__in=qs_pk).values('target_id').annotate(count=Count('target_id'))
    max_alias_count = 0
    if aliases:
        max_alias_count = max([alias['count'] for alias in aliases])
    all_fields = target_fields + target_extra_fields + [f'name{index+1}' for index in range(1, max_alias_count+1)]
    for key in ['id', 'targetlist', 'dataproduct', 'observationrecord', 'reduceddatum', 'aliases', 'targetextra']:
        all_fields.remove(key)

    file_buffer = StringIO()
    writer = csv.DictWriter(file_buffer, fieldnames=all_fields)
    writer.writeheader()
    for target_data in data_list:
        extras = list(TargetExtra.objects.filter(target_id=target_data['id']))
        names = list(TargetName.objects.filter(target_id=target_data['id']))
        for e in extras:
            target_data[e.key] = e.value
        name_index = 2
        for name in names:
            target_data[f'name{str(name_index)}'] = name.name
            name_index += 1
        del target_data['id']  # do not export 'id'
        writer.writerow(target_data)
    return file_buffer


def import_targets(targets):
    """
    Imports a set of targets into the TOM and saves them to the database.

    :param targets: String buffer of targets
    :type targets: StringIO

    :returns: dictionary of successfully imported targets, as well errors
    :rtype: dict
    """
    # TODO: Replace this with an in memory iterator
    targetreader = csv.DictReader(targets, dialect=csv.excel)
    targets = []
    errors = []
    base_target_fields = [field.name for field in Target._meta.get_fields()]
    for index, row in enumerate(targetreader):
        # filter out empty values in base fields, otherwise converting empty string to float will throw error
        row = {k: v for (k, v) in row.items() if not (k in base_target_fields and not v)}
        target_extra_fields = []
        target_names = []
        target_fields = {}
        for k in row:
            # All fields starting with 'name' (e.g. name2, name3) that aren't literally 'name' will be added as
            # TargetNames
            if k != 'name' and k.startswith('name'):
                target_names.append(row[k])
            elif k not in base_target_fields:
                target_extra_fields.append((k, row[k]))
            else:
                target_fields[k] = row[k]
        for extra in target_extra_fields:
            row.pop(extra[0])
        try:
            target = Target.objects.create(**target_fields)
            for extra in target_extra_fields:
                TargetExtra.objects.create(target=target, key=extra[0], value=extra[1])
            for name in target_names:
                if name:
                    TargetName.objects.create(target=target, name=name)
            targets.append(target)
        except Exception as e:
            error = 'Error on line {0}: {1}'.format(index + 2, str(e))
            errors.append(error)

    return {'targets': targets, 'errors': errors}


def import_ephemeris_target(stream):
    """
    Reads in a custom ephemeris from provided file stream.

    Currently only reads in the first site-code ephemeris.
    """

    # TO-DO: need to make robust to input date type
    # TO-DO: need to make robust to input coordinate type

    errors = []
    targets = []

    jpl_ra_key = 'R.A._____(ICRF)_____DEC'
    jpl_jd_key = 'Date_________JDUT'
    jpl_dr_key = 'RA_3sigma'
    jpl_dd_key = 'DEC_3sigma'

    eph = stream.getvalue().split('\n')

    num_sites = 0
    for i in range(len(eph)):
        if 'Center-site name' in eph[i]:
            num_sites += 1

    if num_sites != 8:
        errors.append(Warning('WARNING: Provided file does not have ephemerides for all 7 LCO sites.'))

    eph_json = {}
    end_ind = 0
    for ns in range(num_sites):

        centre_site_name = None
        site_name_found = False
        name = 'custom'
        jd_inds = None
        ra_inds = None
        dr_inds = None
        dd_inds = None
        loop_inds = [-1, -1]
        for i in range(end_ind, len(eph)):
            if 'Center-site name' in eph[i]:
                s = eph[i].split(': ')[-1]
                for j in site_names.keys():
                    if j in s:
                        centre_site_name = site_names[j]
                        site_name_found = True
                        break
                if not site_name_found:
                    centre_site_name = s

            if 'Target body name' in eph[i]:
                name = "-".join(eph[i].split(': ')[1].split('{source')[0].split())

            if jpl_ra_key in eph[i] and jpl_jd_key in eph[i] and jpl_dr_key in eph[i] and jpl_dd_key in eph[i]:
                ra_inds = [eph[i].index(jpl_ra_key), eph[i].index(jpl_ra_key)+len(jpl_ra_key)]
                jd_inds = [eph[i].index(jpl_jd_key), eph[i].index(jpl_jd_key)+len(jpl_jd_key)]
                dr_inds = [eph[i].index(jpl_dr_key), eph[i].index(jpl_dr_key)+len(jpl_dr_key)]
                dd_inds = [eph[i].index(jpl_dd_key), eph[i].index(jpl_dd_key)+len(jpl_dd_key)]
            if '$$SOE' in eph[i]:
                if ra_inds is not None and loop_inds[0] == -1:
                    loop_inds[0] = i+1
            if '$$EOE' in eph[i]:
                if ra_inds is not None and loop_inds[0] != -1:
                    loop_inds[1] = i
                    break

        end_ind = loop_inds[1]+1

        # throw an HTML warning if I cannot understand the centre site name
        if not site_name_found:
            errors.append(Exception(f'Site name {centre_site_name} not understood.'))

        # throw HTML screen of warning if I cannot find the coordinates or
        # ephemerides. TO-DO: put a better error check and correctly thrown
        # warning for now being lazy
        if loop_inds == [-1, -1] or ra_inds is None or jd_inds is None:
            errors.append(Exception('We were not able to understand that ephemeris file.'))

        mjds = []
        ras = []
        decs = []
        drs = []
        dds = []
        R = 0.0
        D = 0.0
        n = 0.0
        for i in range(loop_inds[0], loop_inds[1]):
            mjds.append(str(float(eph[i][jd_inds[0]:jd_inds[1]])-2400000.5))

            s = eph[i][ra_inds[0]:ra_inds[1]].split()
            r = 15.0*(float(s[0])+float(s[1])/60.0+float(s[2])/3600.0)
            ras.append("{:.7f}".format(r))
            d = abs(float(s[3]))+float(s[4])/60.0+float(s[5])/3600.0
            if '-' in s[3]:
                d *= -1.0
            decs.append("{:.6f}".format(d))

            drs.append('{:.7f}'.format( float(eph[i][dr_inds[0]:dr_inds[1]])/3600.0 ))
            dds.append('{:.6f}'.format( float(eph[i][dd_inds[0]:dd_inds[1]])/3600.0 ))

            R += r
            D += d
            n += 1.0

        eph_json[centre_site_name] = []
        for i in range(len(ras)):
            entry = {}
            entry['t'] = mjds[i]
            entry['R'] = ras[i]
            entry['D'] = decs[i]
            entry['dR'] = drs[i]
            entry['dD'] = dds[i]

            eph_json[centre_site_name].append(entry)

    try:
        target_fields = {}
        target_fields['type'] = 'NON_SIDEREAL'
        target_fields['scheme'] = 'EPHEMERIS'
        target_fields['name'] = name
        target_fields['eph_json'] = json.dumps(eph_json)

        target = Target.objects.create(**target_fields)
        targets.append(target)
    except Exception as e:
        errors.append(str(e))

    return {'targets': targets, 'errors': errors}

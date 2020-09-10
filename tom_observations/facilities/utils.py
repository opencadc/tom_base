from astropy.time import Time
import numpy as np

d2r = np.pi/180.0

#example format
"""
***************************************************************************************
 Date__(UT)__HR:MN Date_________JDUT     R.A.___(ICRF/J2000.0)___DEC dRA*cosD d(DEC)/dt
***************************************************************************************
$$SOE
 2013-Jan-01 16:00 2456294.166666667 Am  14 30 58.5670 -12 25 00.360 8.861123  -2.58933

$$EOE
***************************************************************************************
 """

def get_hex(ra, dec):
    s = ra/15.0
    rh = int(s)
    s -= rh
    s *= 60.0
    rm = int(s)
    rs = (s-rm)*60.0

    s = abs(dec)
    dh = int(dec)
    s -= dh
    s *= 60.0
    dm = int(s)
    ds = (s-dm)*60.0

    if dec<0:
        Sign = '-'
    else:
        Sign = '+'

    return (rh, rm, rs, Sign, dh, dm, ds)

def add_month(t):
    T = t.replace('-01-','-Jan-').replace('-02-','-Feb-').replace('-03-','-Mar-').replace('-04-','-Apr-').replace('-05-','-May-')
    T = T.replace('-06-','-Jun-').replace('-07-','-Jul-').replace('-08-','-Aug-').replace('-09-','-Sep-').replace('-10-','-Oct-')
    return T.replace('-11-', '-Nov-').replace('-12-', '-Dec-')

def reconstruct_gemini_eph_note(eph, site='568'):
    mk = eph[site]

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
        t = Time(mjds[-1], format='mjd', scale='utc')
        times.append(add_month(t.iso))

    mjds, ras, decs, dras, ddecs = np.array(mjds), np.array(ras), np.array(decs), np.array(dras), np.array(ddecs)

    rates_ra = (ras[1:]-ras[:-1])*(np.cos(decs[:-1]*d2r))/(mjds[1:]-mjds[:-1])*(3600.0/24.0)
    rates_dec = (decs[1:]-decs[:-1])/(mjds[1:]-mjds[:-1])*(3600.0/24.0)
    rates_ra = np.concatenate([rates_ra, rates_ra[-1:]])
    rates_dec = np.concatenate([rates_dec, rates_dec[-1:]])

    JPL = ["***************************************************************************************",
           " Date__(UT)__HR:MN Date_________JDUT     R.A.___(ICRF/J2000.0)___DEC dRA*cosD d(DEC)/dt",
           "***************************************************************************************",
           "$$SOE",
           ]
    for i in range(len(mjds)):
        (rh, rm, rs, S, dh, dm, ds) = get_hex(ras[i], decs[i])

        entry = " {} {:<17f}     {} {:02} {:07.4f} {}{} {:02} {:06.3f} {:8.5} {:8.5}".format(times[i][:17],
                                                                                             mjds[i]+2400000.5,
                                                                                             rh, rm, rs,
                                                                                             S, dh, dm, ds,
                                                                                             rates_ra[i],
                                                                                             rates_dec[i])
        JPL.append(entry)
    JPL.append("$$EOE")
    JPL.append("***************************************************************************************")

    return (JPL, mjds)

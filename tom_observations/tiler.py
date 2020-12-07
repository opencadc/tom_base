# import pylab as pyl
import numpy as np
from plotly import offline
import plotly.graph_objs as go
import time


def checkThoseCorners(cx, cy, fov, a, b, min_fraction = 0.9):
    """
    This routine determines if >min_fraction of the fov is filled by the error
    ellipse. If yes, true is returned.
    """

    fov2 = fov/2.0

    X = np.linspace(cx-fov2, cx+fov2, 10)
    Y = np.linspace(cy-fov2, cy+fov2, 10)
    (xv, yv) = np.meshgrid(X, Y)

    r2 = (xv/a)**2 + (yv/b)**2
    w = np.where(r2 < 1)
    if len(w[0]) > min_fraction*len(X)*len(Y):
        return True
    else:
        return False


def get_ellipse(a, b):
    ang = np.linspace(0, 2*np.pi, 200)
    return (a*np.cos(ang), b*np.sin(ang))


def make_tiles(fov, a, b, overlap = 0.3, min_fill_fraction = 0.3,
               allowShimmy = True, n_shimmy = 20,
               drawPlot = False):
    """
    Make a tile layout to cover an ellipse descibed by the
    RA (a) and Dec (b) uncertainties. Units assumed to be degrees.
    """

    if 2*a <= fov and 2*b <= fov:
        cent_a = np.array([0.0])
        cent_b = np.array([0.0])
        frames = np.array([[0.0, 0.0]])

    else:
        n_a = int(2*a/(fov*(1 - overlap)))+1
        n_b = int(2*b/(fov*(1 - overlap)))+1
        if n_a%2>0:
            a_offset = (min_fill_fraction - 1.0)*fov/2
        else:
            a_offset = 0.0
        if n_b%2>0:
            b_offset = (min_fill_fraction - 1.0)*fov/2
        else:
            b_offset = 0.0

        if 2*a<fov:
            cent_a = np.array([0.0])
        else:
            cent_a = np.arange(-n_a/2, n_a/2+1)*(fov*(1.0-overlap)) + a_offset
        if 2*b<fov:
            cent_b = np.array([0.0])
        else:
            cent_b = np.arange(-n_b/2, n_b/2+1)*(fov*(1.0-overlap)) + b_offset

        frames = []
        if a>=b:
            for i in range(len(cent_a)):
                strip = []
                for j in range(len(cent_b)):
                    if checkThoseCorners(cent_a[i], cent_b[j], fov, a, b, min_fill_fraction) or len(cent_b)==1:
                        strip.append([cent_a[i], cent_b[j]])

                if len(strip) > 0:
                    strip = np.array(strip)
                    strip[:, 1] -= np.mean(strip[:, 1])
                    for j in strip:
                        frames.append(j)

        elif b>a:
            for j in range(len(cent_b)):
                strip = []
                for i in range(len(cent_a)):
                    if checkThoseCorners(cent_a[i], cent_b[j], fov, a, b, min_fill_fraction) or len(cent_a)==1:
                        strip.append([cent_a[i], cent_b[j]])

                if len(strip) > 0:
                    strip = np.array(strip)
                    strip[:, 0] -= np.mean(strip[:, 0])

                    for i in strip:
                        frames.append(i)
        frames = np.array(frames)

    if allowShimmy and len(frames)>1:
        # make a map that is fov/n pixel scale
        scale = fov/float(n_shimmy)
        nx = int(2*a/scale)+1
        ny = int(2*b/scale)+1

        x = np.linspace(0, 2*a, nx)
        y = np.linspace(0, 2*b, ny)

        gx, gy = np.meshgrid(x, y)
        orig_map = np.zeros((ny, nx), dtype = 'float64')

        r2 = ((gx-a)/a)**2 + ((gy-b)/b)**2
        w = np.where(r2 < 1)
        orig_map[w]=1
        n_ellipse = len(np.where(orig_map>0)[0])

        shimmy = []
        for i in range(int(-n_shimmy/2), int(n_shimmy/2)+1):
            for j in range(int(-n_shimmy/2), int(n_shimmy/2)+1):
                map = np.copy(orig_map)
                for f in frames:
                    dx = scale*i
                    dy = scale*j
                    w = np.where((gx>=f[0]+a+dx-fov/2.0) & (gx<=f[0]+a+dx+fov/2.0) & \
                                 (gy>=f[1]+b+dy-fov/2.0) & (gy<=f[1]+b+dy+fov/2.0) & (map>0))
                    map[w]+=1

                    w_missed = np.where(map==1)
                    shimmy.append([len(w_missed[0]), dx, dy])
        shimmy = np.array(shimmy)
        argmin = np.argmin(shimmy[:, 0])
        frames[:, 0] += shimmy[argmin][1]
        frames[:, 1] += shimmy[argmin][2]
        print('Shimmied by {}, {}.'.format(shimmy[argmin][1], shimmy[argmin][2]))


    if drawPlot:
        fig  = pyl.figure(1)
        sp = fig.add_subplot(111)
        for i in frames:
            pyl.scatter(i[0], i[1])
            rekt = pyl.Rectangle([i[0]-fov/2.0, i[1]-fov/2.0],
                                 fov, fov,
                                 facecolor = 'none', edgecolor='g')
            sp.add_patch(rekt)
        (x, y) = get_ellipse(a, b)
        pyl.plot(x, y)
        pyl.show()

    return frames


if __name__ == "__main__":
    #print(make_tiles(6.0/60.0, 5.5/60.0, 3.5/60.0, drawPlot=True))
    #print(make_tiles(6.0/60.0, 3.5/60.0, 5.5/60.0, drawPlot=True))
    fov = 6.0/60.0
    a, b = 1300.0/3600.0, 950.0/3600.0
    tiles = make_tiles(fov, a, b, min_fill_fraction = 0.3, allowShimmy = False, n_shimmy = 20, drawPlot=False)

    #plot_data = [go.Scatter(x=tiles[:, 0], y=tiles[:, 1], mode='markers')]
    plot_data = []
    for i, f in enumerate(tiles):
        x = [f[0]-fov/2, f[0]-fov/2, f[0]+fov/2, f[0]+fov/2, f[0]-fov/2]
        y = [f[1]-fov/2, f[1]+fov/2, f[1]+fov/2, f[1]-fov/2, f[1]-fov/2]
        plot_data.append(go.Scatter(x=x, y=y, mode='lines', line_color='red', name=str(i)))
    (x, y) = get_ellipse(a, b)
    plot_data.append(go.Scatter(x=x, y=y, mode='lines', line_color='black', name='Uncertainty Ellipse'))
    layout = go.Layout(title=None, xaxis=dict(title="RA"), yaxis=dict(title='Dec.'))
    offline.plot({
    "data": plot_data,
    "layout": layout,

    })

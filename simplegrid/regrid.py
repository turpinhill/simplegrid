#!/usr/bin/env python

import argparse
import math
import numpy as np
import pyproj
from . import gridio
from . import mitgridfilefields
from . import util


def create_parser():
    """Set up the list of arguments to be provided to regrid.
    """
    parser = argparse.ArgumentParser(
        description="""
            Regrid subdomain of an existing grid.""",
        epilog="""
            Note that the ni and nj values, and their implied orientations, are
            determined by the expected format of the file provided by
            'filename'.""")
    parser.add_argument('filename', help="""
        mitgrid (path and) file name""")
    parser.add_argument('ni', type=int, help="""
        number of mitgridfile cells in the nominal east-west direction""")
    parser.add_argument('nj', type=int, help="""
        number of mitgridfile cells in the nominal north-south direction""")
    parser.add_argument('lon1', type=float, help="""
        longitude of first range-defining corner point""")
    parser.add_argument('lat1', type=float, help="""
        latitude of first range-defining corner point""")
    parser.add_argument('lon2', type=float, help="""
        longitude of second range-defining corner point""")
    parser.add_argument('lat2', type=float, help="""
        latitude of second range-defining corner point""")
    parser.add_argument('lon_subscale', type=int, help="""
        subscale factor to be applied to each cell in the nominal east-west
        direction (e.g., '2' doubles the number of x-direction cells)
        (integer>=1)""")
    parser.add_argument('lat_subscale', type=int, help="""
        subscale factor to be applied to each cell in the nominal north-south
        direction between lat1 and lat2 (see lon_subscale comments)
        (integer>=1)""")
    parser.add_argument('outfile', help="""
        file to which regridded matrices will be written""")
    parser.add_argument('-v','--verbose',action='store_true',help="""
        verbose output""")
    return parser


def regrid(mitgridfile,ni,nj,lon1,lat1,lon2,lat2,lon_subscale,lat_subscale,verbose=False):
    """Regrids a rectangular lon/lat region using simple great circle-based
    subdivision, preserving any corner grids that may already exist within the
    region. A normal spherical geoid is currently assumed.

    Args:
        mitgridfile (str): (path and) filename of data to be regridded.
        ni (int): number of mitgridfile cells in the nominal "east-west" direction.
        nj (int): number of mitgridfile cells in the nominal "north-south" direction.
        lon1 (float): longitude of first range-defining corner point.
        lat1 (float): latitude of first range-defining corner point.
        lon2 (float): longitude of second range-defining corner point.
        lat2 (float): latitude of second range-defining corner point.
        lon_subscale (int): subscale factor to be applied in the nominal
            east-west direction to each cell in the (lon1/lat1)-(lon2/lat2)
            range (e.g., '2' doubles the number of x-direction cells; int>=1).
        lat_subscale (int): subscale factor to be applied in the nominal
            north-south direction to each cell in the (lon1/lat1)-(lon2/lat2)
            range (e.g., '2' doubles the number of y-direction cells; int>=1).
        verbose (bool): True for diagnostic output, False otherwise.

    Returns:
        (newgrid,newgrid_ni,newgrid_nj): Tuple consisting of dictionary of
            newly-regridded subdomain matrices (ref. mitgridfilefields.py for
            names and ordering), and regridded ni, nj subdomain cell counts.

    Note:
        Since cell counts are not stored in binary mitgridfiles, it is necessary
        to use the regridded ni and nj cell counts when reading the grid data
        generated by this routine.

    """

    # read mitgridfile into dictionary of grid matrices:
    mitgrid = gridio.read_mitgridfile( mitgridfile, ni, nj, verbose)

    # for now, assume spherical geoid (perhaps user-specified later):
    geod = pyproj.Geod(ellps='sphere')

    # determine original XG, YG matrix indices corresponding to user input
    # lat/lon corners:
    i1,j1,_ = util.nearest(lon1,lat1,mitgrid['XG'],mitgrid['YG'],geod)
    i2,j2,_ = util.nearest(lon2,lat2,mitgrid['XG'],mitgrid['YG'],geod)

    if verbose:
        print('remeshing {0} x {1} cell grid based on'.format(
            abs(i2-i1),abs(j2-j1)))
        print('located corner points ({0:9.4f},{1:9.4f}) and ({2:9.4f},{3:9.4f})'.format(
            lon1,lat1,lon2,lat2))
        print('resulting grid will be {0} x {1} cells (lon/lat subscale = {2}/{3})'.format(
            abs(i2-i1)*lon_subscale,abs(j2-j1)*lat_subscale,lon_subscale,lat_subscale))

    #
    # Step 1:
    #
    # Based on user-selected extents, create a "plus one" matrix partition
    # consisting of original cell range plus a boundary "ring" one cell wide
    # to allow for computing boundary grid edge values.
    #
    # In this, and subsequent operations, the following grid index notation will
    # be useful:
    #
    #    (i, j)        - original (user-selected) grid indices
    #    (i_cg, jc_cg) - "compute grid" indices (doubled resolution)
    #    (i_ca, jc_ca) - "compute area" indices (doubled resolution)
    #

    # original grid index bounds based on user lon/lat selections:
    ilb, jlb = min(i1,i2), min(j1,j2)
    iub, jub = max(i1,i2), max(j1,j2)

    # "plus one" grid extents:
    iLB, iUB = ilb-1, iub+1
    jLB, jUB = jlb-1, jub+1

    # "compute grid" dimensions, allocation:
    num_compute_grid_rows = (iUB-iLB)*lon_subscale*2 + 1
    num_compute_grid_cols = (jUB-jLB)*lat_subscale*2 + 1
    compute_grid_xg = np.zeros((num_compute_grid_rows,num_compute_grid_cols))
    compute_grid_yg = np.zeros((num_compute_grid_rows,num_compute_grid_cols))

    # map mitgrid values to corresponding locations in compute_grid:

    # index transformation from partitioned grid space to compute grid space:
    i_cg = lambda i,lon_subscale : i*lon_subscale*2
    j_cg = lambda j,lat_subscale : j*lat_subscale*2
    it = np.nditer(
        [mitgrid['XG'][iLB:iUB+1,jLB:jUB+1],
         mitgrid['YG'][iLB:iUB+1,jLB:jUB+1]],
        flags=['multi_index'])
    while not it.finished:
        compute_grid_xg[
            i_cg(it.multi_index[0],lon_subscale),
            j_cg(it.multi_index[1],lat_subscale)] = it[0]
        compute_grid_yg[
            i_cg(it.multi_index[0],lon_subscale),
            j_cg(it.multi_index[1],lat_subscale)] = it[1]
        it.iternext()

    if verbose:
        print('user-selected range:')
        print("mitgrid['XG']:")
        print(mitgrid['XG'][ilb:iub+1,jlb:jub+1])
        print("mitgrid['YG']:")
        print(mitgrid['YG'][ilb:iub+1,jlb:jub+1])

        print('user-selected range, "plus one":')
        print("mitgrid['XG'] plus one:")
        print(mitgrid['XG'][iLB:iUB+1,jLB:jUB+1])
        print("mitgrid['YG'] plus one:")
        print(mitgrid['YG'][iLB:iUB+1,jLB:jUB+1])

        print('user-selected range, plus one, mapped to compute_grid:')
        print('compute_grid_xg:')
        print(compute_grid_xg)
        print('compute_grid_yg:')
        print(compute_grid_yg)

    #
    # Step 2: "fill in" grid cell corner points at resolution given by
    # user-specified subdivision level, times two ("compute grid" resolution):
    #

    # 2a: iterate over compute_grid, filling in x-direction edges according to
    # user-specified subdivisions:

    it = np.nditer(
        [compute_grid_xg[:-1:lon_subscale*2,::lat_subscale*2],
         compute_grid_yg[:-1:lon_subscale*2,::lat_subscale*2]],
        flags=['multi_index'])
    while not it.finished:
        # compute equally-spaced x-edge subdivisions...:
        x_edge_subdivided_lonlats = geod.npts(
            it[0],                                      # lon1
            it[1],                                      # lat1
            compute_grid_xg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1],lat_subscale)],  # lon2
            compute_grid_yg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1],lat_subscale)],  # lat2
            lon_subscale*2-1)                           # n intermediate points
        # ...and store to compute_grid:
        compute_grid_xg[
            i_cg(it.multi_index[0],lon_subscale)+1:i_cg(it.multi_index[0]+1,lon_subscale),
            j_cg(it.multi_index[1],lat_subscale)] = \
            np.array(x_edge_subdivided_lonlats)[:,0]
        compute_grid_yg[
            i_cg(it.multi_index[0],lon_subscale)+1:i_cg(it.multi_index[0]+1,lon_subscale),
            j_cg(it.multi_index[1],lat_subscale)] = \
            np.array(x_edge_subdivided_lonlats)[:,1]
        it.iternext()

    if verbose:
        print('compute_grid after x-edge subdivision:')
        print('compute_grid_xg:')
        print(compute_grid_xg)
        print('compute_grid_yg:')
        print(compute_grid_yg)

    # 2b: with x-direction subdivisions in place, iterate over compute_grid,
    # filling in all y-direction values according to user-specified
    # subdivisions. result will be fully-populated array of corner points:

    it = np.nditer(
        [compute_grid_xg[:,:-1:lat_subscale*2],
         compute_grid_yg[:,:-1:lat_subscale*2]],
        flags=['multi_index'])
    while not it.finished:
        # compute equally-spaced y-edge subdivisions...:
        y_subdivided_lonlats = geod.npts(
            it[0],                                          # lon1
            it[1],                                          # lat1
            compute_grid_xg[
                it.multi_index[0],
                j_cg(it.multi_index[1]+1,lat_subscale)],    # lon2
            compute_grid_yg[
                it.multi_index[0],
                j_cg(it.multi_index[1]+1,lat_subscale)],    # lat2
            lat_subscale*2-1)                               # n intermediate points
        # ...and store to compute_grid:
        compute_grid_xg[
            it.multi_index[0],
            j_cg(it.multi_index[1],lat_subscale)+1:j_cg(it.multi_index[1]+1,lat_subscale)] = \
            np.array(y_subdivided_lonlats)[:,0]
        compute_grid_yg[
            it.multi_index[0],
            j_cg(it.multi_index[1],lat_subscale)+1:j_cg(it.multi_index[1]+1,lat_subscale)] = \
            np.array(y_subdivided_lonlats)[:,1]
        it.iternext()

    if verbose:
        print('compute_grid after y_direction subdivision fill-in:')
        print('compute_grid_xg:')
        print(compute_grid_xg)
        print('compute_grid_yg:')
        print(compute_grid_yg)

    #
    # Step 3: Generate areas for sub-quads at the compute_grid array resolution
    #

    # areas, from cartesian coordinates on the unit sphere, scaled according to
    # mean spherical ellipsoid radius:

    compute_areas = util.squad_uarea(
        util.lonlat2cart(compute_grid_xg,compute_grid_yg)) \
        * np.power(geod.a,2)

    if verbose:
        print('compute_areas:')
        print(compute_areas)

    #
    # Step 4: Create and fill in output quantities based on compute grid data:
    #

    outgrid = {key:None for key in mitgridfilefields.names}

    # since matrix slice operations are from start:(stop-1):stride, define a
    # quantity to make it clear in the following code that the stop point should
    # be inclusive, i.e., start:(stop-1+1):stride

    inclusive = 1

    # compute regridded grid location quantities:
    #   XC - longitude east of center of grid (tracer) cell
    #   YC - latitude north of center of grid (tracer) cell
    #   XG - latitude east of southwest corner of grid (tracer) cell
    #   YG - latitude north of southwest corner of grid (tracer) cell

    # XC, YC directly from compute grid partitions:

    # compute grid partitioning:
    cg_first_i  = lon_subscale*2 + 1
    cg_last_i   = cg_first_i + ((iub-ilb)*lon_subscale-1)*2 + inclusive
    cg_stride_i = 2
    cg_first_j  = lat_subscale*2 + 1
    cg_last_j   = cg_first_j + ((jub-jlb)*lat_subscale-1)*2 + inclusive
    cg_stride_j = 2
    # dbg:
    #print('cg_first_i={0}, cg_last_i={1}, cg_stride_i={2}'.format(cg_first_i,cg_last_i,cg_stride_i))
    #print('cg_first_j={0}, cg_last_j={1}, cg_stride_j={2}'.format(cg_first_j,cg_last_j,cg_stride_j))
    outgrid['XC'] = compute_grid_xg[
        cg_first_i:cg_last_i:cg_stride_i,
        cg_first_j:cg_last_j:cg_stride_j]
    outgrid['YC'] = compute_grid_yg[
        cg_first_i:cg_last_i:cg_stride_i,
        cg_first_j:cg_last_j:cg_stride_j]
    if verbose:
        print("outgrid['XC']:")
        print(outgrid['XC'])
        print("outgrid['YC']:")
        print(outgrid['YC'])

    # XG, YG directly from compute grid partitions:

    # compute grid partitioning:
    cg_first_i  = lon_subscale*2
    cg_last_i   = cg_first_i + (iub-ilb)*lon_subscale*2 + inclusive
    cg_stride_i = 2
    cg_first_j  = lat_subscale*2
    cg_last_j   = cg_first_j + (jub-jlb)*lat_subscale*2 + inclusive
    cg_stride_j = 2
    # dbg:
    #print('cg_first_i={0}, cg_last_i={1}, cg_stride_i={2}'.format(cg_first_i,cg_last_i,cg_stride_i))
    #print('cg_first_j={0}, cg_last_j={1}, cg_stride_j={2}'.format(cg_first_j,cg_last_j,cg_stride_j))
    outgrid['XG'] = compute_grid_xg[
        cg_first_i:cg_last_i:cg_stride_i,
        cg_first_j:cg_last_j:cg_stride_j]
    outgrid['YG'] = compute_grid_yg[
        cg_first_i:cg_last_i:cg_stride_i,
        cg_first_j:cg_last_j:cg_stride_j]
    if verbose:
        print("outgrid['XG']:")
        print(outgrid['XG'])
        print("outgrid['YG']:")
        print(outgrid['YG'])

    # tracer cell-related quantities, RAC, DXG, DYG:
    #   DXG - (tracer) cell face separation in X along southern cell wall
    #   DYG - (tracer) cell face separation in Y along western cell wall
    #   RAC - tracer cell area presented in the vertical direction

    # DXG computed from XG, YG values (simpler, since they're already partitions
    # of compute_grid_xg, compute_grid_yg):

    outgrid['DXG'] = np.zeros(((iub-ilb)*lon_subscale, (jub-jlb)*lat_subscale+1))
    it = np.nditer(
        [outgrid['XG'][:-1,:],   # all rows-1, all cols
         outgrid['YG'][:-1,:]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DXG'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                                  # lon1
            it[1],                                                  # lat1
            outgrid['XG'][it.multi_index[0]+1,it.multi_index[1]],   # lon2
            outgrid['YG'][it.multi_index[0]+1,it.multi_index[1]])   # lat2
        it.iternext()
    if verbose:
        print("outgrid['DXG']:")
        print(outgrid['DXG'])

    # DYG, as was DXG, computed from XG, YG values that are partitioned from
    # compute_grid_xg, compute_grid_yg:

    outgrid['DYG'] = np.zeros(((iub-ilb)*lon_subscale+1, (jub-jlb)*lat_subscale))
    it = np.nditer(
        [outgrid['XG'][:,:-1],  # all rows, all cols-1
         outgrid['YG'][:,:-1]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DYG'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                                  # lon1
            it[1],                                                  # lat1
            outgrid['XG'][it.multi_index[0],it.multi_index[1]+1],   # lon2
            outgrid['YG'][it.multi_index[0],it.multi_index[1]+1])   # lat2
        it.iternext()
    if verbose:
        print("outgrid['DYG']:")
        print(outgrid['DYG'])

    # RAC computed from subcell area sums in compute_areas:

    outgrid['RAC'] = np.zeros(((iub-ilb)*lon_subscale, (jub-jlb)*lat_subscale))

    # compute_areas partitioning:
    ca_first_i  = lon_subscale*2
    ca_last_i   = ca_first_i + ((iub-ilb)*lon_subscale-1)*2 + inclusive
    ca_stride_i = 2
    ca_first_j  = lat_subscale*2
    ca_last_j   = ca_first_j +((jub-jlb)*lat_subscale-1)*2 + inclusive
    ca_stride_j = 2
    # dbg:
    #print('ca_first_i={0}, ca_last_i={1}, ca_stride_i={2}'.format(ca_first_i,ca_last_i,ca_stride_i))
    #print('ca_first_j={0}, ca_last_j={1}, ca_stride_j={2}'.format(ca_first_j,ca_last_j,ca_stride_j))

    # transformation from partitioned, strided compute_areas indices (nditer) to
    # underlying compute_areas indices:
    i_ca = lambda i_n,lon_subscale : 2*i_n + 2*lon_subscale
    j_ca = lambda j_n,lat_subscale : 2*j_n + 2*lat_subscale

    it = np.nditer(
        compute_areas[ca_first_i:ca_last_i:ca_stride_i,ca_first_j:ca_last_j:ca_stride_j],
        flags=['multi_index'])
    while not it.finished:
        outgrid['RAC'][it.multi_index[0],it.multi_index[1]] = \
            it[0] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)  ] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)+1] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)  ,j_ca(it.multi_index[1],lat_subscale)+1]
        it.iternext()
    if verbose:
        print("outgrid['RAC']:")
        print(outgrid['RAC'])

    # vorticity cell-related quantities, DXC, DYC, RAZ
    #   DXC - vorticity cell edge length in X-direction
    #   DYC - vorticity cell edge length in Y-direction
    #   RAZ - vorticity cell area presented in the vertical direction

    # DXC vorticity cell edge lengths computed from compute_grid points since
    # endpoints are centered in tracer cells:

    outgrid['DXC'] = np.zeros(((iub-ilb)*lon_subscale+1, (jub-jlb)*lat_subscale))
    # compute grid partitioning:
    cg_first_i  = lon_subscale*2 - 1
    cg_last_i   = cg_first_i + (iub-ilb)*lon_subscale*2 + inclusive
    cg_stride_i = 2
    cg_first_j  = lat_subscale*2 + 1
    cg_last_j   = cg_first_j + ((jub-jlb)*lat_subscale-1)*2 + inclusive
    cg_stride_j = 2
    # dbg:
    #print('cg_first_i={0}, cg_last_i={1}, cg_stride_i={2}'.format(cg_first_i,cg_last_i,cg_stride_i))
    #print('cg_first_j={0}, cg_last_j={1}, cg_stride_j={2}'.format(cg_first_j,cg_last_j,cg_stride_j))

    # transformation from partitioned, strided nditer space (i_n,j_n) to
    # underlying compute_grid space (i_cg,j_cg):
    i_cg = lambda i_n,lon_subscale : 2*lon_subscale-1 + 2*i_n
    j_cg = lambda j_n,lat_subscale : 2*lat_subscale+1 + 2*j_n

    it = np.nditer(
        [compute_grid_xg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_i],
         compute_grid_yg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_j]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DXC'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                          # lon1
            it[1],                                          # lat1
            compute_grid_xg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1]  ,lat_subscale)],    # lon2
            compute_grid_yg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1]  ,lat_subscale)])    # lat2
        it.iternext()
    if verbose:
        print("outgrid['DXC']:")
        print(outgrid['DXC'])

    # DYC vorticity cell edge lengths computed from compute_grid points since
    # endpoints are centered in tracer cells:

    outgrid['DYC'] = np.zeros(((iub-ilb)*lon_subscale, (jub-jlb)*lat_subscale+1))
    # compute grid partitioning:
    cg_first_i  = lon_subscale*2 + 1
    cg_last_i   = cg_first_i + ((iub-ilb)*lon_subscale-1)*2 + inclusive
    cg_stride_i = 2
    cg_first_j  = lat_subscale*2 - 1
    cg_last_j   = cg_first_j + (jub-jlb)*lat_subscale*2 + inclusive
    cg_stride_j = 2
    # dbg:
    #print('cg_first_i={0}, cg_last_i={1}, cg_stride_i={2}'.format(cg_first_i,cg_last_i,cg_stride_i))
    #print('cg_first_j={0}, cg_last_j={1}, cg_stride_j={2}'.format(cg_first_j,cg_last_j,cg_stride_j))

    # transformation from partitioned, strided nditer space (i_n,j_n) to
    # underlying compute_grid space (i_cg,j_cg):
    i_cg = lambda i_n,lon_subscale : 2*lon_subscale+1 + 2*i_n
    j_cg = lambda j_n,lat_subscale : 2*lat_subscale-1 + 2*j_n

    it = np.nditer(
        [compute_grid_xg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_i],
         compute_grid_yg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_j]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DYC'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                          # lon1
            it[1],                                          # lat1
            compute_grid_xg[
                i_cg(it.multi_index[0]  ,lon_subscale),
                j_cg(it.multi_index[1]+1,lat_subscale)],    # lon2
            compute_grid_yg[
                i_cg(it.multi_index[0]  ,lon_subscale),
                j_cg(it.multi_index[1]+1,lat_subscale)])    # lat2
        it.iternext()
    if verbose:
        print("outgrid['DYC']:")
        print(outgrid['DYC'])

    # RAZ vorticity cell areas computed from subcell areas in compute_areas:

    outgrid['RAZ'] = np.zeros(((iub-ilb)*lon_subscale+1, (jub-jlb)*lat_subscale+1))
    # compute_areas partitioning:
    ca_first_i  = lon_subscale*2 - 1
    ca_last_i   = ca_first_i + (iub-ilb)*lon_subscale*2 + inclusive
    ca_stride_i = 2
    ca_first_j  = lat_subscale*2 - 1
    ca_last_j   = ca_first_j + (jub-jlb)*lat_subscale*2 + inclusive
    ca_stride_j = 2
    # dbg:
    #print('ca_first_i={0}, ca_last_i={1}, ca_stride_i={2}'.format(ca_first_i,ca_last_i,ca_stride_i))
    #print('ca_first_j={0}, ca_last_j={1}, ca_stride_j={2}'.format(ca_first_j,ca_last_j,ca_stride_j))

    # transformation from partitioned, strided compute_areas indices (nditer) to
    # underlying compute_areas indices:
    i_ca = lambda i_n,lon_subscale : 2*lon_subscale -1 + 2*i_n
    j_ca = lambda j_n,lat_subscale : 2*lat_subscale -1 + 2*j_n

    it = np.nditer(
        compute_areas[ca_first_i:ca_last_i:ca_stride_i,ca_first_j:ca_last_j:ca_stride_j],
        flags=['multi_index'])
    while not it.finished:
        outgrid['RAZ'][it.multi_index[0],it.multi_index[1]] = \
            it[0] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)  ] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)+1] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)  ,j_ca(it.multi_index[1],lat_subscale)+1]
        it.iternext()
    if verbose:
        print("outgrid['RAZ']:")
        print(outgrid['RAZ'])

    # "U" cell-related quantities, DXC, DYC, RAZ
    #   DXV - U cell edge length in X-direction between v-points
    #   DYF - U cell edge length in Y-direction between tracer cell faces
    #   RAW - U cell area presented in the vertical direction

    # DXV U cell edge lengths computed from compute_grid points: 

    outgrid['DXV'] = np.zeros(((iub-ilb)*lon_subscale+1,(jub-jlb)*lat_subscale+1))
    # compute grid partitioning:
    cg_first_i  = lon_subscale*2 -1
    cg_last_i   = cg_first_i + (iub-ilb)*lon_subscale*2 + inclusive
    cg_stride_i = 2
    cg_first_j  = lat_subscale*2
    cg_last_j   = cg_first_j + (jub-jlb)*lat_subscale*2 + inclusive
    cg_stride_j = 2

    # transformation from partitioned, strided nditer space (i_n,j_n) to
    # underlying compute_grid space (i_cg,j_cg):
    i_cg = lambda i_n,lon_subscale : 2*lon_subscale-1 + 2*i_n
    j_cg = lambda j_n,lat_subscale : 2*lat_subscale   + 2*j_n

    it = np.nditer(
        [compute_grid_xg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_i],
         compute_grid_yg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_j]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DXV'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                          # lon1
            it[1],                                          # lat1
            compute_grid_xg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1]  ,lat_subscale)],    # lon2
            compute_grid_yg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1]  ,lat_subscale)])    # lat2
        it.iternext()
    if verbose:
        print("outgrid['DXV']:")
        print(outgrid['DXV'])

    # DYF U cell edge lengths computed from compute_grid points:

    outgrid['DYF'] = np.zeros(((iub-ilb)*lon_subscale,(jub-jlb)*lat_subscale))
    # compute grid partitioning:
    cg_first_i  = lon_subscale*2 + 1
    cg_last_i   = cg_first_i + ((iub-ilb)*lon_subscale-1)*2 + inclusive
    cg_stride_i = 2
    cg_first_j  = lat_subscale*2
    cg_last_j   = cg_first_j + ((jub-jlb)*lat_subscale-1)*2 + inclusive
    cg_stride_j = 2
    # dbg:
    #print('cg_first_i={0}, cg_last_i={1}, cg_stride_i={2}'.format(cg_first_i,cg_last_i,cg_stride_i))
    #print('cg_first_j={0}, cg_last_j={1}, cg_stride_j={2}'.format(cg_first_j,cg_last_j,cg_stride_j))

    # transformation from partitioned, strided nditer space (i_n,j_n) to
    # underlying compute_grid space (i_cg,j_cg):
    i_cg = lambda i_n,lon_subscale : 2*lon_subscale+1 + 2*i_n
    j_cg = lambda j_n,lat_subscale : 2*lat_subscale   + 2*j_n

    it = np.nditer(
        [compute_grid_xg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_i],
         compute_grid_yg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_j]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DYF'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                          # lon1
            it[1],                                          # lat1
            compute_grid_xg[
                i_cg(it.multi_index[0]  ,lon_subscale),
                j_cg(it.multi_index[1]+1,lat_subscale)],    # lon2
            compute_grid_yg[
                i_cg(it.multi_index[0]  ,lon_subscale),
                j_cg(it.multi_index[1]+1,lat_subscale)])    # lat2
        it.iternext()
    if verbose:
        print("outgrid['DYF']:")
        print(outgrid['DYF'])

    # RAW vertical face area of U cell computed from subcell areas in
    # compute_areas:

    outgrid['RAW'] = np.zeros(((iub-ilb)*lon_subscale+1,(jub-jlb)*lat_subscale))
    # compute areas partitioning:
    ca_first_i  = lon_subscale*2 - 1
    ca_last_i   = ca_first_i + (iub-ilb)*lon_subscale*2 + inclusive
    ca_stride_i = 2
    ca_first_j  = lat_subscale*2
    ca_last_j   = ca_first_j + ((jub-jlb)*lat_subscale-1)*2 + inclusive
    ca_stride_j = 2
    # dbg:
    #print('ca_first_i={0}, ca_last_i={1}, ca_stride_i={2}'.format(ca_first_i,ca_last_i,ca_stride_i))
    #print('ca_first_j={0}, ca_last_j={1}, ca_stride_j={2}'.format(ca_first_j,ca_last_j,ca_stride_j))

    # transformation from partitioned, strided compute_areas indices (nditer) to
    # underlying compute_areas indices:
    i_ca = lambda i_n,lon_subscale : 2*lon_subscale - 1 + 2*i_n
    j_ca = lambda j_n,lat_subscale : 2*lat_subscale     + 2*j_n

    it = np.nditer(
        compute_areas[ca_first_i:ca_last_i:ca_stride_i,ca_first_j:ca_last_j:ca_stride_j],
        flags=['multi_index'])
    while not it.finished:
        outgrid['RAW'][it.multi_index[0],it.multi_index[1]] = \
            it[0] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)  ] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)+1] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)  ,j_ca(it.multi_index[1],lat_subscale)+1]
        it.iternext()
    if verbose:
        print("outgrid['RAW']:")
        print(outgrid['RAW'])

    # "V" cell-related quantities, DXF, DYU, RAS
    #   DXF - V cell northern edge length in X-direction between u-points
    #   DYU - V cell western edge length in Y-direction
    #   RAS - V cell area presented in the vertical direction

    # DXF V cell edge lengths computed using compute_grid point distances:

    outgrid['DXF'] = np.zeros(((iub-ilb)*lon_subscale,(jub-jlb)*lat_subscale))
    # compute grid partitioning:
    cg_first_i  = lon_subscale*2
    cg_last_i   = cg_first_i + ((iub-ilb)*lon_subscale-1)*2 + inclusive
    cg_stride_i = 2
    cg_first_j  = lat_subscale*2 + 1
    cg_last_j   = cg_first_j + ((jub-jlb)*lat_subscale-1)*2 + inclusive
    cg_stride_j = 2

    # transformation from partitioned, strided nditer space (i_n,j_n) to
    # underlying compute_grid space (i_cg,j_cg):
    i_cg = lambda i_n,lon_subscale : 2*lon_subscale     + 2*i_n
    j_cg = lambda j_n,lat_subscale : 2*lat_subscale + 1 + 2*j_n

    it = np.nditer(
        [compute_grid_xg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_i],
         compute_grid_yg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_j]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DXF'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                          # lon1
            it[1],                                          # lat1
            compute_grid_xg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1]  ,lat_subscale)],    # lon2
            compute_grid_yg[
                i_cg(it.multi_index[0]+1,lon_subscale),
                j_cg(it.multi_index[1]  ,lat_subscale)])    # lat2
        it.iternext()
    if verbose:
        print("outgrid['DXF']:")
        print(outgrid['DXF'])

    # DYU V cell western edge length computed from compute_grid point distances:

    outgrid['DYU'] = np.zeros(((iub-ilb)*lon_subscale+1,(jub-jlb)*lat_subscale+1))
    # compute grid partitioning:
    cg_first_i  = 2*lon_subscale
    cg_last_i   = cg_first_i + (iub-ilb)*2*lon_subscale + inclusive
    cg_stride_i = 2
    cg_first_j  = 2*lat_subscale-1
    cg_last_j   = cg_first_j + (jub-jlb)*2*lat_subscale + inclusive
    cg_stride_j = 2

    # transformation from partitioned, strided nditer space (i_n,j_n) to
    # underlying compute_grid space (i_cg,j_cg):
    i_cg = lambda i_n,lon_subscale : 2*lon_subscale     + 2*i_n
    j_cg = lambda j_n,lat_subscale : 2*lat_subscale - 1 + 2*j_n

    it = np.nditer(
        [compute_grid_xg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_j],
         compute_grid_yg[cg_first_i:cg_last_i:cg_stride_i,cg_first_j:cg_last_j:cg_stride_j]],
        flags=['multi_index'])
    while not it.finished:
        _,_,outgrid['DYU'][it.multi_index[0],it.multi_index[1]] = geod.inv(
            it[0],                                          # lon1
            it[1],                                          # lat1
            compute_grid_xg[
                i_cg(it.multi_index[0]  ,lon_subscale),
                j_cg(it.multi_index[1]+1,lat_subscale)],    # lon2
            compute_grid_yg[
                i_cg(it.multi_index[0]  ,lon_subscale),
                j_cg(it.multi_index[1]+1,lat_subscale)])    # lat2
        it.iternext()
    if verbose:
        print("outgrid['DYU']:")
        print(outgrid['DYU'])

    # RAS vertical face area of V cell computed from subcell areas in
    # compute_areas:

    outgrid['RAS'] = np.zeros(((iub-ilb)*lon_subscale,(jub-jlb)*lat_subscale+1))
    # compute areas partitioning:
    ca_first_i  = 2*lon_subscale
    ca_last_i   = ca_first_i + ((iub-ilb)*lon_subscale-1)*2 + inclusive
    ca_stride_i = 2
    ca_first_j  = 2*lat_subscale - 1
    ca_last_j   = ca_first_j + (jub-jlb)*lat_subscale*2 + inclusive
    ca_stride_j = 2

    # transformation from partitioned, strided compute_areas indices (i_n,j_n) to
    # underlying compute_areas indices:
    i_ca = lambda i_n,lon_subscale : 2*lon_subscale     + 2*i_n
    j_ca = lambda j_n,lat_subscale : 2*lat_subscale - 1 + 2*j_n

    it = np.nditer(
        compute_areas[ca_first_i:ca_last_i:ca_stride_i,ca_first_j:ca_last_j:ca_stride_j],
        flags=['multi_index'])
    while not it.finished:
        outgrid['RAS'][it.multi_index[0],it.multi_index[1]] = \
            it[0] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)  ] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)+1,j_ca(it.multi_index[1],lat_subscale)+1] + \
            compute_areas[i_ca(it.multi_index[0],lon_subscale)  ,j_ca(it.multi_index[1],lat_subscale)+1]
        it.iternext()
    if verbose:
        print("outgrid['RAS']:")
        print(outgrid['RAS'])

    return outgrid, (iub-ilb)*lon_subscale, (jub-jlb)*lat_subscale


def main():
    """Command-line entry point."""

    parser = create_parser()
    args = parser.parse_args()
    (newgrid,ni_regridded,nj_regridded) = regrid(
        args.filename,
        args.ni,
        args.nj,
        args.lon1,
        args.lat1,
        args.lon2,
        args.lat2,
        args.lon_subscale,
        args.lat_subscale,
        args.verbose)
    if args.verbose:
        print('writing {0:s} with ni={1:d}, nj={2:d}...'.
            format(args.outfile,ni_regridded,nj_regridded))
    gridio.write_mitgridfile(args.outfile,newgrid,ni_regridded,nj_regridded)
    if args.verbose:
        print('...done.')

if __name__ == '__main__':
    main()


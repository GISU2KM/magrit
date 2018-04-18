# -*- coding: utf-8 -*-
"""
@author: mz
"""
from geopandas import GeoDataFrame, GeoSeries
from shapely.geometry import Polygon
from shapely.ops import cascaded_union
from shapely import speedups
import ujson as json
from .geo import (
    repairCoordsPole, TopologicalError,
    multi_to_single, try_open_geojson)
from .grid_helpers import (
    square_grid_gen, diams_grid_gen, hex_grid_gen, to_float, make_index)


def get_grid_layer(input_file, height, field_name, grid_shape="square"):
    if speedups.available and not speedups.enabled:
        speedups.enable()
    proj_robinson = (
            "+proj=robin +lon_0=0 +x_0=0 +y_0=0 "
            "+ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    gdf, replaced_id_field = try_open_geojson(input_file)
    if replaced_id_field and field_name == 'id':
        field_name = '_id'
    if not gdf[field_name].dtype in (int, float):
        # gdf.loc[:, field_name] = gdf[field_name].replace('', np.NaN)
        # gdf.loc[:, field_name] = gdf[field_name].astype(float)
        gdf.loc[:, field_name] = gdf[field_name].apply(to_float)
    gdf = gdf[gdf[field_name].notnull()]
    gdf = gdf[gdf.geometry.notnull()]
    gdf.index = range(len(gdf))

    mask = GeoSeries(
        cascaded_union(gdf.geometry.buffer(0)),
#        cascaded_union(gdf.geometry),
        crs=gdf.crs
        ).to_crs(crs=proj_robinson).values[0]

    try:
        mask = mask.buffer(1).buffer(-1)
    except TopologicalError:
        mask = mask.buffer(0)

    gdf.to_crs(crs=proj_robinson, inplace=True)

    cell_generator = {
        "square": square_grid_gen,
        "diamond": diams_grid_gen,
        "hexagon": hex_grid_gen,
        }[grid_shape]

    res_geoms = get_dens_grid2(gdf, height, field_name, mask, cell_generator)

    n_field_name = "".join([field_name, "_densitykm"])
    grid = GeoDataFrame(
        index=range(len(res_geoms)),
        data={'id': [i for i in range(len(res_geoms))],
              n_field_name: [i[1] * 1000000 for i in res_geoms],
              'total': [i[2] for i in res_geoms]},
        geometry=[i[0] for i in res_geoms],
        crs=gdf.crs
        ).to_crs({"init": "epsg:4326"})

    total_bounds = grid.total_bounds
    if total_bounds[0] < -179.9999 or total_bounds[1] < -89.9999 \
            or total_bounds[2] > 179.9999 or total_bounds[3] > 89.9999:
        result = json.loads(grid.to_json())
        repairCoordsPole(result)
        return json.dumps(result)
    else:
        return grid.to_json()


def get_dens_grid2(gdf, height, field_name, mask, cell_generator):
    gdf['area_values'] = gdf.geometry.area
    gdf = multi_to_single(gdf)
    geoms = gdf.geometry
    area_values = gdf['area_values'].values
    index = make_index([g.bounds for g in geoms])
    idx_intersects = index.intersection
    array_values = gdf[field_name].values
    res = []
    for rect, cell in cell_generator(gdf.total_bounds, height):
        idx_poly = list(idx_intersects(rect, objects='raw'))
        if idx_poly:
            p = mask.intersection(Polygon(cell))
            if p:
                t = geoms[idx_poly].intersects(p)
                idx = t[t == True].index
                areas_part = geoms[idx].intersection(p).area.values / area_values[idx]
                _sum = (array_values[idx] * areas_part).sum()
                density = _sum / p.area
                res.append((p, density, _sum))
    return res

# def get_diams_dens_grid(gdf, height, field_name):
#     xmin, ymin, xmax, ymax = gdf.total_bounds
#     height = height * 1.45
#     rows = ceil((ymax-ymin) / height) + 1
#     cols = ceil((xmax-xmin) / height) + 2
#
#     x_left_origin = xmin - height
#     y_bottom_origin = ymin - height
#
#     half_height = (height / 2)
#     geoms = gdf.geometry
#     index = make_index([g.bounds for g in geoms])
#     mask = cascaded_union(gdf.geometry).buffer(5).buffer(-5)
#     array_values = gdf[field_name].values
#
#     res = []
#     for col in range((cols * 2) - 1):
#         t = col % 2
#         x1 = x_left_origin + ((col + 0) * half_height)
#         x2 = x_left_origin + ((col + 1) * half_height)
#         x3 = x_left_origin + ((col + 2) * half_height)
#         for row in range(rows):
#             y1 = y_bottom_origin + (((row * 2) + t) * half_height)
#             y2 = y_bottom_origin + (((row * 2) + t + 1) * half_height)
#             y3 = y_bottom_origin + (((row * 2) + t + 2) * half_height)
#
#             p = Polygon([
#                     (x1,  y2), (x2,  y1),
#                     (x3,  y2), (x2,  y3), (x1,  y2)
#                     ])
#
#             idx_poly = list(index.intersection(p.bounds, objects='raw'))
#             if idx_poly:
#                 p = p.intersection(mask)
#                 if p:
#                     idx = geoms[idx_poly].intersects(p)
#                     idx = idx[idx].index
#                     areas_part = geoms[idx].intersection(p).area.values / geoms[idx].area.values
#                     density = (array_values[idx] * areas_part).sum() / p.area
#                     res.append((p, density))
#
#     return res

# def get_hex_dens_grid(gdf, height, field_name):
#     xmin, ymin, xmax, ymax = gdf.total_bounds
#     rows = ceil((ymax-ymin) / height) + 1
#     cols = ceil((xmax-xmin) / height)
#
#     x_left_origin = xmin - height
#     y_bottom_origin = ymin - height
#
#     half_height = (height / 2)
#     geoms = gdf.geometry
#     index = make_index([g.bounds for g in geoms])
#     mask = cascaded_union(gdf.geometry).buffer(5).buffer(-5)
#     array_values = gdf[field_name].values
#
#     xvertexlo = 0.288675134594813 * height
#     xvertexhi = 0.577350269189626 * height
#     xspacing = xvertexlo + xvertexhi
#     res = []
#
#     for col in range((cols*2) + 1):
#         x1 = x_left_origin + (col * xspacing)	# far left
#         x2 = x1 + (xvertexhi - xvertexlo)	# left
#         x3 = x_left_origin + ((col + 1) * xspacing)	# right
#         x4 = x3 + (xvertexhi - xvertexlo)	# far right
#         t = col % 2
#         for row in range(rows + 1):
#             y1 = y_bottom_origin + (((row * 2) + t) * half_height)	# hi
#             y2 = y_bottom_origin + (((row * 2) + t + 1) * half_height)	# mid
#             y3 = y_bottom_origin + (((row * 2) + t + 2) * half_height)	# lo
#
#             p = Polygon([
#                 (x1, y2), (x2, y1), (x3, y1),
#                 (x4, y2), (x3, y3), (x2, y3), (x1, y2)
#                 ])
#
#             idx_poly = list(index.intersection(p.bounds, objects='raw'))
#             if idx_poly:
#                 p = p.intersection(mask)
#                 if p:
#                     idx = geoms[idx_poly].intersects(p)
#                     idx = idx[idx].index
#                     areas_part = geoms[idx].intersection(p).area.values / geoms[idx].area.values
#                     density = (array_values[idx] * areas_part).sum() / p.area
#                     res.append((p, density))
#
#     return res

#def get_square_dens_grid2(gdf, height, field_name, mask):
#    xmin, ymin, xmax, ymax = gdf.total_bounds
#    rows = ceil((ymax-ymin) / height)
#    cols = ceil((xmax-xmin) / height)
#
#    x_left_origin = xmin
#    x_right_origin = xmin + height
#    y_top_origin = ymax
#    y_bottom_origin = ymax - height
#
#    area_values = gdf.geometry.area
#    geoms = gdf.geometry
#    index = make_index([g.bounds for g in geoms])
#    idx_intersects = index.intersection
#    array_values = gdf[field_name].values
#
#    res = []
#    for countcols in range(cols):
#        y_top = y_top_origin
#        y_bottom = y_bottom_origin
#        for countrows in range(rows):
#            idx_poly = list(idx_intersects(
#                (x_left_origin, y_bottom, x_right_origin, y_top), objects='raw'))
#            if idx_poly:
#                p = mask.intersection(Polygon([
#                        (x_left_origin, y_top), (x_right_origin, y_top),
#                        (x_right_origin, y_bottom), (x_left_origin, y_bottom)
#                        ]))
#                if p:
#                    idx = geoms[idx_poly].intersects(p).index
#                    intersected_geoms = geoms[idx]
#                    areas_part = intersected_geoms.intersection(p).area.values / area_values[idx]
#                    density = (array_values[idx] * areas_part).sum() / p.area
#                    res.append((p, density))
#
#            y_top = y_top - height
#            y_bottom = y_bottom - height
#        x_left_origin = x_left_origin + height
#        x_right_origin = x_right_origin + height
#
#    return res

#if __name__ == "__main__":
#    import ujson as json
#    import timeit
#    import time
#    setup = '''from __main__ import get_grid_layer; f = "/home/mz/dev/magrit/magrit_app/static/data_sample/nuts3_data.geojson"'''
#    cmd1 = '''result = get_grid_layer(f, 115000, "pop1999", "square")'''
#    cmd2 = '''result = get_grid_layer(f, 115000, "pop1999", "square2")'''
#
#    times = []
#    n = 5
#    print('Method 1 :')
#    for i in range(n):
#        t = time.time()
#        result1 = get_grid_layer("/home/mz/dev/magrit/magrit_app/static/data_sample/nuts3_data.geojson", 115000, "pop1999", "square")
#        with open('/tmp/result1.geojson', 'w') as f:
#            f.write(result1)
#        rt = time.time() - t
#        print("{:.3f}".format(rt))
#        times.append(rt)
#    print("Mean : {}".format(sum(times) / n))
#
#    print('Method 2 :')
#    times = []
#    n = 5
#    for i in range(n):
#        t = time.time()
#        result2 = get_grid_layer("/home/mz/dev/magrit/magrit_app/static/data_sample/nuts3_data.geojson", 115000, "pop1999", "square2")
#        with open('/tmp/result2.geojson', 'w') as f:
#            f.write(result2)
#        rt = time.time() - t
#        print("{:.3f}".format(rt))
#        times.append(rt)
#    print("Mean : {}".format(sum(times) / n))

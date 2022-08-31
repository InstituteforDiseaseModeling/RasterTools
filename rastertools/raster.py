import matplotlib.path as plt
import numpy as np
import shapefile

from PIL import Image
from PIL.TiffTags import TAGS
from pathlib import Path
from typing import Any, Dict, List, Union
from rastertools.shape import area_sphere


def raster_clip(raster_file: Union[str, Path], shape_stem: Union[str, Path]) -> Dict[str, Union[float, int]]:
    """Extract data from a raster"""
    assert Path(raster_file).is_file(), "Raster file not found."
    # Raster data
    raster = Image.open(raster_file)

    # Shapefiles
    sf1 = shapefile.Reader(str(shape_stem))
    sf1s = sf1.shapes()
    sf1r = sf1.records()

    # Extract data from raster
    tags = get_tiff_tags(raster)
    point = tags["ModelTiepointTag"]
    scale = tags["ModelPixelScaleTag"]
    x0, y0 = point[3], point[4]
    dx, dy = scale[0], -scale[1]

    # Make sure values are in range
    assert (-180 < x0 < 180 or 0 < x0 < 360) and -85 < y0 < 85, "Tie point coordinates have invalid range."
    assert -1 < dx < 1 and -1 < dy < 1, "Pixel scale has invalid range."

    dat_mat = np.array(raster)
    xy_ints = np.argwhere(dat_mat > 0)
    sparce_data = np.zeros((xy_ints.shape[0], 3), dtype=float)

    # Construct sparce matrix of (long, lat, data)
    sparce_data[:, 0] = x0 + dx * xy_ints[:, 1] + dx / 2.0
    sparce_data[:, 1] = y0 + dy * xy_ints[:, 0] + dy / 2.0
    sparce_data[:, 2] = dat_mat[xy_ints[:, 0], xy_ints[:, 1]]

    # Output dictionary
    data_dict = dict()

    # Iterate of shapes in shapefile
    for k1 in range(len(sf1r)):

        # First (only) field in shapefile record is dotname
        shape_name = sf1r[k1][0]

        # Shapefile shape points
        sfsp = np.array(sf1s[k1].points)

        # Null shape; error in shapefile
        if sfsp.shape[0] == 0:
            raise Exception('Bad shapefile. No parts in shape.')

        # Subset data matrix for clipping
        xy_max = np.max(sfsp, axis=0)
        xy_min = np.min(sfsp, axis=0)
        clip_bool1 = np.logical_and(sparce_data[:, 0] > xy_min[0], sparce_data[:, 1] > xy_min[1])
        clip_bool2 = np.logical_and(sparce_data[:, 0] < xy_max[0], sparce_data[:, 1] < xy_max[1])
        data_clip = sparce_data[np.logical_and(clip_bool1, clip_bool2), :]

        # No population in shape
        if data_clip.shape[0] == 0:
            data_dict[shape_name] = 0
            print(k1 + 1, 'of', len(sf1r), shape_name, data_dict[shape_name])
            continue

        # Track booleans (indicates if lat/long is interior)
        data_bool = np.zeros(data_clip.shape[0], dtype=bool)
        prt_list = list(sf1s[k1].parts) + [len(sfsp)]

        # Iterate over parts of shapefile
        for k2 in range(len(prt_list) - 1):
            shp_prt = sfsp[prt_list[k2]:prt_list[k2 + 1]]
            path_shp = plt.Path(shp_prt, closed=True, readonly=True)
            area_prt = area_sphere(shp_prt)

            # Union of positive areas; intersection with negative areas
            if area_prt > 0:
                data_bool = np.logical_or(data_bool, path_shp.contains_points(data_clip[:, :2]))
            else:
                data_bool = np.logical_and(data_bool, np.logical_not(path_shp.contains_points(data_clip[:, :2])))

        # Record value to dict; print status
        data_dict[shape_name] = int(np.round(np.sum(data_clip[data_bool, 2]), 0))
        print(k1 + 1, 'of', len(sf1r), shape_name, data_dict[shape_name])

    return data_dict


def get_tiff_tags(raster: Image) -> Dict[str, Any]:
    # https://stackoverflow.com/questions/46477712/reading-tiff-image-metadata-in-python
    return {TAGS[t]: raster.tag[t] for t in dict(raster.tag)}

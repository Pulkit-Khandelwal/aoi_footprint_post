""""
Author: Pulkit Khandelwal

Email: pulkit.khandelwal@mail.mcgill.ca
"""

import time
import overpy
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString
from osgeo import gdal, ogr


class OSMdataQuery:
    """
    Define the main class
    """

    def __init__(self):
        self.aoi = None
        self.tag = None
        self.mask = None

    @classmethod
    def query(cls, aoi, tag):
        """
        Query method asks the user for the geoJSON AOI and the required tag to search for

        Args:
            aoi(object): aoi = geoJSON file or coordinates or object or string or polygon
                            For now: geoJSON file and coordinates

            tag(string): the type of structure to be queried in the given aoi
                        The supported queries (for now) are:
                            building
                            highway

        Returns:
            Queries the Overpass API and returns a GeoDataFrame which
            has all the required metadata.


        Example::

                dataframe = osm.query(aoi='path/to/geo_json_aoi.geojson',
                                    tag='building')

        """

        if not isinstance(aoi, (str, list)):
            raise Exception('AOI must be either a geoJSON file (s string)'
                            'or a list of coordinates')

        if not isinstance(tag, str):
            raise Exception('Please, enter a tag for the query')

        # initialize the API using the Overpy Python wrapper
        api = overpy.Overpass()

        # get the s,w,n,e bounds to query the API
        # south: southern limit or minimum latitude
        # west: western limit, usually the minimum longitude
        # north: northern limit or maximum latitude
        # east: eastern limit, usually  maximum longitude

        # read the geoJSON file as a geoDataFrame using geoPandas
        if isinstance(aoi, str):
            input_aoi = gpd.read_file(aoi)
            bounds_coords = input_aoi['geometry'].bounds
            south = bounds_coords['miny'][0]
            west = bounds_coords['minx'][0]
            north = bounds_coords['maxy'][0]
            east = bounds_coords['maxx'][0]

        # read the coordinates
        if isinstance(aoi, list):
            polygon_aoi = Polygon(aoi)
            bounds_coords = polygon_aoi.bounds
            south = bounds_coords[1]
            west = bounds_coords[0]
            north = bounds_coords[3]
            east = bounds_coords[2]

        # query the API using the Overpy syntax
        query_str = '[out:json];way({south:.8f}, {west:.8f}, {north:.8f},' \
                    ' {east:.8f})[{tag:.50s}]; (._;>;); out;'

        query_aoi = query_str.format(north=north, south=south, east=east, west=west, tag=tag)

        print('Querying API for the tag: {tag}'.format(tag=tag))
        start = time.time()
        query_result = api.query(query_aoi)
        end = time.time()
        time_elapsed = end - start

        print('Queried the API in {sec} seconds'.format(sec=time_elapsed))

        # let's store the ways, nodes and relations of the query
        result_ways = query_result.ways

        # let's get all the nodes in all the ways for the given query
        # list of the nodes in each of the ways
        # where each entry is a list

        nodes_of_ways = [way.get_nodes(resolve_missing=True) for way in result_ways]

        # extract the lats/longs in the above list
        list_lon_lat = []
        for way in nodes_of_ways:
            list_of_ways = []
            for node in way:
                list_of_ways.append([float(node.lon), float(node.lat)])
            list_lon_lat.append(list_of_ways)

        # let's create a geoDataFrame to store the query and its metadata
        geopandas_dataframe = gpd.GeoDataFrame()
        geopandas_dataframe['geometry'] = None

        # iterate through each way
        for index, way in enumerate(result_ways):
            coordinates = list_lon_lat[index]
            # check if it is a Polygon, Point or a LineString
            if coordinates[0] == coordinates[-1]:
                geopandas_dataframe.loc[index, 'geometry'] = Polygon(coordinates)
            elif len(coordinates) == 1:
                geopandas_dataframe.loc[index, 'geometry'] = Point(coordinates)
            else:
                geopandas_dataframe.loc[index, 'geometry'] = LineString(coordinates)

            geopandas_dataframe.loc[index, 'way id'] = str(way)
            geopandas_dataframe.loc[index, 'expanded_tag'] = str(way.tags)
            geopandas_dataframe.loc[index, 'queried_tag'] = tag

        geopandas_dataframe.crs = {'init': 'epsg:4326'}

        return geopandas_dataframe

    @classmethod
    def to_geojson(cls, geopandas_dataframe, name='object.geojson', in_utm=False):
        """
        Saves the geoJSON dataframe as a geoJSON file

        Args:
            geopandas_dataframe(geopandas dataframe): takes in a geopandas dataframe
            name: a user specified filename
            in_utm(Boolean): set True if you want to save the geometry in UTM coordinates
                             set False if you want to save the geometry in long/lat
        Returns:
            A GEOJSON object and is saved with the given file name

            json_object: a vector object

        Example::

                osm.to_geojson(name = 'save_as_geojson.geojson')

        """

        # Convert to utm
        if in_utm is True:
            geopandas_dataframe = geopandas_dataframe.to_crs(epsg=3395)

        print('Saving as a geoJSON file as {name}'.format(name=name))
        with open(name, 'w') as file:
            file.write(geopandas_dataframe.to_json())


    @classmethod
    def to_shapefile(cls, geopandas_dataframe, name='shape_file.shp', in_utm=False):
        """
        Converts the geojson_dataframe to a shape file

        Args:
            geopandas_dataframe(geopandas dataframe): takes in a geopandas dataframe
            name(shape file): saves a shape file
            in_utm(Boolean): set True if you want to save the geometry in UTM coordinates
                             set False if you want to save the geometry in long/lat

        Returns:
            Saves a shape file with a given name

        Example::

                OSM.to_shapefile(data_frame, name='my_file.shp')
        """

        # Convert to utm
        if in_utm is True:
            data = geopandas_dataframe.to_crs(epsg=3395)
        else:
            data = geopandas_dataframe

        # If the dataframe has multiple geometries then
        # convert them to a single geometry
        # otherwise a shape file cannot be generated

        # Check which geometry occurs  the most
        data['geom_type'] = None
        for index, row in data.iterrows():
            row['geom_type'] = row['geometry'].geom_type

        max_occur_geom = data['geom_type'].value_counts().idxmax()

        for index, row in data.iterrows():
            geom = row['geometry']
            if geom.geom_type is not max_occur_geom:
                if max_occur_geom == 'LineString':
                    row['geometry'] = LineString(list(geom.exterior.coords))
                if max_occur_geom == 'Polygon':
                    # for let's handle it by deleting the row
                    # though the LineString should be converted to a polygon
                    data.drop(index, inplace=True)
                if max_occur_geom == 'Point':
                    row['geometry'] = Point(list(geom.exterior.coords))

        # Save as a shape file
        data.to_file(name)

    @classmethod
    def to_mask(cls, shape_file, label_color=255, out_mask='mask.tif', x_res=3.125,
                y_res=3.125, cols=None, rows=None):

        """
        Saves the masks for the given aoi with its corresponding labels (given in a dictionary)
        You can either provide of the following:
        cols and rows: in which case the x_res and y_res are automatically calculated
        x_res and y_res: in which case the cols and rows are automatically calculated


        TODO:: Think about labels as label_color=(0, 0, 255)

        Args:
            name: a user specified filename
            label_color: color for the label mask
            x_res(float): resolution fo the x dim (default: 3.125)
            y_res(float): resolution fo the y dim (default: 3.125)
            (Note: default resolution is calculated in the program)
            cols: number of columns in the image
            rows: number of rows in the image
            (Note: Default resolution is of Planetscope Imagery)

        Returns:
            Masks is saved with the given file name
            mask(numpy array): labeled mask image

        Example::

                OSM.to_mask(out_mask='sample_labels.tif', shape_file='sample.shp')
        """

        source_ds = ogr.Open(shape_file)
        source_layer = source_ds.GetLayer()
        x_min, x_max, y_min, y_max = source_layer.GetExtent()

        #Get the dimension of the output image
        if cols is None and rows is None:
            cols = int((x_max - x_min) / x_res)
            rows = int((y_max - y_min) / y_res)

        # Get the resolution of the output image
        if cols is not None and rows is not None:
            x_res = (x_max - x_min) / cols
            y_res = (y_max - y_min) / rows

        raster = gdal.GetDriverByName('GTiff').Create(out_mask, cols, rows, 1, gdal.GDT_Byte)
        raster.SetGeoTransform((x_min, x_res, 0, y_max, 0, -y_res))

        gdal.RasterizeLayer(raster, [1], source_layer, burn_values=[label_color])

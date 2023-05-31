#!/usr/bin/env python
# -*- coding: utf-8 -*-

##     Kartblad Clipper
##     Copyright (C) 2017  Mathieu Tachon

##     This program is free software: you can redistribute it and/or modify
##     it under the terms of the GNU General Public License as published by
##     the Free Software Foundation, either version 3 of the License, or
##     (at your option) any later version.

##     This program is distributed in the hope that it will be useful,
##     but WITHOUT ANY WARRANTY; without even the implied warranty of
##     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##     GNU General Public License for more details.

##     You should have received a copy of the GNU General Public License
##     along with this program.  If not, see <http://www.gnu.org/licenses/>.

##     Installation
##     conda install -yc conda-forge numpy
##     conda install -yc conda-forge gdal
##     conda install -yc conda-forge shapely
##     conda install -yc conda-forge tqdm

##     Bruk
##     LAZ 1.2 retiler
##     Preprosessering
##     - FxTransLas koding av href og vref

##     Scriptet bør kjøres i python env enten via egen Conda installasjon eller via 'Fysak Python'
##     Ta kontakt med Christian Malmquist for hjelp med å få miljøet satt opp. 

##     Oppsett for virtuelt miljø i Fysakpython. 
##     - Git Clone https://bitbucket.statkart.no/scm/prof/ndh_kartbladklipper.git
##     - cmd.exe
##     - cd c:\Fysak\Python3\Scripts
##     - conda create --name kartbladklipper
##     - conda activate kartbladklipper
##     - cd ..\ndh_kartbladklipper
##     - installer dependencies som listet over
##     - python ndh_kartbladklipper.py med argument som vist i prompt

##     Alternativt oppsett fra Conda Env Fil (Testet OK 20200623 mot python v3.7)
##     - @ Anaconda Prompt
##     - conda env create --name kartbladklipper --file kartbladklipper-env.txt

##     Tips for bruk
##     - Legg SOSI avgrensningfil + kartbladklipper folder nært root og uten æøå eller mellomrom
##     - Eks: c:\temp\klipper\
##     - Legg inputfiler til underkatalog input
##     - Eks: c:\temp\klipper\input
##     - Lag destinasjonsfolder for output
##     - Eks: c:\temp\klipper\output
##     - Kall scriptet fra c:\temp\klipper med absolutte stier til både input, output og aoi


import argparse
import os
import sys
from concurrent import futures
from collections import namedtuple, Counter
import re
from tempfile import NamedTemporaryFile
import queue
from subprocess import Popen, PIPE
import itertools
import glob
import time
import textwrap
import logging
import math

import numpy as np
from shapely.geometry import *
from shapely.ops import polygonize_full
from osgeo import ogr, osr
import tqdm


FYSAK_PATH = 'C:\Fysak'

mko_template = """
FysakVersjon >= K1.1

UTFØR

.Fil/Datafil
..Steng 1
!..Bakgrunn 1
..NyIndeks 0
..Datafil <AOI>

.Tegn/Base

.Fil/NyDatafil
..Datafil <outfile>
..Innhold Geodata
..Format SOSI
..Steng 0

.Dig/Kartbladinnd
..Sone <UTMzone>
..Base 1
..Målestokk 1000

.Fil/Utelat
..AlleFramgrunn 1
..SlettIndeks 1
..Rens 1

.Fil/Avslutt
..SlettIndeks 1
..Rens 1"""

## Define namedtuple which will store the needed information for each
## kartblad.
Kartblad = namedtuple('Kartblad', ['name', 'geometry', 'bounds'])
## Get logger.
logger = logging.getLogger(__name__)
## Set basic logging configuration.
formatter = logging.Formatter('%(asctime)s - %(message)s')
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
logger.addHandler(ch)


def run_fysak_mko(mko_template, AOI, path2outputfile, UTMzone):
    """Make kartblad (*.sos) file.

    Replace some fields in the macro template by the user inputs and
    write to (*.mko) file the macro. Then start Fysak with the
    generated macro in a minimized window to create the kartblad file.


    Positional arguments:

    mko_template: string representation of the macro template.
    AOI: absolute path to the (*.sos) file which contains the
    polygon(s) definining the area(s) that should be covered by the
    laser data.
    path2outputfile: absolute path to the output kartblad (*.sos)
    file.
    UTMzone: UTM zone of the project location (supported: 32,33 or
    35).
    """
    mko_template = re.sub(r'<AOI>', '{!r}'.format(AOI).strip('\'\"'),
                          mko_template)
    mko_template = re.sub(r'<outfile>', '{!r}'.format(path2outputfile).strip('\'\"'),
                          mko_template)    
    mko_template = re.sub(r'<UTMzone>', UTMzone, mko_template)
    mko = NamedTemporaryFile(mode='w', suffix='.mko', delete=False)
    mko.write(mko_template)
    mko.close()
    mko_dir = os.path.dirname(mko.name)
    logger.info('Running Fysak : make kartblad file...')
    try:
        p = Popen('{} /m {}'.format(os.path.join(FYSAK_PATH,'Fysak.exe'), mko.name),
                  cwd=mko_dir, universal_newlines=True, stdout=PIPE,
                  stderr=PIPE).communicate()[0]
        if p:
            logger.debug(p)
    finally:
        os.unlink(mko.name)


def add_exe_to_path():
    """Add LAStools executables location to the PATH.
    """
    logger.info('Add to the PATH LAStools executable files location...')
    os.environ['PATH'] = os.path.join(FYSAK_PATH, 'LAStools') + \
      os.pathsep + os.environ['PATH']


def set_env_var():
    """Set the GDAL_DATA environment variable.
    """
    logger.info('Add the GDAL_DATA system variable...')    
    os.environ['GDAL_DATA'] = os.sep.join([FYSAK_PATH,
                                           'GDAL', 'data'])


def run_lasindex(LAZ_directory, ncores):
    """Run spatial indexing of laser data.

    In order to leverage LAStools' fast query machinery, the input
    laser data directory must be populated with *.lax files (index
    files), or the *.laz files must have a builtin spatial index. This
    function generate separate *.lax files in the input laser data
    directory.

    
    Positional arguments:

    LAZ_directory: absolute path to the input laser data directory.
    ncores: number of cores to use for generating the spatial index
    files.
    """
    logger.info('Running spatial indexing...')
    cmd = 'lasindex -i *.laz'
    if ncores > 1:
        cmd += ' -cores {}'.format(ncores)
    p = Popen(cmd, cwd=LAZ_directory, stdout=PIPE,
              stderr=PIPE).communicate()[0]
    if p:
        logger.debug(p)


def SOSI_file_reader(path2filename):
    """Read an input SOSI files with ".FLATE" objects an returns a
    list of 'Kartblad' instances, which are a 3-field namedtuples with
    the fields 'name' (kartblad), 'geometry'
    (shapely.geometry.polygon.Polygon) and 'bounds' (coords: minx miny
    maxx maxy).


    Positional argument:

    path2filename: absolute path to the input SOSI file.
    """
    ## Supported geometry types.
    supported_geom_types = ['KURVE', 'LINJE', 'FLATE']
    ## Register the regex patterns to filter the information from
    ## the input file.
    head_pattern = re.compile(r'\.HODE(?:.|\n)+?(?=\n\.\w)')
    yxz_pattern = re.compile(r'(?<=\.\.NØ)H?(?P<yxz>(?:\s+?(?:-?\d+)\s+?'
                             '(?:-?\d+)(?:[ \t\r\f\v]+?(?:-?\d+))?)+)')
    geom_pattern = re.compile(r'\.(?:{})(?:.|\n)+?(?=\n\.\w)'
                              .format('|'.join(supported_geom_types)))
    kartblad_name_pattern = re.compile(r'\.\.R_KART\s+?(?P<name>(?:\d|-)+)')
    refs_pattern = re.compile(r'\.\.REF(?:.|\n)+?(?=\.\.)')
    knum_pattern = re.compile(r'\.(?:KURVE|LINJE)\s+?(?P<num>\d+)')
    units_pattern = re.compile(r'\.\.\.ENHET\s+?(?P<float>(?:\d|\.)+)')
    origin_pattern = re.compile(r'(?<=\.\.\.ORIGO-NØ)\s+?(?P<y>-?\d+)\s+?'
                                '(?P<x>-?\d+)')    
    ## Store coordinates of ".KURVE" objects and references of
    ## ".FLATE".
    kurve_coords = dict()
    flate_refs = dict()    
    ## Store the resultings polygons in a list.
    kartblad_list = list()
    ## Make a numpy dtype for the coordinates structured array.    
    dtype= [('y', np.float), ('x', np.float)]
    with open(path2filename, 'r', encoding='utf-8') as f:
        contents = f.read()
    ## Extract the information from the file's header.
    head_match = head_pattern.search(contents)
    header = head_match.group().strip()
    all_features = slice(head_match.end(), None)
    logger.info('Finding the units of the {} file...'.format(path2filename))
    units = units_pattern.search(header)
    if not units:
        raise RuntimeError('The {!r} file does not '
                           'have an "ENHET" property!'.format(path2filename))
    try:
        logger.info('Converting the coordinates\' units...')
        units = float(units.group('float'))
    except ValueError:
        raise ValueError('The "ENHET" attribute does not have a '
                         'valid value!')    
    logger.info('Looking for "ORIGO-NØ"...')
    origin = origin_pattern.search(header)
    if origin:
        logger.info('Converting "ORIGO-NØ"...')
        origin_y = int(origin.group('y'))
        origin_x = int(origin.group('x'))
    ## Start iterating over the input file's features.    
    logger.info('Extract the geometry features from the {} file...'.format(path2filename))
    for feature in geom_pattern.finditer(contents[all_features]):
        feature_str = feature.group()
        if feature_str.startswith('.F'):
            ## Feature is ".FLATE".
            kartblad_name = kartblad_name_pattern.search(feature_str).group('name')
            logger.debug('Registering references for kartblad {!r}...'.format(kartblad_name))
            flate_refs[kartblad_name] = re.findall(r'(\d+)', refs_pattern.search(feature_str).group())
        else:
            ## Feature is ".KURVE" or ".LINJE".
            yx_coords = [yxz.group('yxz').strip().split('\n')
                          for yxz in yxz_pattern.finditer(feature_str)]
            yx_coords[:] = [tuple(yxz.strip().split()[:2])
                            for coords in yx_coords
                            for yxz in coords]
            ## Convert the list of coordinates to a numpy
            ## structured array.
            logger.debug('Building the coordinates structured array...')
            arr_yx = np.asarray(yx_coords, dtype=dtype)
            ## Apply units on the XY-coordinates of the feature.
            for field in arr_yx.dtype.names:
                logger.debug('Applying the units factor on the '
                      '{}-coordinates...'.format(field.upper()))
                np.round_(arr_yx[field]*units, decimals=int(math.log10(1/units)),
                          out=arr_yx[field])
            ## Correct the YX-coordinates if ORIGO-NØ is specified in the
            ## input file.
            if origin:
                logger.debug('Applying the "ORIGO-NØ" shift on the feature\'s '
                      'coordinates...')
                arr_yx['y'] += origin_y
                arr_yx['x'] += origin_x
            knum = knum_pattern.search(feature_str).group('num')
            logger.debug('Converting ".KURVE/.LINJE {}" to LineString...'.format(knum))
            geom_shapely = LineString(arr_yx[['x', 'y']].tolist())
            kurve_coords[knum] = geom_shapely
    if flate_refs:
    ## If there are ".FLATE" features, try to convert to polygons the
    ## referred ".KURVE" features.
        ## Set of the registered the referred ".KURVE" numbers.
        kurve_refs = set()
        for kartblad, lines in flate_refs.items():
            ## List of ".KURVE" geometries that define the ".FLATE"
            ## boundary.
            linestrings = [kurve_coords[line] for line in lines]
            ## Polygonize the LineString instances.
            logger.debug('Polygonize kartblad {!r}...'.format(kartblad))
            poly, *rest = polygonize_full(linestrings)
            ## List of Polygon instances.
            poly = [Polygon(p.exterior) for p in poly]
            if poly:
                kartblad_list.append(Kartblad(kartblad, poly[0], poly[0].bounds))
                del poly
    return kartblad_list


def rename_LAZ_output(LAZ_output):
    """Rename the output LAZ file.

    Rename the output LAZ file by removing the appended numbered
    suffix, so that the file name match the kartblad name. Return
    clipped if the laser data was clipped within the kartblad extent,
    or return empty if no laser point was found within the
    corresponding kartblad.


    Positional argument:

    LAZ_output: absolute path to the final output LAZ file without the
    numbered suffix.
    """
    for f in glob.glob(changefileformat(LAZ_output, '*.laz')):
        os.rename(f, LAZ_output)
        return 'clipped'
    else:
        return 'empty'


def clip_many(LAZ_directory, output_directory, kartblad_list, LAZ_EPSG,
              ncores, verbose):
    """Clip the laser data using multiple kartblad polygon geometries.

    Orchestrate the clipping of the laser data against the kartblad
    polygon geometries using concurrency.


    Positional arguments:

    LAZ_directory: absolute path to the input laser data directory.
    output_directory: absolute path to the output directory where the
    clipped laser data will be saved.
    kartblad_list: list of 'Kartblad' instances, which are a 3-field
    namedtuples with the fields 'name' (kartblad), 'geometry'
    (shapely.geometry.polygon.Polygon) and 'bounds' (coords: minx miny
    maxx maxy).
    LAZ_EPSG: EPSG code (integer) of the projected coordinate
    reference system of the input LAZ files (supported: 25832, 25833
    or 25835).
    ncores: number of CPU cores to use for clipping the laser data.
    verbose: bool which indicates whether the user wants to run the
    script in verbose/debug mode.
    """
    counter = Counter()
    with futures.ThreadPoolExecutor(max_workers=ncores) as executor:
        future_list = list()
        for k in kartblad_list:
            future = executor.submit(clip_one, LAZ_directory,
                            output_directory, k, LAZ_EPSG)
            future_list.append(future)
        done_iter = futures.as_completed(future_list)
        if not verbose:
            done_iter = tqdm.tqdm(done_iter, ascii=True,
                                  desc='Clipping laser data',
                                  total=len(kartblad_list))
        for future in done_iter:
            res = future.result()
            counter[res] += 1
    return counter


def clip_one(LAZ_directory, output_directory, kartblad, LAZ_EPSG):
    """Clip the laser data against one kartblad polygon geometry.

    Clip the laser data with LAStools (lasclip) using a single feature
    created Shapefile.

    
    Positional arguments:

    LAZ_directory: absolute path to the input laser data directory.
    output_directory: absolute path to the output directory where the
    clipped laser data will be saved.
    kartblad: 'Kartblad' instance, which is a 3-field namedtuple with
    the fields 'name' (kartblad), 'geometry'
    (shapely.geometry.polygon.Polygon) and 'bounds' (coords: minx miny
    maxx maxy).
    LAZ_EPSG: EPSG code (integer) of the projected coordinate
    reference system of the input LAZ files (supported: 25832, 25833
    or 25835).
    """
    ## Create a temporary file.
    tf = NamedTemporaryFile(suffix='.shp', delete=False)
    tf.close()
    ## Create the shapefile with the kartblad geometry.
    create_single_geometry_shapefile(tf.name, LAZ_EPSG, kartblad.geometry)
    poly = tf.name
    bounds = kartblad.bounds
    ## Get the absolute path of the temporary files (*.shp file +
    ## metadata files).
    tempfiles = itertools.chain([poly], getSHPmetadatafiles(poly))
    ## Path to the output LAZ file.
    LAZ_output = os.path.join(output_directory, kartblad.name + '.laz')
    ## Command to run in a separate process.
    cmd = ('lasclip -i *.laz -merged -inside {bounds[0]} {bounds[1]} '
           '{bounds[2]} {bounds[3]} -poly {poly} '
           '-split -o {LAZ_output}'.format(**locals()))
    try:
        p = Popen(cmd, cwd=LAZ_directory, stdout=PIPE, stderr=PIPE,
                  universal_newlines=True).communicate()[0]
        if p:
            logger.debug(p)
    except Exception:
        continue_run = None
        while continue_run.lower() not in ('y', 'n'):
            continue_run = input('An exception occurred when clipping kartblad'
                                 '{kartblad.name!r}:\n'
                                 '{exc[0]} : {exc[1]}\n'
                                 'Do you want to ignore it and continue? (y/n)'
                                 .format(kartblad=kartblad, exc=sys.exc_info()))
        if continue_run == 'n':
            raise
        else:
            pass
    else:
        logger.debug('{} : OK'.format(kartblad.name))
    finally:
        removetmpfiles(tempfiles)
    status = rename_LAZ_output(LAZ_output)
    return status
        

def create_single_geometry_shapefile(output_filename, EPSG, geom):
    """Create a Shapefile with a single polygon feature.


    Positional arguments:

    output_filename: absolute path to the output file.
    EPSG: EPSG code (int) of the projected Spatial Reference System of
    the output file (relevant are: 25832, 25833 and 28535).
    geom: shapely geometric object (shapely.geometry.polygon.Polygon).
    """
    ## Geometry type of output shapefile.
    geom_type = ogr.wkbPolygon
    ## Create a osr.SpatialReference instance.
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(EPSG)
    ## Get the Shapefile driver.
    driver = ogr.GetDriverByName('ESRI Shapefile')
    ## Delete the file with the same path as 'output_filename' if any.
    if os.path.isfile(output_filename):
        os.unlink(output_filename)
    data_source = driver.CreateDataSource(output_filename)
    layer = data_source.CreateLayer('kartblad', srs=srs,
                                    geom_type=geom_type)
    ## Create the polygon geometry on the output layer.
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(ogr.CreateGeometryFromWkt(geom.wkt))
    layer.CreateFeature(feature)
    feature = None
    ## Close the output file.
    data_source = None


def changefileformat(filepath_in, fileformat_out):
    """Change the extension of a file name (or file absolute path).

    Take as input a file name/path to file and an output file format,
    and return the same file name/path to file with the file extension
    replaced by the given output file format.
    
    
    Positional arguments:

    filepath_in: input file name/path to file.
    fileformat_out: output file format (extension).
    """
    return os.path.splitext(filepath_in)[0] + fileformat_out

    
def getSHPmetadatafiles(path2SHP):
    """Get the path of the metadata files of a Shapefile.

    Get as input the absolute path of a shapefile, and return a
    generator of absolute paths of metadata files.


    Positional argument:

    path2SHP: absolute path to the *.shp file.
    """
    return (changefileformat(path2SHP, ext)
            for ext in ('.shx', '.dbf', '.prj'))


def removetmpfiles(path2tmpfiles):
    """Delete some files.

    Take as input an iterable of absolute paths to files and delete
    those files.


    Positional argument:

    path2tmpfiles: iterable of absolute file paths.
    """
    for tf in path2tmpfiles:
        if os.path.isfile(tf):
            os.unlink(tf)

    
def extractprojectedSRSfromSOSI(path2filename):
    """Extract the EPSG code of an input (*.sos) file.

    Read information in a header of a SOSI file and return the
    EPSG code number of the file features' projected SRS. '..KOORDSYS'
    property must be one of 22, 23 or 25. If the '..KOORDSYS' is not
    found in the file, return None.

    
    Positional argument:

    path2filename: absolute path to the input SOSI file.
    """
    head_pattern = re.compile(r'\.HODE(?:.|\n)+?(?=\n\.\w)')    
    SRS_pattern = re.compile(r'(?<=\.\.\.KOORDSYS)\s+?(?P<srs>\d+)')
    with open(path2filename, 'r', encoding='utf-8') as f:
        contents = f.read()
    ## Extract the information from the file's header.
    head_match = head_pattern.search(contents)
    header = head_match.group().strip()
    SRS = SRS_pattern.search(header)
    if SRS:
        return 25810 + int(SRS.group('srs'))
    else:
        return None


def main(**kwargs):
    """Main function that orchestrate the entire clipping process.

    Start by running the macro in Fysak to generate the kartblad file,
    then generate the *.lax file if wanted by the user, and then clip
    the laser data.


    Keyword arguments:

    laz_in: absolute path to the input laser data directory.
    laz_out:: absolute path to the output directory where the clipped
    laser data will be saved.
    aoi: absolute path to the (*.sos) file which contains the polygon(s)
    definining the area(s) that should be covered by the laser data.
    run_indexing: bool that indicates whether the user wants to run the
    spatial indexing of the laser data in the same process.
    ncores: number of CPU cores to use for running the whole script.
    verbose: bool which indicates whether the user wants to run the
    script in verbose/debug mode.
    """
    ## Start profiling the running process.
    t0 = time.time()
    ## Set the logging level according to the verbosity parameter.
    verbose = kwargs['verbose']
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    ## Get the other input parameters.
    LAZ_input_directory = os.path.normpath(kwargs['laz_in'])
    LAZ_output_directory = os.path.normpath(kwargs['laz_out'])
    if not os.path.isdir(LAZ_output_directory):
        os.makedirs(LAZ_output_directory)
    AOI = os.path.normpath(kwargs['aoi'])
    run_indexing = kwargs['run_indexing']
    ncores = kwargs['ncores']
    ## Get the EPSG of the project's spatial reference system.
    SRS = extractprojectedSRSfromSOSI(AOI)
    if SRS is None:
        raise RuntimeError('The "...KOORDSYS" property is missing from '
                           'the {!r} file!'.format(AOI))
    else:
        UTMzone = str(SRS)[-2:]
    ## Get a path of the kartblad temporary file.
    kartblad_file = NamedTemporaryFile(mode='w', suffix='.sos', delete=False)
    kartblad_file.close()
    ## Add the location of LAStools executable files to the PATH.
    add_exe_to_path()
    ## Add the GDAL_DATA environment variable.
    set_env_var()
    ## Run the macro in Fysak to make the kartblad file, and run the
    ## spatial indexing of LAZ files if wanted by the user.
    if run_indexing:
        max_workers = 2
    else:
        max_workers = 1
    with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        to_do = list()
        to_do.append(executor.submit(run_fysak_mko, mko_template, AOI,
                                     kartblad_file.name, UTMzone))
        if run_indexing:
            to_do.append(executor.submit(run_lasindex, LAZ_input_directory,
                                         ncores))
        ## Wait the termination of the thread(s).
        for future in futures.as_completed(to_do):
            _ = future.result()
    ## Read the kartblad file and extract the kartblad polygons.
    logger.info('Read the kartblad file...')
    kartblad_list = SOSI_file_reader(kartblad_file.name)
    os.unlink(kartblad_file.name)
    print('{} kartblad polygons will be used to clip the laser data.'
          .format(len(kartblad_list)))
    print('{} core(s) will be used.'.format(ncores))
    ## Start clipping the data.
    counter = clip_many(LAZ_input_directory, LAZ_output_directory,
                        kartblad_list, SRS, ncores, verbose)
    elapsed = time.time() - t0
    minutes, seconds = divmod(elapsed, 60)
    hours, minutes = divmod(minutes, 60)
    formatted_time = str()
    if hours:
        formatted_time += ' {}h'.format(int(hours))
    if minutes:
        formatted_time += ' {}m'.format(int(minutes))
    if seconds:
        formatted_time += ' {:.1f}s'.format(seconds)
    print('-' * 30)
    if counter['clipped']:
        print('{} kartblad used to clip the laser data.'.format(counter['clipped']))
    if counter['empty']:
        print('{} empty kartblad.'.format(counter['empty']))
    print('Elapsed time :{}'.format(formatted_time))



## Define optional arguments when running the script from the command
## window.    
parser =  argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
                                  description=textwrap.dedent("""\
                                  Kartblad Clipper
                                  ----------------------------------------------------
                                      This script is intended to be used for clipping
                                      laser data against kartblad polygon geometries."""))
## Inputs.
required_grp = parser.add_argument_group('Required Parameters')
# Input LAZ directory.
required_grp.add_argument('-i', '--input_directory', required=True,
                          metavar='INPUT_LASER_DATA_DIRECTORY', dest='laz_in',
                          help=textwrap.dedent("""\
                          INPUT LASER DATA DIRECTORY
                              Path to the directory where the input 
                              laser data is located."""))
# Output LAZ directory.
required_grp.add_argument('-o', '--output_directory', required=True,
                          metavar='OUTPUT_LASER_DATA_DIRECTORY', dest='laz_out',
                          help=textwrap.dedent("""\
                          OUTPUT LASER DATA DIRECTORY
                              Path to the output directory which the
                              clipped laser data will be saved to."""))
# AOI.
required_grp.add_argument('-a', '--AOI', required=True,
                          metavar='AREA_OF_INTEREST (*.sos)', dest='aoi',
                          help=textwrap.dedent("""\
                          AREA OF INTEREST
                              Path to the input file (*.sos) which
                              contains the polygon(s) defining the
                              area(s) covred by the laser data."""))
## Optimization parameters.
optimization_grp = parser.add_argument_group('Optimization Parameters')
# Run indexing.
optimization_grp.add_argument('--run_indexing', dest='run_indexing',
                              action='store_true',
                              help=textwrap.dedent("""\
                              RUN SPATIAL INDEXING
                                  In order to leverage LAStools' fast query
                                  machinery, the input laser data directory
                                  must be populated with *.lax files
                                  (index files), or the *.laz files must
                                  have a builtin spatial index. If lasindex
                                  was not run on the input laser data files
                                  prior to running this script, one should
                                  use the '--run_indexing' option."""))
# Number of CPU cores to be used.
num_cores = os.cpu_count()
optimization_grp.add_argument('-C', '--ncores', type=int, dest='ncores',
                    choices=list(range(1,num_cores+1)), default=num_cores,
                    help=textwrap.dedent("""\
                    NUMBER OF CORES
                       Number of cores used to run the script.
                       Default is {}.""".format(num_cores)))
# Verbosity.
optimization_grp.add_argument('-v', '--verbose', dest='verbose',
                              action='store_true',
                              help=textwrap.dedent("""\
                              VERBOSITY
                                  Use this option to increase the verbosity
                                  of the logging messages. This can be useful
                                  for debugging."""))
                       
if __name__ == '__main__':
    ## Parse the command-line arguments and run the script
    ## accordingly.
    args = parser.parse_args()
    cli_args = {'laz_in': args.laz_in,
                'laz_out': args.laz_out,
                'aoi': args.aoi,
                'run_indexing': args.run_indexing,
                'ncores': args.ncores,
                'verbose': args.verbose,
                }
    ## Run main function with CLI arguments.
    main(**cli_args)    

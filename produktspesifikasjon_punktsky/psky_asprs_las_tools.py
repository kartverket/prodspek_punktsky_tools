#!/usr/bin/env python
"""
pdal based python tools for manipulating LiDAR datasets managed by Kartverket.

 Installation:
        1) OSGeo  (https://trac.osgeo.org/osgeo4w/)
        2) Docker (https://hub.docker.com/r/cmalmqui/kartverket_punktsky)
        3) Conda  (https://anaconda.org/conda-forge/pdal)

Version History:
1. Working version, singlecore
2. Multicore, inproved JSON handling
Current version: https://github.com/kartverket/produktspesifikasjon_punktsky_tools 

Author: christian.malmquist@karverket.no
Maintained by: https://github.com/orgs/kartverket/teams/proff

Reference Documents: 
    -   https://www.asprs.org/divisions-committees/lidar-division/laser-las-file-format-exchange-activities
    -   https://www.asprs.org/wp-content/uploads/2019/07/LAS_1_4_r15.pdf
    -   https://www.asprs.org/wp-content/uploads/2010/12/LAS_Domain_Profile_Description_Topo-Bathy_Lidar.pdf 
    -   https://sosi.geonorge.no/Produktspesifikasjoner/Punktsky/ 
    -   https://register.geonorge.no/produktspesifikasjoner/fkb-laser/3.0
    -   https://support.geocue.com/wp-content/uploads/2015/01/CueTip-Working-with-LAS-v1.4-Files-in-GeoCue.pdf    

"""

__author__      = "Christian Malmquist"
__copyright__   = "Norwegian Mapping Authority"
__version__     = "2"
__maintainer__  = "Christian Malmquist"
__email__       = "christian.malmquist@kartverket.com"
__status__      = "Working"

# Dependencies
from concurrent import futures
import glob
import json
from multiprocessing import Process
from pathlib import Path
import pdal     

def exc_func_in_proc(func, *args, **kwargs) -> None:
    proc = Process(
        target=func,
        args=tuple(args),
        kwargs=kwargs,
    )
    proc.start()
    proc.join()
    proc.close()

def psky_tag14(ifile,ofile,epsg,sensorsys):
    
    pipeline = [
        {
            "type": "readers.las",
            "filename": ifile,
        },
        {
            "type": "writers.las",
            "forward": "all",
            "extra_dims": "all",
            "system_id": f"{sensorsys}",
            "minor_version": 4,
            "dataformat_id": 6,
            "compression": "laszip",
            "a_srs": f"{epsg}",
            "filename": f"{ofile}"
        }
    ]
    pipeline_json = json.dumps(pipeline)

    # Run PDAL Pipeline
    pipeline = pdal.Pipeline(pipeline_json)
    count = pipeline.execute_streaming()
    #arrays = pipeline.arrays
    #metadata = pipeline.metadata
    #logger = pipeline.log    

def worker_tag14():
    lasifiles = [Path(f) for f in glob.glob(ifolder)]
    with futures.ThreadPoolExecutor(num_workers) as executor:
        to_do = dict()
        file_count = 0
        for lasif in lasifiles:
            lasof = Path(ofolder, lasif.name).as_posix()
            future = executor.submit(
                exc_func_in_proc,
                psky_tag14,
                lasif.as_posix(),
                lasof,
                a_srs,
                system_id,
            )
            to_do[future] = lasif.as_posix()
            file_count += 1
        print("Start tagging files")
        for count, future in enumerate(futures.as_completed(to_do), 1):
            print(
                f"File tagged [{count}/{file_count} ({count/file_count*100: >4.1f}%)]: "
                f"{to_do[future]!r}"
            )

def psky_12_to_14(ifile,ofile,epsg,sensorsys):
    
    pipeline = [
        {
            "type": "readers.las",
            "filename": ifile,
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 21 WHERE Classification == 24"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 40 WHERE Classification == 26"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 41 WHERE Classification == 27"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 42 WHERE Classification == 28"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 43 WHERE Classification == 29"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 44 WHERE Classification == 30"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 45 WHERE Classification == 31"
        },
        {
            "type": "writers.las",
            "forward": "all",
            "extra_dims": "all",
            "system_id": f"{sensorsys}",
            "minor_version": 4,
            "dataformat_id": 6,
            "compression": "laszip",
            "a_srs": f"{epsg}",
            "filename": f"{ofile}"
        }
    ]
    pipeline_json = json.dumps(pipeline)

    # Run PDAL Pipeline
    pipeline = pdal.Pipeline(pipeline_json)
    count = pipeline.execute_streaming()
    #arrays = pipeline.arrays
    #metadata = pipeline.metadata
    #logger = pipeline.log        

def worker_12_to_14():
    lasifiles = [Path(f) for f in glob.glob(ifolder)]
    with futures.ThreadPoolExecutor(num_workers) as executor:
        to_do = dict()
        file_count = 0
        for lasif in lasifiles:
            lasof = Path(ofolder, lasif.name).as_posix()
            future = executor.submit(
                exc_func_in_proc,
                psky_12_to_14,
                lasif.as_posix(),
                lasof,
                a_srs,
                system_id,
            )
            to_do[future] = lasif.as_posix()
            file_count += 1
        print("Start converting files from 1.2 to 1.4")
        for count, future in enumerate(futures.as_completed(to_do), 1):
            print(
                f"File converted [{count}/{file_count} ({count/file_count*100: >4.1f}%)]: "
                f"{to_do[future]!r}"
            )

def psky_14_to_12(ifile,ofile):
    
    pipeline = [
        {
            "type": "readers.las",
            "filename": ifile,
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 24 WHERE Classification == 21"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 26 WHERE Classification == 40"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 27 WHERE Classification == 41"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 28 WHERE Classification == 42"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 29 WHERE Classification == 43"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 30 WHERE Classification == 44"
        },
        {
            "type":"filters.assign",
            "value" : "Classification = 31 WHERE Classification == 45"
        },
        {
            "type": "writers.las",
            "forward": "header",
            "minor_version":2,
            "dataformat_id":3,
            "compression":"laszip",
            "filename": "{ofile}"
        }
    ]
    pipeline_json = json.dumps(pipeline)

    # Run PDAL Pipeline
    pipeline = pdal.Pipeline(pipeline_json)
    count = pipeline.execute_streaming()
    #arrays = pipeline.arrays
    #metadata = pipeline.metadata
    #logger = pipeline.log    

def worker_14_to_12():
    lasifiles = [Path(f) for f in glob.glob(ifolder)]
    with futures.ThreadPoolExecutor(num_workers) as executor:
        to_do = dict()
        file_count = 0
        for lasif in lasifiles:
            lasof = Path(ofolder, lasif.name).as_posix()
            future = executor.submit(
                exc_func_in_proc,
                psky_14_to_12,
                lasif.as_posix(),
                lasof,
            )
            to_do[future] = lasif.as_posix()
            file_count += 1
        print("Start converting files from 1.4 to 1.2")
        for count, future in enumerate(futures.as_completed(to_do), 1):
            print(
                f"File converted [{count}/{file_count} ({count/file_count*100: >4.1f}%)]: "
                f"{to_do[future]!r}"
            )

if __name__ == "__main__":
    #MACHINE VARIABLES
    num_workers = 8 # Have fun, as many workers as the number of cores you have available :)

    #DO WORK
    ## Sett ønsket arbeidsoppgave til True og juster prosjektparametre

    # Tag LAS header
    ## Innholdet i filen er uendret, men header tagges med koordinatsystem og sensorsystem som definert i Produktspesifikasjon Punktsky
    ## "system_id" = sensorsystem    = https://github.com/ASPRSorg/LAS/wiki/Standard-System-Identifiers#system-code-table 
    ## "a_srs"     = koordinatsystem = EPSG:5972 eller EPSG:5973 eller EPSG:5975
    if True:
        a_srs     = "EPSG:5972"
        system_id = "0000"
        ifolder = r"C:\projects\pskytools\las14\*.laz" 
        ofolder = r"C:\projects\pskytools\las14_tagged"
        worker_tag14()

    # Konverter LAS 1.4 til LAS 1.2
    ## Filen konverteres ned til 1.2 og klassekoder remappes til FKB-Laser
    ## Merk: konverteringen er destruktiv (scan angle resolution, scanner channel, return numbers, classes over 32, timing)
    if False:
        ifolder = r"C:\projects\pskytools\las14\*.laz" 
        ofolder = r"C:\projects\pskytools\las12_test"
        worker_14_to_12()
    
    # Konverter LAS 1.2 til LAS 1.4
    ## Filen konverteres opp til 1.4 og klassekoder remappes til Produktspesifikasjon Punktsky
    if False:
        a_srs     = "EPSG:5972"
        system_id = "AOCZ2"        
        ifolder = r"C:\projects\pskytools\las12_test\*.laz" 
        ofolder = r"C:\projects\pskytools\las14_test"
        worker_12_to_14()                         

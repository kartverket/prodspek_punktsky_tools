#!/usr/bin/env python
"""
pdal based python tools for interacting with kartverket lidar datasets 

 Installation of Python Environment:
        1) OSGeo  (https://trac.osgeo.org/osgeo4w/)
        2) Docker (https://hub.docker.com/r/cmalmqui/kartverket_punktsky)
        3) Conda  (https://anaconda.org/conda-forge/pdal)
                

Version History:
V0: 	Working version 

Author: christian.malmquist@karverket.no"""

__author__      = "Christian Malmquist"
__copyright__   = "Norwegian Mapping Authority"
__version__     = "0.1"
__maintainer__  = "Christian Malmquist"
__email__       = "christian.malmquist@kartverket.com"
__status__      = "Test"

# Dependencies
import glob
import pdal     

def psky_tag14(ifile,ofile,epsg,sensorsys):
    
    # workaround for windows path separator in json
    # https://stackoverflow.com/questions/59033154/escaping-single-and-double-backslash-from-json
    ifile = ifile.replace("\\","\\\\")
    ofile = ofile.replace("\\","\\\\")

    worker = f"""
[
    "{ifile}",
    {{
        "type":"writers.las",
        "forward": "header",
        "system_id": "{sensorsys}",
        "minor_version":4,
        "compression":"laszip",
        "a_srs":"{epsg}",
        "filename": "{ofile}"
    }}
]
"""
    # Run PDAL Pipeline
    pipeline = pdal.Pipeline(worker)
    count = pipeline.execute()
    #arrays = pipeline.arrays
    # MERK: pipeline.arrays snubler mot numpy.version.version = 1.20.2 distribuert via OSGeo4W

    #metadata = pipeline.metadata
    # MERK: metadata tryner på særnårske tegn i 1.2
    # "PCSCitationGeoKey: UTM sone 33, basert på EUREF89 (ETRS89/UTM)"
    logger = pipeline.log    

def psky_12_to_14(ifile,ofile):
    
    # workaround for windows path separator in json
    # https://stackoverflow.com/questions/59033154/escaping-single-and-double-backslash-from-json
    ifile = ifile.replace("\\","\\\\")
    ofile = ofile.replace("\\","\\\\")

    worker = f"""
[
    "{ifile}",
    {{
        "type":"filters.assign",
        "value" : "Classification = 21 WHERE Classification == 24",
        "value" : "Classification = 40 WHERE Classification == 26",
        "value" : "Classification = 41 WHERE Classification == 27",
        "value" : "Classification = 42 WHERE Classification == 28",
        "value" : "Classification = 43 WHERE Classification == 29",
        "value" : "Classification = 44 WHERE Classification == 30",
        "value" : "Classification = 45 WHERE Classification == 31"

    }},
    {{
        "type":"writers.las",
        "forward": "header",
        "minor_version":4,
        "dataformat_id":6,
        "compression":"laszip",
        "filename": "{ofile}"
    }}
]
"""
    # Run PDAL Pipeline
    pipeline = pdal.Pipeline(worker)
    count = pipeline.execute()
    logger = pipeline.log

def psky_14_to_12(ifile,ofile):
    
    # workaround for windows path separator in json
    # https://stackoverflow.com/questions/59033154/escaping-single-and-double-backslash-from-json
    ifile = ifile.replace("\\","\\\\")
    ofile = ofile.replace("\\","\\\\")

    worker = f"""
[
    "{ifile}",
    {{
        "type":"filters.assign",
        "value" : "Classification = 24 WHERE Classification == 21",
        "value" : "Classification = 26 WHERE Classification == 40",
        "value" : "Classification = 27 WHERE Classification == 41",
        "value" : "Classification = 28 WHERE Classification == 42",
        "value" : "Classification = 29 WHERE Classification == 43",
        "value" : "Classification = 30 WHERE Classification == 44",
        "value" : "Classification = 31 WHERE Classification == 45"

    }},
    {{
        "type":"writers.las",
        "forward": "header",
        "minor_version":2,
        "dataformat_id":3,
        "compression":"laszip",
        "filename": "{ofile}"
    }}
]
"""
    # Run PDAL Pipeline
    pipeline = pdal.Pipeline(worker)
    count = pipeline.execute()
    logger = pipeline.log

#USER VARIABLES

#INPUT / OUTPUT
ifolder = r"C:\_TMP\las12\*.laz"
ofolder = r"C:\_TMP\las14"

## "system_id" = sensorsystem    = https://github.com/ASPRSorg/LAS/wiki/Standard-System-Identifiers#system-code-table 
## "a_srs"     = koordinatsystem = EPSG:5972 eller EPSG:5973 eller EPSG:5975
a_srs     = "EPSG:5973"
system_id = "OCZ2"


lasifiles = glob.glob(ifolder)
totfiles = len(lasifiles)
counter = 1
for lasif in lasifiles:
    print(f"{counter}/{totfiles} ({counter/totfiles*100: >4.1f}%) - {lasif}")
    lasof = ofolder+"\\"+lasif.split("\\")[-1]
    #psky_tag14(lasif,lasof,a_srs,system_id)
    #psky_14_to_12(lasif,lasof)
    psky_12_to_14(lasif, lasof)
    counter = counter+1
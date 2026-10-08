"""Bounded four-band NAIP NDVI review raster; never modifies LAS or reference labels."""
import argparse
import datetime
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from canopy import greenness
from canopy.run_safeguards import fingerprint,verify_fingerprint


def build(image,metadata,output,threshold=.3):
    import arcpy
    import numpy as np
    from canopy import common
    image=Path(image);metadata=Path(metadata);output=Path(output)
    if output.exists(): raise FileExistsError('Choose a new greenness output directory')
    record=json.loads(metadata.read_text())
    if record.get('source')!='NAIP' or record.get('band_mapping')!={'red':1,'green':2,'blue':3,'nir':4}:
        raise ValueError('Verified NAIP RGB/NIR band metadata required; RGB previews are insufficient')
    datetime.date.fromisoformat(record['survey_date'])
    verify_fingerprint(record['image'],image)
    raster,cell=common.grid(str(image),max_cells=4_000_000)
    if int(arcpy.GetRasterProperties_management(str(image),'BANDCOUNT')[0])!=4:
        raise ValueError('Four-band input required')
    if not -1<=threshold<=1: raise ValueError('NDVI threshold must be between -1 and 1')
    # Cast in ArcGIS before replacing NoData with NaN, avoiding uint8 NaN casts.
    bands=arcpy.RasterToNumPyArray(arcpy.sa.Float(str(image)),nodata_to_value=np.nan)
    value=greenness.ndvi(bands[0],bands[3])
    flags=greenness.screen(value,threshold)
    output.mkdir(parents=True)
    path=output/'ndvi_review.tif'
    arcpy.NumPyArrayToRaster(np.where(np.isfinite(value),value,-9999).astype(np.float32),
                            arcpy.Point(raster.extent.XMin,raster.extent.YMin),cell,cell,-9999).save(str(path))
    arcpy.management.DefineProjection(str(path),raster.spatialReference)
    result={'status':'REVIEW_SCREEN_ONLY','image':fingerprint(image),'metadata':fingerprint(metadata),
            'survey_date':record['survey_date'],'source_record':record,'threshold':threshold,
            'band_mapping':record['band_mapping'],'ndvi':str(path),'cell_size_m':cell,
            'counts':{name:int((flags==name).sum()) for name in ('LOW_GREENNESS_REVIEW','GREEN_SPECTRAL_SUPPORT','UNKNOWN')},
            'warning':'Low greenness is not proof of roof or non-tree. No LAS classes or labels changed.'}
    verify_fingerprint(record['image'],image)
    (output/'review.json').write_text(json.dumps(result,indent=2))
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path);p.add_argument('metadata',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--threshold',type=float,default=.3)
    args=p.parse_args(argv)
    from canopy import licensing
    with licensing.extensions('Spatial'):
        result=build(args.image,args.metadata,args.output,args.threshold)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

"""Inspect a dated Nearmap Custom WMS and export one georeferenced pilot image.

Keep the secret-bearing Custom WMS URL in a private text file, never on the CLI.
"""
import argparse
import json
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.transform import from_bounds
import requests

PILOT_BBOX=(428100.0,4504100.0,428400.0,4504400.0)  # EPSG:6341
DATE=re.compile(r'(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)')

def local(tag):
    return tag.rsplit('}',1)[-1]

def child_text(node,tag):
    return next((x.text or '' for x in node if local(x.tag)==tag),'').strip()

def read_service(path):
    url=Path(path).read_text(encoding='utf-8').strip()
    split=urlsplit(url)
    if split.scheme!='https' or split.hostname!='api.nearmap.com' or '/wms/v1/places/' not in split.path or '/apikey/' not in split.path:
        raise ValueError('The file must contain a Nearmap Custom WMS HTTPS URL from MyAccount.')
    return url

def request(service,params):
    try:
        response=requests.get(service,params=params,timeout=90)
    except requests.RequestException as exc:
        raise RuntimeError('Nearmap WMS request failed; check the service connection.') from None
    if response.status_code!=200:
        raise RuntimeError(f'Nearmap WMS returned HTTP {response.status_code}; check access and the service setup.')
    return response

def layers_from_capabilities(body):
    root=ET.fromstring(body)
    if root.attrib.get('version')!='1.1.1':
        raise ValueError('Expected WMS 1.1.1 capabilities; verify the Custom WMS service.')
    rows=[]
    def visit(node,inherited):
        own=set(inherited)
        for c in node:
            if local(c.tag)=='SRS' and c.text: own.update(c.text.split())
        name=child_text(node,'Name');title=child_text(node,'Title')
        dates=DATE.findall(title+' '+name)
        if name and dates:
            rows.append({'name':name,'title':title,'dates':sorted(set(dates)),'srs':sorted(own)})
        for c in node:
            if local(c.tag)=='Layer': visit(c,own)
    for node in root.iter():
        if local(node.tag)=='Layer':
            visit(node,set());break
    return rows

def capabilities(service):
    response=request(service,{'SERVICE':'WMS','REQUEST':'GetCapabilities','VERSION':'1.1.1'})
    try: return layers_from_capabilities(response.content)
    except ET.ParseError:
        raise RuntimeError('Nearmap did not return parseable WMS capabilities.') from None

def request_bbox(srs):
    if srs=='EPSG:6341': return PILOT_BBOX
    transform=Transformer.from_crs('EPSG:6341',srs,always_xy=True)
    west,south,east,north=PILOT_BBOX
    xy=[transform.transform(x,y) for x,y in [(west,south),(east,south),(east,north),(west,north)]]
    return (min(x for x,y in xy),min(y for x,y in xy),max(x for x,y in xy),max(y for x,y in xy))

def export(service,layer,date,out,width,height,rows):
    matching=[r for r in rows if r['name']==layer and date in r['dates']]
    if len(matching)!=1:
        raise ValueError('Select an exact dated layer name and date printed by the list command.')
    supported=matching[0]['srs']
    srs=next((s for s in ('EPSG:6341','EPSG:3857','EPSG:4326') if s in supported),None)
    if not srs: raise ValueError('The dated layer has no supported EPSG:6341, 3857, or 4326 SRS.')
    bbox=request_bbox(srs)
    params={'SERVICE':'WMS','VERSION':'1.1.1','REQUEST':'GetMap','LAYERS':layer,
            'STYLES':'','SRS':srs,'BBOX':','.join(f'{n:.8f}' for n in bbox),
            'WIDTH':width,'HEIGHT':height,'FORMAT':'image/jpeg','TRANSPARENT':'FALSE'}
    response=request(service,params)
    if 'image/' not in response.headers.get('Content-Type',''):
        raise RuntimeError('GetMap did not return an image; check the dated layer and AOI.')
    try: array=np.asarray(Image.open(BytesIO(response.content)).convert('RGB'))
    except Exception: raise RuntimeError('GetMap response was not a readable image.') from None
    if array.shape[:2]!=(height,width):
        raise RuntimeError('GetMap image dimensions differ from the requested tile.')
    if out.exists(): raise FileExistsError(f'Output already exists: {out}')
    out.parent.mkdir(parents=True,exist_ok=True)
    with rasterio.open(out,'w',driver='GTiff',width=width,height=height,count=3,
                       dtype='uint8',crs=srs,transform=from_bounds(*bbox,width,height),
                       compress='deflate',predictor=2,tiled=True) as dst:
        for band in range(3): dst.write(array[:,:,band],band+1)
    metadata={'source':'Nearmap Custom WMS','survey_layer':layer,'survey_date':date,
              'retrieval_note':'Image response from exact dated WMS layer; verify visible coverage and local photo date in Nearmap.',
              'srs':srs,'bbox':bbox,'width':width,'height':height,'output':str(out)}
    out.with_suffix('.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return metadata

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url-file',required=True,type=Path,help='Private file containing the Nearmap Custom WMS URL')
    commands=parser.add_subparsers(dest='command',required=True)
    listing=commands.add_parser('list',help='List survey-date WMS layers')
    listing.add_argument('--year',default='2023')
    fetching=commands.add_parser('fetch',help='Fetch one exact dated layer as GeoTIFF')
    fetching.add_argument('--layer',required=True)
    fetching.add_argument('--date',required=True,help='Exact YYYY-MM-DD survey date listed by list')
    fetching.add_argument('--output',required=True,type=Path)
    fetching.add_argument('--width',type=int,default=2048)
    fetching.add_argument('--height',type=int,default=2048)
    args=parser.parse_args()
    if args.command=='fetch' and (not 256<=args.width<=4096 or not 256<=args.height<=4096):
        parser.error('Width and height must each be 256-4096 pixels.')
    service=read_service(args.url_file)
    rows=capabilities(service)
    if args.command=='list':
        print(json.dumps([r for r in rows if any(d.startswith(args.year) for d in r['dates'])],indent=2))
    else:
        print(json.dumps(export(service,args.layer,args.date,args.output,args.width,args.height,rows),indent=2))

if __name__=='__main__': main()

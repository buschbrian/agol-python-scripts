"""Configure the NEW private review service, map, scene and app; never overwrite review records.

Sources remain read-only, existing public apps/scenes remain unchanged. --go is required for writes.
Resumes using the audit's created.json, refusing mismatched service IDs or any nonprivate review item.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

from review_rules import EDIT_FIELDS

CITY={'xmin':-12459067.21,'ymin':4962105.56,'xmax':-12442851.81,'ymax':4970359.57,
      'spatialReference':{'wkid':102100,'latestWkid':3857}}
WARNING='Unvalidated planning estimates from LiDAR flown October-November 2023; not surveyed or field verified.'
TITLES={'roofs_review':'Roofs and County footprints','trees_review':'CFTree crown outlines',
        'tree_exceptions_review':'CFTree reconstruction exclusions'}
SERVICE_FIELDS={'OBJECTID','GlobalID','created_user','created_date','last_edited_user','last_edited_date',
                'Shape__Area','Shape__Length','SHAPE__Area','SHAPE__Length'}


def write(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf8')


def form(kind):
    desc=('No roof model does not prove demolition. Compare the footprint, 2023 evidence and newer dated imagery; '
          'record whether absence was at the survey or a change afterward.' if kind=='roofs_review' else
          'Draft reconstruction, not a tree census. Crown outlines are convex hulls, not the full 3D meshes. '
          'Roof overlap can be real overhang; cross-tile overlap can be separate trees. Trunk size and position are inferred.')
    return {'title':'Review {SOURCE_ID}' if kind=='roofs_review' else 'Review {MODEL_ID}',
            'description':desc+' Record the evidence capture date, not just today’s review date.',
            'formElements':[
                {'type':'field','fieldName':'REVIEW_STATUS','label':'Review status','inputType':{'type':'combo-box'}},
                {'type':'field','fieldName':'REVIEW_DECISION','label':'Your finding','inputType':{'type':'combo-box'}},
                {'type':'field','fieldName':'EVIDENCE_SOURCE','label':'Evidence source','inputType':{'type':'text-box'},
                 'hint':'Imagery provider / field visit / photo / LiDAR view'},
                {'type':'field','fieldName':'EVIDENCE_DATE','label':'Evidence capture date','inputType':{'type':'text-box'},
                 'hint':'YYYY-MM-DD, year/range, or unknown'},
                {'type':'field','fieldName':'REVIEW_NOTES','label':'Notes and proposed correction','inputType':{'type':'text-area'}}]}


def popup(kind,fields,map_url=None):
    manual=set(EDIT_FIELDS)
    display=[f for f in fields if f['name'] not in SERVICE_FIELDS and not f['name'].lower().startswith('shape')]
    def info(f):
        d={'fieldName':f['name'],'label':f.get('alias',f['name']),'visible':True,'isEditable':f['name'] in manual}
        if f['type']=='esriFieldTypeDouble':d['format']={'places':1,'digitSeparator':True}
        return d
    text=('<b>Review cues, not findings.</b> No hybrid roof model is not proof of demolition. LiDAR: October-November 2023. '
          'County footprint vintage is not established. Record the capture date of imagery or field evidence.'
          if kind=='roofs_review' else
          '<b>Draft CFTree review.</b> The polygon is a convex XY outline of the local mesh, not the full 3D tree. '
          'Trunk diameter and position are inferred, not field measurements. Overlap and edge cues require inspection.')
    if kind=='tree_exceptions_review':
        text='<b>Excluded reconstruction candidate.</b> Point is its highest vegetation return, not a measured stem. No tree mesh was exported.'
    if map_url:text+=f'<p><a href="{map_url}" target="_blank">Open the editing map</a> to save a finding, evidence date and notes.</p>'
    return {'title':TITLES[kind]+(' — {SOURCE_ID}' if kind=='roofs_review' else ' — {MODEL_ID}'),
            'fieldInfos':[info(f) for f in display],
            'popupElements':[{'type':'text','text':text},{'type':'fields','fieldInfos':[info(f) for f in display]}]}


def symbol(kind,color):
    if kind=='tree_exceptions_review':
        return {'type':'esriSMS','style':'esriSMSDiamond','color':color,'size':9,
                'outline':{'color':[255,255,255,255],'width':1}}
    return {'type':'esriSFS','style':'esriSFSSolid','color':color[:3]+[35 if kind=='trees_review' else 65],
            'outline':{'type':'esriSLS','style':'esriSLSSolid','color':color,'width':1.3}}


def renderer(kind):
    colors=[[207,50,63,255],[230,146,20,255],[42,135,174,255],[105,120,111,200]]
    if kind=='trees_review':colors[3]=[41,146,94,220]
    return {'type':'uniqueValue','field1':'PRIORITY','defaultSymbol':symbol(kind,colors[3]),
            'uniqueValueInfos':[{'value':str(i+1),'label':label,'symbol':symbol(kind,colors[i])}
                               for i,label in enumerate(['1 — Evidence gap / excluded reconstruction',
                               '2 — Model or spatial mismatch cue','3 — Edge / overlap context','4 — Routine review'])]}


def map_layer(layer,item_id,kind,ident,where=None,visible=True):
    props=dict(layer.properties)
    node={'id':ident,'title':TITLES[kind],'layerType':'ArcGISFeatureLayer','url':layer.url,'itemId':item_id,
          'visibility':visible,'opacity':1,'minScale':18056 if kind=='trees_review' else 0,
          'popupInfo':popup(kind,[dict(f) for f in props['fields']]),'formInfo':form(kind),
          'layerDefinition':{'drawingInfo':{'renderer':renderer(kind)},'allowGeometryUpdates':False},
          'showLabels':False,'disablePopup':False}
    if where:node['layerDefinition']['definitionExpression']=where
    return node


def context(map_url,scene_url):
    return (f'<p><b>{WARNING}</b></p><p>This private review workspace combines the three-way hybrid buildings with '
            '119,410 CFTree crown outlines from all 61 processing tiles and 75 excluded candidates. Full CFTree 3D meshes '
            'remain local. The outlines are convex XY hulls; their extents can overstate real crowns.</p>'
            '<p><b>Start with the red roofs.</b> There are 481 County footprints without a hybrid model. Amber roofs include '
            'fallback models or low roof support. A missing model can reflect an obsolete footprint, no building at the '
            'survey, limited support, classification, alignment or reconstruction failure. It does not establish demolition.</p>'
            '<p><b>Tree review.</b> Inspect excluded candidates, inferred trunk centers on footprints and cross-tile overlap '
            'candidates. Overhanging trees may legitimately overlap roofs. Tile-edge and overlap flags do not prove an error. '
            'All trunks are inferred; diameters are not measured DBH. This is not a tree census.</p>'
            '<p><b>Dates matter.</b> LiDAR was acquired October-November 2023. County footprint vintage is not established; '
            'basemap imagery capture dates vary by location. Separate absence at the survey from removal or new construction '
            'afterward. Record the evidence source and capture date.</p>'
            '<p><b>Save a finding.</b> Open the editing map, use Edit, select a review feature and enter your finding, '
            'status, evidence source/date and notes; then update/save the feature. Tree outlines appear when you zoom in. '
            'Toggle the all-features layers for routine examples. Photos can be attached to review features.</p>'
            '<p>Measurements are in feet and square feet. Geometry uses the established Web Mercator / ITRF08 alignment. '
            'Review edits stay in these private copies; they do not delete source assets or enter training/reference labels.</p>'
            f'<p><a href="{map_url}" target="_blank">Edit roof and tree findings</a> | '
            f'<a href="{scene_url}" target="_blank">Inspect alongside the 3D buildings</a></p>')


def main():
    p=argparse.ArgumentParser();p.add_argument('--service',required=True);p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--go',action='store_true');a=p.parse_args()
    a.audit.mkdir(parents=True,exist_ok=True)
    from arcgis.gis import GIS,ItemProperties
    from arcgis.features import FeatureLayerCollection
    import arcpy
    gis=GIS('pro');item=gis.content.get(a.service)
    assert item.owner==gis.users.me.username and item.access=='private'
    layers={l.properties.name:l for l in item.layers}
    assert set(layers)==set(TITLES),list(layers)
    manifest=json.loads(a.manifest.read_text())
    for kind,l in layers.items():assert l.query(return_count_only=True)==manifest['layers'][kind]['count']
    plan={'service_id':item.id,'layer_names':list(layers),'sharing':'private','editable_fields':EDIT_FIELDS,
          'geometry_edits':False,'create_delete':False,'source_edits':False}
    write(a.audit/'configuration-plan.json',plan)
    if not a.go:print(json.dumps(plan,indent=2));return
    flc=FeatureLayerCollection.fromitem(item)
    write(a.audit/'service-before.json',dict(flc.properties))
    result=flc.manager.update_definition({'hasStaticData':False,'capabilities':'Query,Update,Editing,Extract',
        'allowGeometryUpdates':False,'editorTrackingInfo':{'enableEditorTracking':True,
        'enableOwnershipAccessControl':False,'allowOthersToUpdate':False,'allowOthersToDelete':False,
        'allowAnonymousToQuery':False}})
    assert result.get('success'),result
    for kind,l in layers.items():
        write(a.audit/f'{kind}-before.json',dict(l.properties))
        fields=[]
        for f in l.properties.fields:
            f=dict(f)
            if f['type'] not in ('esriFieldTypeOID','esriFieldTypeGlobalID') and f['name'] not in SERVICE_FIELDS:
                fields.append({'name':f['name'],'editable':f['name'] in EDIT_FIELDS})
        result=l.manager.update_definition({'allowGeometryUpdates':False,'capabilities':'Query,Update,Editing,Extract',
                                            'fields':fields,'drawingInfo':{'renderer':renderer(kind)}})
        assert result.get('success'),result
    # Fetch fresh properties after schema controls.
    item=gis.content.get(a.service);layers={l.properties.name:l for l in item.layers}
    folder=gis.content.folders.get('Millcreek LiDAR 2023')
    created_path=a.audit/'created.json'
    created=json.loads(created_path.read_text()) if created_path.exists() else {'service':item.id}
    assert created['service']==item.id
    def create(key,typ,title,data,extra=None):
        if key in created:
            existing=gis.content.get(created[key]);assert existing.access=='private'
            return existing
        props=ItemProperties(title=title,item_type=typ,tags=['Millcreek','LiDAR','review','CFTree','2023','planning estimate'],
            snippet='Private roof and tree review copies with feet-based evidence and editable findings. '+WARNING,
            description=WARNING,license_info=WARNING,access_information='Millcreek GIS; Salt Lake Valley 2023 QL1 lidar; County footprints; CFTree.',
            type_keywords=extra)
        made=folder.add(item_properties=props,text=json.dumps(data)).result()
        created[key]=made.id;write(created_path,created)
        print(key,made.id,flush=True)
        return made
    imagery={'title':'World Imagery (capture dates vary)','baseMapLayers':[{'id':'imagery','title':'World Imagery',
        'layerType':'ArcGISTiledMapServiceLayer','url':'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer',
        'visibility':True,'opacity':1}]}
    nodes=[]
    for kind in ['roofs_review','trees_review','tree_exceptions_review']:
        if kind!='tree_exceptions_review':
            all_node=map_layer(layers[kind],item.id,kind,kind+'-all',visible=False)
            all_node['title']='All '+TITLES[kind].lower()+' — toggle for routine review';nodes.append(all_node)
        where="PRIORITY <= 2 AND REVIEW_STATUS <> 'reviewed'" if kind!='tree_exceptions_review' else "REVIEW_STATUS <> 'reviewed'"
        node=map_layer(layers[kind],item.id,kind,kind+'-priority',where)
        node['title']=TITLES[kind]+' — priority review';nodes.append(node)
    bookmarks=[]
    for r in manifest['roofs']['examples'][:3]:
        point=arcpy.PointGeometry(arcpy.Point(r['x'],r['y']),arcpy.SpatialReference(6341)).projectAs(
            arcpy.SpatialReference(3857),'WGS_1984_(ITRF08)_To_NAD_1983_2011').firstPoint
        bookmarks.append({'name':f'No hybrid model — County {r["source_id"]}',
            'extent':{'xmin':point.X-160,'xmax':point.X+160,'ymin':point.Y-120,'ymax':point.Y+120,
                      'spatialReference':{'wkid':102100}}})
    if manifest['trees']['examples']:
        r=manifest['trees']['examples'][0]
        point=arcpy.PointGeometry(arcpy.Point(r['x'],r['y']),arcpy.SpatialReference(6341)).projectAs(
            arcpy.SpatialReference(3857),'WGS_1984_(ITRF08)_To_NAD_1983_2011').firstPoint
        bookmarks.append({'name':'Tree spatial review example','extent':{'xmin':point.X-130,'xmax':point.X+130,
            'ymin':point.Y-100,'ymax':point.Y+100,'spatialReference':{'wkid':102100}}})
    map_data={'operationalLayers':nodes,'baseMap':imagery,'spatialReference':{'wkid':102100},
        'initialState':{'viewpoint':{'targetGeometry':CITY}},'bookmarks':bookmarks,
        'version':'2.35','authoringApp':'Millcreek GIS review preparation','authoringAppVersion':'20261026'}
    webmap=create('map','Web Map','Millcreek roof and tree review',map_data)
    map_url=f'https://www.arcgis.com/apps/mapviewer/index.html?webmap={webmap.id}'
    scene_data=gis.content.get('5b5bdf4a63c9466fad5884039aa7357f').get_data()
    scene_data=copy.deepcopy(scene_data)
    # Existing buildings/terrain are references; new review overlays are draped and do not pretend to be CFTree meshes.
    scene_data.pop('presentation',None)
    scene_nodes=[]
    for n in nodes:
        node=copy.deepcopy(n);node.pop('formInfo',None)
        node['elevationInfo']={'mode':'onTheGround'}
        kind=next(k for k in TITLES if node['id'].startswith(k))
        node['popupInfo']=popup(kind,[dict(f) for f in layers[kind].properties.fields],map_url)
        scene_nodes.append(node)
    scene_data['operationalLayers']+=scene_nodes
    scene_data['baseMap']=copy.deepcopy(imagery)
    scene=create('scene','Web Scene','Millcreek buildings and tree review in 3D',scene_data)
    scene_url=f'https://www.arcgis.com/home/webscene/viewer.html?webscene={scene.id}'
    details=context(map_url,scene_url)
    for obj in [webmap,scene]:
        assert obj.update(item_properties={'description':details,'extent':[[-111.923,40.65],[-111.777,40.71]]})
    appdata={'source':'888910da7fdc4b11ac32825ad2d87816','folderId':folder.properties['id'],'values':{
        'type':'webscene','webscene':scene.id,'title':'Millcreek Roof and Tree Review',
        'splash':True,'splashTitle':'Roof and tree review','splashContent':details,'splashButtonText':'Open review scene',
        'theme':'light','home':True,'search':True,'legend':True,'layerList':True,'layerListOpenAtStart':True,
        'info':True,'detailsContent':details,'detailsOpenAtStart':False,'measure':True,'units':'imperial',
        'measureLinearUnit':'feet','measureAreaUnit':'square-feet','share':False,'fullScreen':True,
        'slides':False,'daylight':True,'elevationProfile':False,'exportToPDF':False,
        'mapA11yDesc':'Private review of County roof mismatches and CFTree convex crown outlines alongside 3D buildings.'}}
    app=create('app','Web Mapping Application','Millcreek Roof and Tree Review',appdata,
        ['Configurable','configurableApp','instantApp','JavaScript','Map','Mapping Site','Online Map','Web Map',
         '3Dscene','sourceId#af151b76c68941d48f41b3031bf1110e'])
    app_url=f'https://{gis.properties.urlKey}.{gis.properties.customBaseUrl}/apps/instant/3dviewer/index.html?appid={app.id}'
    assert app.update(item_properties={'url':app_url,'description':details})
    assert item.update(data={'layers':[{'id':int(l.properties.id),'popupInfo':popup(k,[dict(f) for f in l.properties.fields],map_url),
        'formInfo':form(k),'layerDefinition':{'drawingInfo':{'renderer':renderer(k)}}} for k,l in layers.items()]},
        item_properties={'description':details})
    urls={'app':app_url,'map':map_url,'scene':scene_url,'service_item':item.homepage}
    write(a.audit/'links.json',urls)
    for key,obj in [('map',webmap),('scene',scene),('app',app)]:
        fresh=gis.content.get(obj.id);assert fresh.access=='private'
        write(a.audit/f'{key}-data.json',fresh.get_data())
    verify(gis,item.id,manifest,a.audit,created)
    print(json.dumps(urls,indent=2))


def verify(gis,ident,manifest,audit,created):
    from arcgis.features import FeatureLayerCollection
    item=gis.content.get(ident);flc=FeatureLayerCollection.fromitem(item)
    assert item.access=='private'
    assert flc.properties.allowGeometryUpdates is False
    assert 'Create' not in flc.properties.capabilities and 'Delete' not in flc.properties.capabilities
    checks={}
    for l in item.layers:
        kind=l.properties.name
        count=l.query(return_count_only=True)
        assert count==manifest['layers'][kind]['count']
        assert l.properties.allowGeometryUpdates is False
        fields={f['name']:dict(f) for f in l.properties.fields}
        assert all(fields[n]['editable'] for n in EDIT_FIELDS)
        assert all(not f['editable'] for n,f in fields.items() if n not in EDIT_FIELDS and n not in SERVICE_FIELDS)
        assert fields['REVIEW_STATUS'].get('domain') and fields['REVIEW_DECISION'].get('domain')
        assert l.properties.hasAttachments
        record=l.query(where="REVIEW_STATUS='pending'",out_fields='OBJECTID,REVIEW_NOTES',return_geometry=False,result_record_count=1).features[0]
        old=dict(record.attributes);oid=old['OBJECTID']
        # Newly created review copies only. Test persistence and restore the note; never change a human finding.
        test_note='Automated edit-persistence check; this note will be restored immediately.'
        result=l.edit_features(updates=[{'attributes':{'OBJECTID':oid,'REVIEW_NOTES':test_note}}])
        assert result['updateResults'][0]['success']
        assert l.query(object_ids=str(oid),out_fields='REVIEW_NOTES',return_geometry=False).features[0].attributes['REVIEW_NOTES']==test_note
        result=l.edit_features(updates=[{'attributes':{'OBJECTID':oid,'REVIEW_NOTES':old['REVIEW_NOTES']}}])
        assert result['updateResults'][0]['success']
        assert l.query(object_ids=str(oid),out_fields='REVIEW_NOTES',return_geometry=False).features[0].attributes['REVIEW_NOTES']==old['REVIEW_NOTES']
        checks[kind]={'count':count,'private':True,'review_fields_editable':True,'source_fields_readonly':True,
            'geometry_updates':False,'attachments':True,'coded_findings':True,'edit_persisted_and_restored':True,
            'priority_count':l.query(where='PRIORITY<=2',return_count_only=True)}
        write(audit/f'{kind}-after.json',dict(l.properties))
    webmap=gis.content.get(created['map']).get_data()
    assert sum('formInfo' in n for n in webmap['operationalLayers'])==5
    for n in webmap['operationalLayers']:
        assert [e['fieldName'] for e in n['formInfo']['formElements']]==EDIT_FIELDS
    # Anonymous requests must not expose the private review service.
    import requests
    response=requests.get(item.url+'/0/query',params={'f':'json','where':'1=1','returnCountOnly':'true'},timeout=45).json()
    assert 'error' in response,response
    write(audit/'verification.json',{'layers':checks,'map_forms':5,'private_items':created,
          'anonymous_query_blocked':True,'full_3d_cftree_meshes_published':False})


if __name__=='__main__':main()

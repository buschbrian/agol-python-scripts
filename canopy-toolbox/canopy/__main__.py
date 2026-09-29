"""ArcGIS Pro command-line entry point. Run with python -m canopy."""
import argparse
import json

def main(argv=None):
    parser=argparse.ArgumentParser(description="Canopy inventory: audit, prepare copies, and run tiled estimates")
    commands=parser.add_subparsers(dest="command",required=True)
    audit=commands.add_parser("inventory",help="Read LAS headers and sampled or full class counts without creating LAS statistics")
    audit.add_argument("folder");audit.add_argument("--report",required=True);audit.add_argument("--full",action="store_true")
    idx=commands.add_parser("index-delivery",help="Map LAS header bounds to a feature class, with optional flight dates from a swath index")
    idx.add_argument("folder");idx.add_argument("output")
    idx.add_argument("--swaths",help="Swath-index polygons in the delivery's horizontal CRS")
    idx.add_argument("--date-field",default="DATE_D")
    idx.add_argument("--boundary",help="Polygon(s) whose coverage to measure, e.g. the city; projected if needed")
    idx.add_argument("--tile-index",help="Official tile index in the delivery's horizontal CRS; needs --boundary")
    idx.add_argument("--tile-field",default="Tile_Name")
    idx.add_argument("--label",help="Name for the acquisition record, e.g. '2023 Salt Lake Valley'")
    prepare=commands.add_parser("prepare",help="Extract and classify a new pilot working copy")
    prepare.add_argument("folder");prepare.add_argument("output")
    prepare.add_argument("--extent",type=float,nargs=4,required=True,metavar=("XMIN","YMIN","XMAX","YMAX"))
    prepare.add_argument("--max-vegetation-height",type=float,default=80)
    prepare.add_argument("--classify-noise",action="store_true")
    prepare.add_argument("--building-method",choices=("CONSERVATIVE","STANDARD","AGGRESSIVE"),default="STANDARD")
    prepare.add_argument("--roof-tolerance",type=float,default=3,help="Metres above detected roofs assigned building class; inspect tree overhangs")
    run=commands.add_parser("run",help="Build tiled CHM, then detect and segment one AOI (maximum 4 million cells)")
    run.add_argument("lasd");run.add_argument("output");run.add_argument("--extent",type=float,nargs=4,required=True)
    run.add_argument("--tile-size",type=float,default=200);run.add_argument("--overlap",type=float)
    run.add_argument("--cell-size",type=float,default=.5);run.add_argument("--bands",default="2-6:1.0, 6-12:1.5, 12-20:2.0, 20-:2.5")
    run.add_argument("--smooth",type=int,default=1);run.add_argument("--min-crown-area",type=float,default=3)
    run.add_argument("--source-files",nargs="+");run.add_argument("--source-id")
    run.add_argument("--building-clearance",type=float,default=.35,help="Measured building-above-vegetation separation for same-cell occlusion, in metres")
    run.add_argument("--resume",action="store_true");run.add_argument("--z-metres",action="store_true")
    run.add_argument("--classified-background-zero",action="store_true",help="Declare class 0 to be model-classified non-canopy; never use for unclassified delivery points")
    refine=commands.add_parser("refine-roofs",help="Experimental roof-edge correction on NEW prepared LAS copies")
    refine.add_argument("lasd");refine.add_argument("output")
    refine.add_argument("--method",choices=("plane","local"),default="plane")
    refine.add_argument("--cell-size",type=float)
    refine.add_argument("--edge-distance",type=float)
    refine.add_argument("--below-roof",type=float,default=.35)
    refine.add_argument("--above-roof",type=float)
    refine.add_argument("--min-roof-area",type=float)
    refine.add_argument("--radius",type=float)
    refine.add_argument("--neighbors",type=int)
    refine.add_argument("--min-neighbors",type=int)
    refine.add_argument("--min-votes",type=int)
    refine.add_argument("--max-fit-rmse",type=float)
    refine.add_argument("--max-slope",type=float)
    refine.add_argument("--classes",type=int,nargs="+",choices=(3,4,5))
    gate=commands.add_parser("shape-gate",help="Experimental wall/pole/wire shape evidence: review LAS copies by default; --apply writes a NEW prepared copy")
    gate.add_argument("lasd");gate.add_argument("output")
    gate.add_argument("--extent",type=float,nargs=4,metavar=("XMIN","YMIN","XMAX","YMAX"),help="Gated extent inside the prepared extent (default: all of it)")
    gate.add_argument("--apply",action="store_true",help="Move rule-selected class 3/4/5 points to class 1 in a new prepared dataset")
    gate.add_argument("--classes",type=int,nargs="+",choices=(3,4,5),help="Classes --apply may change (default 4 5)")
    planning=commands.add_parser("planning",help="Terrain, drainage screening, surface and footprint heights (bounded pilot)")
    planning.add_argument("lasd");planning.add_argument("output")
    planning.add_argument("--extent",type=float,nargs=4,required=True)
    planning.add_argument("--footprints");planning.add_argument("--footprint-id")
    planning.add_argument("--cell-size",type=float,default=.5)
    planning.add_argument("--neighborhood",type=float,default=3)
    planning.add_argument("--tpi-radius",type=float,default=10)
    planning.add_argument("--drainage-area",type=float,default=1000)
    planning.add_argument("--contour-interval",type=float,default=2)
    planning.add_argument("--z-metres",action="store_true")
    get=commands.add_parser("fetch",help="Download a LAZ tile manifest with resume and size/point checks; no ArcGIS needed")
    get.add_argument("manifest");get.add_argument("output")
    get.add_argument("--tiles",nargs="+",help="Only these tile names from the manifest")
    get.add_argument("--workers",type=int,default=4,help="Tiles downloaded at once, 1 to 8 (default 4)")
    refs=commands.add_parser("fetch-footprints",help="Fetch reference building footprints for bounded extents (EPSG:6341)")
    refs.add_argument("output")
    refs.add_argument("--extent",type=float,nargs=4,action="append",required=True)
    refs.add_argument("--name",action="append")
    refs.add_argument("--buffer",type=float,default=50)
    refs.add_argument("--osm-json",nargs=5,action="append",default=[],metavar=("PATH","S","W","N","E"))
    refs.add_argument("--overpass",action="store_true")
    recon=commands.add_parser("reconcile-buildings",help="Compare class-6 buildings with reference footprints; review screens, not truth")
    recon.add_argument("lasd");recon.add_argument("output")
    recon.add_argument("--extent",type=float,nargs=4,required=True)
    recon.add_argument("--footprints",required=True);recon.add_argument("--coverage")
    recon.add_argument("--trees");recon.add_argument("--tile")
    try:
        from .building_rules import DEFAULTS as thresholds
    except ImportError:
        thresholds={}
    for key,value in thresholds.items():
        recon.add_argument("--"+key.replace("_","-"),type=float,default=None,help=f"default {value}")
    args=parser.parse_args(argv)
    if args.command=="refine-roofs":
        plane_only={"cell_size":.5,"edge_distance":1,"min_roof_area":25}
        local_only={"radius":1.,"neighbors":16,"min_neighbors":6,"min_votes":3,
                    "max_fit_rmse":.15,"max_slope":1.5,"classes":[4,5]}
        wrong=local_only if args.method=="plane" else plane_only
        for key in wrong:
            if getattr(args,key) is not None:
                parser.error(f"--{key.replace('_','-')} is not valid with --method {args.method}")
        for key,value in {**plane_only,**local_only}.items():
            if getattr(args,key) is None: setattr(args,key,value)
        if args.above_roof is None: args.above_roof=3 if args.method=="plane" else .5
    if args.command=="shape-gate":
        if args.classes and not args.apply: parser.error("--classes is valid only with --apply")
        from . import shape_gate
        dataset=None
        if args.apply:
            from . import preparation
            dataset=preparation.dataset_writer(args.lasd)
        result=shape_gate.run(args.lasd,args.output,args.extent,args.apply,args.classes or (4,5),dataset)
        print(json.dumps({k:v for k,v in result.items() if k not in ("input_files","before","after","sources")},indent=2,default=str))
        return
    if args.command=="fetch":
        from . import fetch
        try: result=fetch.fetch(args.manifest,args.output,args.tiles,args.workers)
        except ValueError as e: parser.error(str(e))
        print(json.dumps(result,indent=2))
        if result["failed"]: raise SystemExit(1)
        return
    if args.command=="fetch-footprints":
        from . import footprints
        if args.name and len(args.name)!=len(args.extent): parser.error("Give one --name per --extent")
        osm=[(row[0],[float(v) for v in row[1:]]) for row in args.osm_json]
        result=footprints.fetch(args.output,args.extent,args.buffer,osm,args.overpass,args.name)
        print(json.dumps({"reference":result["sources"],"coverage":result["coverage"]},indent=2,default=str))
        return
    from . import common,licensing,preparation,pipeline
    if args.command=="inventory":
        result=preparation.inventory(args.folder,sample=not args.full)
        common.write_json(args.report,result)
        print(f"{result['file_count']} files; {result['point_count']:,} points. Report: {args.report}")
    elif args.command=="index-delivery":
        from . import delivery
        result=delivery.index(args.folder,args.output,args.swaths,args.date_field,args.boundary,
                              args.tile_index,args.tile_field,args.label)
        print(f"{result['file_count']} tiles indexed to {result['feature_class']}; facts: {result['facts']}")
    else:
        with licensing.extensions("3D","Spatial"):
            if args.command=="prepare":
                result=preparation.prepare(args.folder,args.output,args.extent,
                                           args.max_vegetation_height,args.classify_noise,roof_tolerance=args.roof_tolerance,
                                           building_method=args.building_method)
            elif args.command=="refine-roofs":
                from . import roofs
                if args.method=="local":
                    result=roofs.refine_local(args.lasd,args.output,args.radius,args.neighbors,args.min_neighbors,
                                             args.min_votes,args.below_roof,args.above_roof,args.max_fit_rmse,
                                             args.max_slope,args.classes)
                else:
                    result=roofs.refine(args.lasd,args.output,args.cell_size,args.edge_distance,
                                        args.below_roof,args.above_roof,args.min_roof_area)
            elif args.command=="planning":
                from . import planning
                result=planning.build(args.lasd,args.output,args.extent,args.footprints,args.footprint_id,
                                      args.cell_size,args.neighborhood,args.tpi_radius,args.drainage_area,
                                      args.contour_interval,"metres" if args.z_metres else None)
            elif args.command=="reconcile-buildings":
                from . import building_rules,buildings
                overrides={key:getattr(args,key) for key in building_rules.DEFAULTS}
                result=buildings.reconcile(args.lasd,args.output,args.extent,args.footprints,args.coverage,
                                          args.trees,args.tile,**overrides)
            else:
                result=pipeline.run(args.lasd,args.output,args.extent,args.tile_size,args.overlap,args.cell_size,
                                    args.bands,args.smooth,args.min_crown_area,args.source_files,args.source_id,
                                    args.resume,"metres" if args.z_metres else None,args.building_clearance,
                                    args.classified_background_zero)
        print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()

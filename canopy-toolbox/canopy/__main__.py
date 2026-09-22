"""ArcGIS Pro command-line entry point. Run with python -m canopy."""
import argparse
import json

def main(argv=None):
    parser=argparse.ArgumentParser(description="Canopy inventory: audit, prepare copies, and run tiled estimates")
    commands=parser.add_subparsers(dest="command",required=True)
    audit=commands.add_parser("inventory",help="Read LAS headers and sampled or full class counts without creating LAS statistics")
    audit.add_argument("folder");audit.add_argument("--report",required=True);audit.add_argument("--full",action="store_true")
    prepare=commands.add_parser("prepare",help="Extract and classify a new pilot working copy")
    prepare.add_argument("folder");prepare.add_argument("output")
    prepare.add_argument("--extent",type=float,nargs=4,required=True,metavar=("XMIN","YMIN","XMAX","YMAX"))
    prepare.add_argument("--max-vegetation-height",type=float,default=80)
    prepare.add_argument("--classify-noise",action="store_true")
    prepare.add_argument("--roof-tolerance",type=float,default=3,help="Metres above detected roofs assigned building class; inspect tree overhangs")
    run=commands.add_parser("run",help="Build tiled CHM, then detect and segment one AOI (maximum 4 million cells)")
    run.add_argument("lasd");run.add_argument("output");run.add_argument("--extent",type=float,nargs=4,required=True)
    run.add_argument("--tile-size",type=float,default=200);run.add_argument("--overlap",type=float)
    run.add_argument("--cell-size",type=float,default=.5);run.add_argument("--bands",default="2-6:1.0, 6-12:1.5, 12-20:2.0, 20-:2.5")
    run.add_argument("--smooth",type=int,default=1);run.add_argument("--min-crown-area",type=float,default=3)
    run.add_argument("--source-files",nargs="+");run.add_argument("--source-id")
    run.add_argument("--building-clearance",type=float,default=.35,help="Measured building-above-vegetation separation for same-cell occlusion, in metres")
    run.add_argument("--resume",action="store_true");run.add_argument("--z-metres",action="store_true")
    refine=commands.add_parser("refine-roofs",help="Experimental roof-edge correction on NEW prepared LAS copies")
    refine.add_argument("lasd");refine.add_argument("output")
    refine.add_argument("--cell-size",type=float,default=.5)
    refine.add_argument("--edge-distance",type=float,default=1)
    refine.add_argument("--below-roof",type=float,default=.35)
    refine.add_argument("--above-roof",type=float,default=3)
    refine.add_argument("--min-roof-area",type=float,default=25)
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
    args=parser.parse_args(argv)
    from . import common,licensing,preparation,pipeline
    if args.command=="inventory":
        result=preparation.inventory(args.folder,sample=not args.full)
        common.write_json(args.report,result)
        print(f"{result['file_count']} files; {result['point_count']:,} points. Report: {args.report}")
    else:
        with licensing.extensions("3D","Spatial"):
            if args.command=="prepare":
                result=preparation.prepare(args.folder,args.output,args.extent,
                                           args.max_vegetation_height,args.classify_noise,roof_tolerance=args.roof_tolerance)
            elif args.command=="refine-roofs":
                from . import roofs
                result=roofs.refine(args.lasd,args.output,args.cell_size,args.edge_distance,
                                    args.below_roof,args.above_roof,args.min_roof_area)
            elif args.command=="planning":
                from . import planning
                result=planning.build(args.lasd,args.output,args.extent,args.footprints,args.footprint_id,
                                      args.cell_size,args.neighborhood,args.tpi_radius,args.drainage_area,
                                      args.contour_interval,"metres" if args.z_metres else None)
            else:
                result=pipeline.run(args.lasd,args.output,args.extent,args.tile_size,args.overlap,args.cell_size,
                                    args.bands,args.smooth,args.min_crown_area,args.source_files,args.source_id,
                                    args.resume,"metres" if args.z_metres else None,args.building_clearance)
        print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()

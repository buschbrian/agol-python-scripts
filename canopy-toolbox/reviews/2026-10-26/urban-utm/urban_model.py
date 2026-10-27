r"""Read and set an ArcGIS Urban model's base layers through the Urban API (October 27, 2026).

    python reviews/2026-10-26/urban-utm/urban_model.py show MODEL_ID          read-only: coordinate system and config
    python reviews/2026-10-26/urban-utm/urban_model.py utm MODEL_ID [--go]    the UTM basemap and buildings, both visualizations

ArcGIS Pro Python (PYTHONNOUSERSITE=1), signed in to Pro as the model's owner (GISMillcreek). The token is ArcGIS Pro's
(arcpy.GetSigninToken); the endpoint and the mutation are the ones the Urban web app uses (updateUrbanModelConfig).
The local model 2dc81c6f3a4b47efba2849dbfff9bf0f (6341) was created on October 27 with schematic and realistic visualization
"Default" and no customBasemapItemId, so it loaded the Web Mercator defaults (Open 3D Buildings, Open 3D Trees, Light Gray
Canvas, Google mesh), which a 6341 view refuses; only the custom terrain drew. Urban's data manager shows no Default/Custom
switch for a local model, so the config is set here. Without --go nothing is written.
"""
import argparse
import json

API = "https://urban-api.arcgis.com/graphql"
CONFIG = """customElevationLayerItemId initialVisualizationStyle schematicVisualization satelliteVisualization
  customBasemapItemId customSatelliteBasemapItemId existingBuildingsLayerItemId existingSatelliteBuildingsLayerItemId
  existingTreesLayerItemId existingSatelliteTreesLayerItemId customBaselayersItemId"""
SHOW = "query($id: PortalItemId!) { urbanModel(urbanModelId: $id) { id title owner spatialReference { wkid } config { %s } } }" % CONFIG
SET = ("mutation($id: PortalItemId!, $c: UpdateUrbanModelConfigInput!) "
       "{ updateUrbanModelConfig(urbanModelId: $id, urbanModelConfig: $c) { %s } }" % CONFIG)
UTM_BASEMAP_WEBMAP = "8289e4be22534a9f99a7514c795a477b"   # in the org Basemaps gallery
UTM_BUILDINGS = "b8e8ddaceac54876bd4c0cf3f31d92fd"
UTM = {"schematicVisualization": "Custom", "satelliteVisualization": "Custom",
       "customBasemapItemId": UTM_BASEMAP_WEBMAP, "customSatelliteBasemapItemId": UTM_BASEMAP_WEBMAP,
       "existingBuildingsLayerItemId": UTM_BUILDINGS, "existingSatelliteBuildingsLayerItemId": UTM_BUILDINGS}


def gql(query, variables):
    import arcpy
    import requests
    token = arcpy.GetSigninToken()
    response = requests.post(API, json={"query": query, "variables": variables}, timeout=60,
                             headers={"Authorization": f"Bearer {token['token']}",
                                      "Referer": token.get("referer") or "https://www.arcgis.com"})
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise SystemExit(json.dumps(body["errors"], indent=1))
    return body["data"]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("show", "utm"))
    p.add_argument("model")
    p.add_argument("--go", action="store_true", help="utm: write the config")
    a = p.parse_args(argv)
    before = gql(SHOW, {"id": a.model})["urbanModel"]
    print(json.dumps(before, indent=1))
    if a.step == "utm":
        assert before["spatialReference"]["wkid"] == 6341, before["spatialReference"]
        if not a.go:
            print("Dry run; would set:", json.dumps(UTM, indent=1))
            return
        print(json.dumps(gql(SET, {"id": a.model, "c": UTM})["updateUrbanModelConfig"], indent=1))


if __name__ == "__main__":
    main()

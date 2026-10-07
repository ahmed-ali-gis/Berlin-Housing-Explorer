"""Build a compact, dated transit snapshot from an official VBB GTFS ZIP.
Usage: python scripts/build_transit.py /path/GTFS.zip 2026-09-30
Uses only the Python standard library. Runtime needs no GTFS download.
Quelle: GTFS reference (https://gtfs.org/documentation/schedule/reference/)
Quelle: Extended route types (https://developers.google.com/transit/gtfs/reference/extended-route-types)
Quelle: VBB datasets (https://unternehmen.vbb.de/digitale-services/datensaetze/)
"""
import csv, io, json, zipfile, sys, hashlib
from pathlib import Path
from datetime import date
from collections import defaultdict

SOURCE='https://www.vbb.de/fileadmin/user_upload/VBB/Dokumente/API-Datensaetze/gtfs-mastscharf/GTFS.zip'
BBOX=(13.0,52.3,13.85,52.7)
def mode(route):
    t=int(route['route_type']); name=route['route_short_name']
    if t==109: return 'S-Bahn'
    if t in (1,400,401,402): return 'U-Bahn'
    if t==0 or 900<=t<1000: return 'Tram'
    if t==3 or 700<=t<800: return 'Bus'
    if t in (4,1000,1200): return 'Ferry'
    if t==2 or 100<=t<200: return 'Regional rail'
    raise ValueError(f'Unmapped route type {t} ({name})')

def build(path,day,output_dir=None):
    z=zipfile.ZipFile(path)
    def rows(name):
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))
    compact=day.strftime('%Y%m%d'); weekday=day.strftime('%A').lower()
    active={r['service_id'] for r in rows('calendar.txt') if r['start_date']<=compact<=r['end_date'] and r[weekday]=='1'}
    for r in rows('calendar_dates.txt'):
        if r['date']==compact:
            if r['exception_type']=='1': active.add(r['service_id'])
            else: active.discard(r['service_id'])
    if not active: raise ValueError('No active services on selected snapshot date')
    routes={r['route_id']:r for r in rows('routes.txt')}
    stops={}
    for r in rows('stops.txt'):
        if r['location_type'] not in ('','0') or not r['stop_lon'] or not r['stop_lat']: continue
        x,y=float(r['stop_lon']),float(r['stop_lat'])
        if BBOX[0]<=x<=BBOX[2] and BBOX[1]<=y<=BBOX[3]: stops[r['stop_id']]=r
    trips={r['trip_id']:(r['route_id'],r['shape_id']) for r in rows('trips.txt') if r['service_id'] in active}
    stop_routes=defaultdict(set); used_shapes=defaultdict(set)
    for r in rows('stop_times.txt'):
        if r['stop_id'] not in stops or r['trip_id'] not in trips: continue
        if r.get('pickup_type')=='1' and r.get('drop_off_type')=='1': continue
        rid,sid=trips[r['trip_id']];stop_routes[r['stop_id']].add(rid)
        if sid: used_shapes[sid].add(rid)
    print('served boarding points',len(stop_routes),'shapes',len(used_shapes),flush=True)
    features=[]
    for sid,rids in sorted(stop_routes.items()):
        s=stops[sid];lines=defaultdict(set)
        for rid in rids: lines[mode(routes[rid])].add(routes[rid]['route_short_name'] or rid)
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[float(s['stop_lon']),float(s['stop_lat'])]},'properties':{'id':sid,'name':s['stop_name'],'modes':sorted(lines),'lines':{m:sorted(v) for m,v in lines.items()}}})
    shape_points=defaultdict(list)
    for r in rows('shapes.txt'):
        if r['shape_id'] in used_shapes:
            shape_points[r['shape_id']].append((int(r['shape_pt_sequence']),float(r['shape_pt_lon']),float(r['shape_pt_lat'])))
    network=[]
    for sid,points in sorted(shape_points.items()):
        segments=[];segment=[]
        # Break outside the bounding box instead of drawing invented connectors.
        for _,x,y in sorted(points):
            if BBOX[0]<=x<=BBOX[2] and BBOX[1]<=y<=BBOX[3]:
                if not segment or segment[-1]!=[x,y]: segment.append([x,y])
            else:
                if len(segment)>1:segments.append(segment)
                segment=[]
        if len(segment)>1:segments.append(segment)
        if not segments:continue
        for rid in sorted(used_shapes[sid]):
            r=routes[rid]
            network.append({'type':'Feature','geometry':{'type':'MultiLineString','coordinates':segments},'properties':{'id':rid+':'+sid,'name':r['route_short_name'] or rid,'mode':mode(r)}})
    metadata={'provider':'Verkehrsverbund Berlin-Brandenburg (VBB)','source_url':SOURCE,'license':'CC BY 4.0','license_url':'https://creativecommons.org/licenses/by/4.0/','retrieved_on':date.today().isoformat(),'service_date':day.isoformat(),'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'scope':'Scheduled services on service_date; boarding points and supplied GTFS shapes within Berlin-area bounding box. PostGIS limits coverage to district polygons. Not live, not journey planning.','boarding_point_count':len(features),'shape_variant_count':len(network)}
    out=Path(output_dir) if output_dir else Path(__file__).resolve().parents[1]/'data'
    for name,items in [('transit_stops',features),('transit_routes',network)]:
        (out/(name+'.geojson')).write_text(json.dumps({'type':'FeatureCollection','features':items},ensure_ascii=False,separators=(',',':')))
    (out/'transit_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(metadata,flush=True)
if __name__=='__main__':build(sys.argv[1],date.fromisoformat(sys.argv[2]))

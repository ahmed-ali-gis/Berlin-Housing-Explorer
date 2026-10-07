"""Synthetic GTFS test: calendar exceptions, mode codes, stop eligibility and geometry gaps."""
import csv,io,json,tempfile,zipfile,importlib.util
from pathlib import Path
from datetime import date
spec=importlib.util.spec_from_file_location('builder',Path(__file__).resolve().parents[1]/'scripts/build_transit.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp);archive=tmp/'feed.zip'
    with zipfile.ZipFile(archive,'w') as z:
        def table(name,header,rows):
            stream=io.StringIO();writer=csv.writer(stream);writer.writerow(header.split(','));writer.writerows(rows);z.writestr(name,stream.getvalue())
        table('calendar.txt','service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date',[
            ['normal',1,1,1,1,1,1,1,'20260101','20261231'],['cancelled',1,1,1,1,1,1,1,'20260101','20261231']])
        table('calendar_dates.txt','service_id,date,exception_type',[['cancelled','20260930',2],['extra','20260930',1]])
        table('routes.txt','route_id,route_short_name,route_type',[['u','U1',400],['b','100',700],['s','S1',109]])
        table('trips.txt','trip_id,route_id,service_id,shape_id',[['t1','u','normal','shape'],['t2','b','cancelled','shape'],['t3','s','extra','shape']])
        table('stops.txt','stop_id,stop_name,stop_lon,stop_lat,location_type',[
            ['inside','Inside',13.4,52.5,0],['outside','Outside',14.5,52.5,0],['station','Parent station',13.4,52.5,1],['pass','Pass-through',13.5,52.5,0]])
        table('stop_times.txt','trip_id,stop_id,pickup_type,drop_off_type',[
            ['t1','inside',0,0],['t2','inside',0,0],['t3','inside',0,0],['t1','outside',0,0],['t1','station',0,0],['t1','pass',1,1]])
        table('shapes.txt','shape_id,shape_pt_sequence,shape_pt_lon,shape_pt_lat',[
            ['shape',0,13.4,52.5],['shape',1,13.41,52.5],['shape',2,14.5,52.5],['shape',3,13.5,52.5],['shape',4,13.51,52.5]])
    builder.build(archive,date(2026,9,30),tmp)
    stops=json.loads((tmp/'transit_stops.geojson').read_text())['features']
    assert len(stops)==1 and stops[0]['properties']['modes']==['S-Bahn','U-Bahn']
    assert stops[0]['properties']['lines']=={'U-Bahn':['U1'],'S-Bahn':['S1']}
    routes=json.loads((tmp/'transit_routes.geojson').read_text())['features']
    assert len(routes)==2 and all(len(f['geometry']['coordinates'])==2 for f in routes)
    print('PASS: active-date selection, exceptions, VBB modes, boarding eligibility, bbox exclusion and no invented shape connectors.')

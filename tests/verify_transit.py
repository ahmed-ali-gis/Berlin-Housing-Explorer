"""API consistency checks for the bundled VBB snapshot. Run after verify_portfolio_api.py."""
import json,urllib.request,os
BASE=os.environ.get('GIS_TEST_URL','http://127.0.0.1:8000')
def get(path):
    with urllib.request.urlopen(BASE+path,timeout=90) as r:return json.load(r)
network=get('/api/transit'); areas=get('/api/districts')['features']
assert network['metadata']['service_date']=='2026-09-30'
assert network['metadata']['license']=='CC BY 4.0'
stops=network['stops']['features'];routes=network['routes']['features']
assert len(stops)>1000 and len(routes)>100
assert {'Bus','Tram','S-Bahn','U-Bahn'} <= {r['properties']['mode'] for r in routes}
for f in areas:
    s=f['properties']['transit']
    assert s['boarding_points']>=0
    assert s['modes']==sorted(s['by_mode'])
    for mode,info in s['by_mode'].items():
        assert 0<info['boarding_points']<=s['boarding_points']
        assert info['lines']==sorted(set(info['lines'])) and info['lines']
mitte=next(f for f in areas if f['properties']['name']=='Mitte')['properties']['transit']
assert {'U-Bahn','S-Bahn','Bus'}<=set(mitte['modes'])
assert len({s['properties']['id'] for s in stops})==len(stops)
print(f'PASS: {len(stops)} Berlin boarding points, {len(routes)} named mode/line geometries, {len(areas)} district summaries; Mitte has U-Bahn, S-Bahn and Bus.')

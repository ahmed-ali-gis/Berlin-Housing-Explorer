"""Local VBB snapshot and PostGIS stop-in-region analysis.
Quelle: VBB (https://unternehmen.vbb.de/digitale-services/datensaetze/)
Quelle: ST_Covers (https://postgis.net/docs/ST_Covers.html)
"""
import json
from collections import defaultdict
from psycopg.types.json import Jsonb


def initialize_transit(db, root):
    db.execute('''CREATE TABLE IF NOT EXISTS housing.transit_stops (
        id text PRIMARY KEY, name text NOT NULL, modes text[] NOT NULL,
        lines jsonb NOT NULL, geom geometry(Point,4326) NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS transit_stops_geom_idx ON housing.transit_stops USING gist(geom)')
    db.execute('''CREATE TABLE IF NOT EXISTS housing.transit_routes (
        id text PRIMARY KEY, name text NOT NULL, mode text NOT NULL,
        geom geometry(MultiLineString,4326) NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS housing.transit_coverage (
        code text PRIMARY KEY REFERENCES housing.districts(code), summary jsonb NOT NULL)''')
    # Replace only bundled reference transit data, within the main startup transaction.
    db.execute('TRUNCATE housing.transit_coverage, housing.transit_stops, housing.transit_routes')
    stops=json.loads((root/'data/transit_stops.geojson').read_text())['features']
    routes=json.loads((root/'data/transit_routes.geojson').read_text())['features']
    with db.cursor() as cur:
        cur.executemany('''INSERT INTO housing.transit_stops VALUES
            (%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))''',
            [(f['properties']['id'],f['properties']['name'],f['properties']['modes'],
              Jsonb(f['properties']['lines']),json.dumps(f['geometry'])) for f in stops])
        cur.executemany('''INSERT INTO housing.transit_routes VALUES
            (%s,%s,%s,ST_Multi(ST_SimplifyPreserveTopology(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),0.00005)))''',
            [(f['properties']['id'],f['properties']['name'],f['properties']['mode'],json.dumps(f['geometry'])) for f in routes])
    db.execute('''DELETE FROM housing.transit_stops s WHERE NOT EXISTS
        (SELECT 1 FROM housing.districts d WHERE ST_Covers(d.geom,s.geom))''')
    summaries={r['code']:{'boarding_points':0,'modes':[],'by_mode':{}} for r in db.execute('SELECT code FROM housing.districts')}
    for r in db.execute('''SELECT d.code,s.id,s.modes,s.lines FROM housing.districts d
            JOIN housing.transit_stops s ON ST_Covers(d.geom,s.geom) ORDER BY d.code,s.id'''):
        summary=summaries[r['code']];summary['boarding_points']+=1
        for mode in r['modes']:
            bucket=summary['by_mode'].setdefault(mode,{'boarding_points':0,'lines':set()})
            bucket['boarding_points']+=1;bucket['lines'].update(r['lines'][mode])
    for summary in summaries.values():
        summary['modes']=sorted(summary['by_mode'])
        for v in summary['by_mode'].values():v['lines']=sorted(v['lines'])
    with db.cursor() as cur:
        cur.executemany('INSERT INTO housing.transit_coverage VALUES (%s,%s)',[(code,Jsonb(s)) for code,s in summaries.items()])


def feature_collection(rows):
    return {'type':'FeatureCollection','features':[
        {'type':'Feature','geometry':r.pop('geometry'),'properties':r} for r in rows]}

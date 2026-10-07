"""Berlin housing explorer: persisted workplace profiles and spatial comparisons.
Quelle: Custom Response - FastAPI (https://fastapi.tiangolo.com/advanced/custom-response/)
"""
import csv
import hashlib
import json
import math
import os
import secrets
from functools import lru_cache
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import psycopg
from app.transit import initialize_transit, feature_collection
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict

ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.environ['DATABASE_URL']


def connect():
    return psycopg.connect(DB_URL, row_factory=dict_row)


def initialize():
    # Initialization is transactional and repeatable; existing profiles are retained.
    with connect() as db:
        db.execute('CREATE EXTENSION IF NOT EXISTS postgis')
        db.execute('CREATE SCHEMA IF NOT EXISTS housing')
        db.execute('''CREATE TABLE IF NOT EXISTS housing.districts (
            code text PRIMARY KEY, name text NOT NULL UNIQUE, borough text NOT NULL,
            geom geometry(MultiPolygon,4326) NOT NULL,
            avg_rent double precision, avg_buy double precision, price_rows integer NOT NULL DEFAULT 0)''')
        db.execute('CREATE INDEX IF NOT EXISTS district_geom_idx ON housing.districts USING gist(geom)')
        db.execute('''CREATE TABLE IF NOT EXISTS housing.profiles (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            token_hash text NOT NULL UNIQUE, name text NOT NULL,
            budget double precision NOT NULL CHECK(budget>0),
            mode text NOT NULL CHECK(mode IN ('rent','buy')),
            workplace geometry(Point,4326) NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now())''')
        db.execute('ALTER TABLE housing.profiles ADD COLUMN IF NOT EXISTS max_distance_km double precision NOT NULL DEFAULT 15 CHECK(max_distance_km>0 AND max_distance_km<=100)')
        db.execute('CREATE INDEX IF NOT EXISTS workplace_idx ON housing.profiles USING gist(workplace)')
        features = json.loads((ROOT/'data/districts.geojson').read_text())['features']
        prices = {}
        # Prices are optional: the public copy excludes unlicensed housing data.
        price_file = ROOT/'data/prices.csv'
        price_rows = csv.DictReader(price_file.open(encoding='utf-8')) if price_file.exists() else []
        for row in price_rows:
            key = row['borough'].split(' (')[0].strip().casefold()
            values = [float(row['avgRent']), float(row['avgBuy'])]
            if not all(math.isfinite(v) and v > 0 for v in values):
                raise ValueError(f'Invalid prices for {key}')
            prices.setdefault(key, []).append(values)
        names = {f['properties']['Ortsteilna'].strip().casefold() for f in features}
        if prices.keys() - names:
            raise ValueError('Unmatched price region names')
        for feature in features:
            p = feature['properties']; rows = prices.get(p['Ortsteilna'].strip().casefold(), [])
            rent = sum(x[0] for x in rows)/len(rows) if rows else None
            buy = sum(x[1] for x in rows)/len(rows) if rows else None
            db.execute('''INSERT INTO housing.districts(code,name,borough,geom,avg_rent,avg_buy,price_rows)
                VALUES (%s,%s,%s,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),%s,%s,%s)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name,borough=EXCLUDED.borough,
                geom=EXCLUDED.geom,avg_rent=EXCLUDED.avg_rent,avg_buy=EXCLUDED.avg_buy,price_rows=EXCLUDED.price_rows''',
                (p['ORT'],p['Ortsteilna'],p['Bezname'],json.dumps(feature['geometry']),rent,buy,len(rows)))
        invalid = db.execute('SELECT count(*) AS n FROM housing.districts WHERE NOT ST_IsValid(geom)').fetchone()['n']
        if invalid:
            raise ValueError(f'{invalid} invalid district geometries')
        initialize_transit(db, ROOT)


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title='Berlin Housing Explorer',version='2.1.0',lifespan=lifespan)


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    name: str = Field(min_length=2,max_length=100)
    budget: float = Field(gt=0,le=1000000)
    mode: Literal['rent','buy'] = 'rent'
    max_distance_km: float = Field(default=15,gt=0,le=100)
    lon: float = Field(ge=13.0,le=13.85)
    lat: float = Field(ge=52.3,le=52.7)


def profile_hash(auth):
    if not auth or not auth.startswith('Bearer ') or len(auth[7:]) < 20:
        raise HTTPException(401,'A valid profile key is required')
    return hashlib.sha256(auth[7:].encode()).hexdigest()


def owned(db, auth):
    p = db.execute('''SELECT id,name,budget,mode,max_distance_km,ST_X(workplace) AS lon,
        ST_Y(workplace) AS lat,updated_at FROM housing.profiles WHERE token_hash=%s''',
        (profile_hash(auth),)).fetchone()
    if not p:
        raise HTTPException(401,'Profile key not found')
    return p


@app.get('/',include_in_schema=False)
def home():
    return FileResponse(ROOT/'app/index.html', headers={'Cache-Control':'no-store'})


@app.get('/health')
def health():
    with connect() as db:
        count = db.execute('SELECT count(*) AS n FROM housing.districts').fetchone()['n']
    return {'status':'ok','districts':count}


@app.get('/api/districts')
def districts():
    with connect() as db:
        rows = db.execute('''SELECT d.code,name,borough,avg_rent,avg_buy,price_rows,c.summary AS transit,
            ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.00003))::json AS geometry,
            ST_AsGeoJSON(ST_PointOnSurface(geom))::json AS representative_point
            FROM housing.districts d JOIN housing.transit_coverage c ON c.code=d.code ORDER BY name''').fetchall()
    return {'type':'FeatureCollection','features':[
        {'type':'Feature','geometry':r.pop('geometry'),'properties':r} for r in rows]}


@app.post('/api/profiles',status_code=201)
def create_profile(p: Profile):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('''INSERT INTO housing.profiles(token_hash,name,budget,mode,max_distance_km,workplace)
            VALUES (%s,%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326))''',
            (hashlib.sha256(token.encode()).hexdigest(),p.name,p.budget,p.mode,p.max_distance_km,p.lon,p.lat))
        result = owned(db,'Bearer '+token)
    return {'key':token,'profile':result}


@app.get('/api/profiles/me')
def read_profile(authorization: str | None = Header(default=None)):
    with connect() as db:
        return owned(db,authorization)


@app.put('/api/profiles/me')
def update_profile(p: Profile, authorization: str | None = Header(default=None)):
    with connect() as db:
        previous = owned(db,authorization)
        db.execute('''UPDATE housing.profiles SET name=%s,budget=%s,mode=%s,max_distance_km=%s,
            workplace=ST_SetSRID(ST_MakePoint(%s,%s),4326),updated_at=now() WHERE id=%s''',
            (p.name,p.budget,p.mode,p.max_distance_km,p.lon,p.lat,previous['id']))
        return owned(db,authorization)


@app.delete('/api/profiles/me',status_code=204)
def delete_profile(authorization: str | None = Header(default=None)):
    with connect() as db:
        p = owned(db,authorization)
        db.execute('DELETE FROM housing.profiles WHERE id=%s',(p['id'],))


@app.get('/api/recommendations')
# Quelle: PostGIS ST_Distance (https://postgis.net/docs/ST_Distance.html)
# Quelle: PostGIS ST_PointOnSurface (https://postgis.net/docs/ST_PointOnSurface.html)
def recommendations(authorization: str | None = Header(default=None),
                    max_distance_km: float | None = Query(default=None,gt=0,le=100)):
    with connect() as db:
        p = owned(db,authorization)
        if max_distance_km is None:
            max_distance_km = p['max_distance_km']
        rows = db.execute('''WITH comparison AS (
            SELECT d.code,name,c.summary AS transit,CASE WHEN %s='rent' THEN avg_rent ELSE avg_buy END AS price,
            ST_Distance(ST_PointOnSurface(geom)::geography,
              ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)/1000.0 AS distance_km
            FROM housing.districts d JOIN housing.transit_coverage c ON c.code=d.code)
            SELECT *,0.6*(price/%s)+0.4*(distance_km/%s) AS score FROM comparison
            WHERE price IS NOT NULL AND price<=%s AND distance_km<=%s
            ORDER BY score,name''',
            (p['mode'],p['lon'],p['lat'],p['budget'],max_distance_km,p['budget'],max_distance_km)).fetchall()
    return {'profile':p,'mode':p['mode'],'max_distance_km':max_distance_km,
            'results':rows,'count':len(rows),'score_note':'Lower is better; 60% price ratio + 40% distance ratio'}


@app.get('/api/transit')
@lru_cache(maxsize=1)
def transit():
    with connect() as db:
        stops = db.execute("SELECT id,name,modes,lines,ST_AsGeoJSON(geom)::json AS geometry FROM housing.transit_stops ORDER BY id").fetchall()
        routes = db.execute("SELECT name,mode,ST_AsGeoJSON(ST_Multi(ST_UnaryUnion(ST_Collect(geom))))::json AS geometry FROM housing.transit_routes GROUP BY name,mode ORDER BY mode,name").fetchall()
    return {'metadata':json.loads((ROOT/'data/transit_metadata.json').read_text()),
            'stops':feature_collection(stops),'routes':feature_collection(routes)}

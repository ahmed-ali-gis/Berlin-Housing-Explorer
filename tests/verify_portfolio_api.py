"""Integration checks against a running application; creates and deletes its own profiles."""
import json
import math
import os
import urllib.error
import urllib.request

BASE = os.environ.get('GIS_TEST_URL', 'http://127.0.0.1:8000')

def request(path, method='GET', data=None, key=None, expected=200):
    headers={'Content-Type':'application/json'}
    if key: headers['Authorization']='Bearer '+key
    req=urllib.request.Request(BASE+path, data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=30) as res: status=res.status; raw=res.read()
    except urllib.error.HTTPError as e: status=e.code;raw=e.read()
    assert status==expected,(method,path,status,raw)
    return json.loads(raw) if raw else None


def run():
    keys=[]
    try:
        assert request('/health')['districts']==96
        features=request('/api/districts')['features']
        assert len(features)==96
        assert sum(f['properties']['price_rows'] for f in features)==80
        by_code={f['properties']['code']:f['properties'] for f in features}
        request('/api/profiles/me',expected=401)
        profile={'name':'Integration Test','budget':18,'mode':'rent','lon':13.405,'lat':52.52}
        request('/api/profiles','POST',{**profile,'budget':0},expected=422)
        request('/api/profiles','POST',{**profile,'lon':0},expected=422)
        made=request('/api/profiles','POST',profile,expected=201);key=made['key'];keys.append(key)
        assert request('/api/profiles/me',key=key)['id']==made['profile']['id']
        assert request('/api/profiles/me',key=key)['lon']==profile['lon']
        result=request('/api/recommendations?max_distance_km=15',key=key)
        assert result['count']>0
        assert all(x['transit']==by_code[x['code']]['transit'] for x in result['results'])
        assert all(x['price']<=18 and x['distance_km']<=15 for x in result['results'])
        assert all(abs(x['price']-by_code[x['code']]['avg_rent'])<1e-8 for x in result['results'])
        assert [x['score'] for x in result['results']]==sorted(x['score'] for x in result['results'])
        assert all(abs(x['score']-(.6*x['price']/18+.4*x['distance_km']/15))<1e-8 for x in result['results'])
        request('/api/recommendations?max_distance_km=0',key=key,expected=422)
        changed={**profile,'name':'Updated Test','mode':'buy','budget':5000,'lon':13.31,'lat':52.50,'max_distance_km':10}
        updated=request('/api/profiles/me','PUT',changed,key)
        assert updated['id']==made['profile']['id'] and updated['lon']==13.31 and updated['name']=='Updated Test'
        bought=request('/api/recommendations?max_distance_km=15',key=key)
        assert request('/api/profiles/me',key=key)['max_distance_km']==10
        assert request('/api/recommendations',key=key)['max_distance_km']==10
        assert bought['count']>0 and bought['mode']=='buy'
        assert all(abs(x['price']-by_code[x['code']]['avg_buy'])<1e-8 for x in bought['results'])
        assert all(x['price']<=5000 for x in bought['results'])
        second=request('/api/profiles','POST',{**profile,'name':'Separate Test'},expected=201);keys.append(second['key'])
        assert request('/api/profiles/me',key=second['key'])['name']=='Separate Test'
        request('/api/profiles/me','PUT',profile,'x'*43,expected=401)
        request('/api/profiles/me','PUT',{**profile,'budget':.01},key)
        assert request('/api/recommendations',key=key)['count']==0
        request('/api/profiles/me','DELETE',key=key,expected=204);keys.remove(key)
        request('/api/profiles/me',key=key,expected=401)
        print('PASS: data coverage, authorization, validation, create/read/update/delete, rent/buy pricing, distance filters, score formula, empty results, profile isolation.')
    finally:
        for key in keys:request('/api/profiles/me','DELETE',key=key,expected=204)

if __name__=='__main__':run()

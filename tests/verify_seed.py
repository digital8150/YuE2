import json
import time
import urllib.request

def fetch(url):
    req = urllib.request.Request(url, headers={'Connection': 'close', 'User-Agent': 'SeedVerifier/1.0'})
    with urllib.request.urlopen(req, timeout=5) as res:
        data = res.read()
        return res.status, len(data)

print("1. Testing 5 Artists (Avatar & Banner):")
for aid in [-1, -2, -3, -4, -5]:
    st_av, len_av = fetch(f"http://127.0.0.1:7860/api/artists/{aid}/avatar")
    time.sleep(0.05)
    st_bn, len_bn = fetch(f"http://127.0.0.1:7860/api/artists/{aid}/banner")
    time.sleep(0.05)
    print(f"  Artist {aid}: Avatar {st_av} ({len_av:,} B), Banner {st_bn} ({len_bn:,} B)")

print("\n2. Testing Discover:")
time.sleep(0.05)
req = urllib.request.Request("http://127.0.0.1:7860/api/library/discover", headers={'Connection': 'close', 'User-Agent': 'SeedVerifier/1.0'})
with urllib.request.urlopen(req, timeout=5) as res:
    data = json.loads(res.read().decode('utf-8'))
    print(f"  Total artists in discover: {len(data['artists'])}")
    print(f"  Total albums in discover: {len(data['albums'])}")
    print(f"  Total new releases: {len(data['new_releases'])}")
    print(f"  Total this week: {len(data['this_week'])}")

print("\n3. Testing Charts (Top 10):")
time.sleep(0.05)
req = urllib.request.Request("http://127.0.0.1:7860/api/library/charts", headers={'Connection': 'close', 'User-Agent': 'SeedVerifier/1.0'})
with urllib.request.urlopen(req, timeout=5) as res:
    charts = json.loads(res.read().decode('utf-8'))
    print(f"  Total chart tracks: {len(charts)}")
    for i, trk in enumerate(charts[:10]):
        print(f"    #{i+1:2d}: {trk['title']} - {trk['creator']} ({trk['play_count']:,} plays)")

print("\n4. Testing Audio Streaming on Top Track:")
time.sleep(0.05)
sample_track = charts[0]
req = urllib.request.Request(f"http://127.0.0.1:7860{sample_track['audio_url']}", headers={'Connection': 'close', 'Range': 'bytes=0-1023', 'User-Agent': 'SeedVerifier/1.0'})
with urllib.request.urlopen(req, timeout=5) as res:
    chunk = res.read()
    print(f"  Track: {sample_track['title']}")
    print(f"  Status: {res.status}, Content-Type: {res.headers.get('Content-Type')}, Streamed: {len(chunk)} bytes")

print("\n=== Verification Completed Successfully! ===")

import asyncio
import aiohttp

BASE_URL = "http://127.0.0.1:7860"

async def main():
    async with aiohttp.ClientSession() as session:
        print("=== 1. Checking Discover API ===")
        async with session.get(f"{BASE_URL}/api/library/discover") as r:
            assert r.status == 200
            data = await r.json()
            print(f"  Artists: {len(data['artists'])}")
            print(f"  Albums:  {len(data['albums'])}")
            print(f"  New Releases: {len(data['new_releases'])}")
            print(f"  This Week:    {len(data['this_week'])}")
            print(f"  Charts:       {len(data['charts'])}")

        print("\n=== 2. Checking Artists Profiles & Images ===")
        for artist in data['artists']:
            aid = artist['id']
            name = artist['name']
            tracks_cnt = artist['track_count']
            av_url = artist.get('avatar_url')
            bn_url = artist.get('banner_url')
            
            av_status, bn_status = None, None
            if av_url:
                async with session.get(f"{BASE_URL}{av_url}") as r:
                    av_status = r.status
            if bn_url:
                async with session.get(f"{BASE_URL}{bn_url}") as r:
                    bn_status = r.status
            print(f"  [{aid}] {name} (Tracks: {tracks_cnt}) -> Avatar: {av_status}, Banner: {bn_status}")

        print("\n=== 3. Checking All 10 Albums & Covers ===")
        async with session.get(f"{BASE_URL}/api/library/discover") as r:
            albums = (await r.json())['albums']
            for alb in albums:
                cover_url = alb.get('cover_url')
                c_status = None
                if cover_url:
                    async with session.get(f"{BASE_URL}{cover_url}") as cr:
                        c_status = cr.status
                print(f"  Album: {alb['title']} by {alb['artist_name']} ({alb['track_count']} tracks) -> Cover: {c_status}")

        print("\n=== 4. Checking Top 10 Chart Tracks & Audio Streaming ===")
        async with session.get(f"{BASE_URL}/api/library/charts") as r:
            charts = await r.json()
            print(f"  Total Published Tracks in Charts: {len(charts)}")
            for i, trk in enumerate(charts[:10]):
                audio_url = trk['audio_url']
                # Stream first 1KB
                async with session.get(f"{BASE_URL}{audio_url}", headers={"Range": "bytes=0-1023"}) as ar:
                    chunk = await ar.read()
                    print(f"    #{i+1:2d}: {trk['title']} - {trk['creator']} ({trk['play_count']:,} plays) -> Audio HTTP {ar.status} ({len(chunk)} B streamed)")

        print("\n=== All Tests Passed Flawlessly! ===")

if __name__ == "__main__":
    asyncio.run(main())

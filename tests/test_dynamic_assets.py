#!/usr/bin/env python3
"""
Test Dynamic Assets Fetching
Usage: python test_dynamic_assets.py
"""

import asyncio
import os
import sys
import logging
import json

# Prefer backend package over root-level app/
sys.path.insert(0, "backend/src")

from app.infrastructure.external.nofxos_dynamic_assets import NofXOSDynamicAssetsClient

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Enter your NofXOS API Key here to test without env vars
API_KEY = "cm_568c67eae410d912c54c"

async def main():
    print("=" * 60)
    print("TESTING DYNAMIC ASSETS FETCH")
    print("=" * 60)

    # You can set NOFXOS_API_URL env var if needed, otherwise uses default
    client = NofXOSDynamicAssetsClient()
    
    # Define sources to test
    # You can modify these to test different configurations
    sources = {
        "ai500": {"enabled": True, "limit": 2},
        "ai300": {"enabled": True, "limit": 2, "level": "HIGH_CONFIDENCE"}, # Example level
        "oi_top": {"enabled": True, "limit": 5, "duration": "4h"},
        "oi_low": {"enabled": True, "limit": 5, "duration": "4h"},
    }

    # Use hardcoded key if present, otherwise env var
    api_key = API_KEY or os.environ.get("NOFXOS_API_KEY")
    if not api_key:
        print("\n[WARNING] API Key is missing!")
        print("Please fill in the API_KEY variable in the script or set NOFXOS_API_KEY env var.")
        print("Some endpoints might require authentication.\n")
    else:
        print(f"Using API Key: {api_key[:4]}...{api_key[-4:]}")

    print("\nRequesting assets from sources:")
    for source, config in sources.items():
        print(f"  - {source}: {config}")

    print("\nFetching...")
    all_assets = []
    
    import httpx
    
    # We will manually fetch each source to see what they return individually
    # This accesses internal methods of the client for debugging/testing purposes
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            
            # --- AI500 ---
            if sources["ai500"]["enabled"]:
                print("\n[AI500]")
                assets = await client._fetch_ai500(
                    http_client, 
                    api_key, 
                    limit=int(sources["ai500"].get("limit", 10))
                )
                print(f"  Count: {len(assets)}")
                print(f"  Assets: {assets}")
                all_assets.extend(assets)

            # --- AI300 ---
            if sources["ai300"]["enabled"]:
                print("\n[AI300]")
                assets = await client._fetch_ai300(
                    http_client, 
                    api_key, 
                    limit=int(sources["ai300"].get("limit", 20)),
                    level=sources["ai300"].get("level")
                )
                print(f"  Count: {len(assets)}")
                print(f"  Assets: {assets}")
                all_assets.extend(assets)

            # --- OI TOP (RAW FETCH) ---
            if sources["oi_top"]["enabled"]:
                print("\n[OI TOP - RAW FETCH]")
                
                # Manual request to see raw order
                raw_url = f"{client._base_url}/oi/top-ranking"
                raw_params = {"limit": int(sources["oi_top"].get("limit", 20)), "duration": sources["oi_top"].get("duration", "1h")}
                if api_key:
                    raw_params["auth"] = api_key
                
                print(f"  Fetching: {raw_url} (params={raw_params})")
                raw_resp = await http_client.get(raw_url, params=raw_params)
                
                raw_assets = []
                if raw_resp.status_code == 200:
                    raw_data = raw_resp.json()
                    print(f"  Raw JSON Response:\n{json.dumps(raw_data, indent=2)}")
                    positions = raw_data.get("data", {}).get("positions", [])
                    raw_assets = [p.get("symbol") for p in positions]
                else:
                    print(f"  Failed raw fetch: {raw_resp.status_code}")

                # Client fetch (uses sorted(set()))
                print("\n[OI TOP - CLIENT FETCH]")
                assets = await client._fetch_oi_ranking(
                    http_client, 
                    api_key, 
                    ranking_type="top",
                    limit=int(sources["oi_top"].get("limit", 20)),
                    duration=sources["oi_top"].get("duration", "1h")
                )
                print(f"  Count: {len(assets)}")
                print(f"  Client Output: {assets}")
                all_assets.extend(assets)
                
                print(f"\n  MATCH: {raw_assets == assets}")
                if raw_assets != assets:
                    print("  [WARNING] Client output does not match raw order!")

            # --- OI LOW ---
            if sources["oi_low"]["enabled"]:
                print("\n[OI LOW]")
                assets = await client._fetch_oi_ranking(
                    http_client, 
                    api_key, 
                    ranking_type="low",
                    limit=int(sources["oi_low"].get("limit", 20)),
                    duration=sources["oi_low"].get("duration", "1h")
                )
                print(f"  Count: {len(assets)}")
                print(f"  Assets: {assets}")
                all_assets.extend(assets)
        
        # Unique list
        unique_assets = sorted(set(all_assets))

        print("\n" + "-" * 40)
        print(f"Total Unique Assets: {len(unique_assets)}")
        print("-" * 40)
        
        for i, asset in enumerate(unique_assets, 1):
            # Since we just want the list, let's just print the final unique list
            print(f"{i:3}. {asset}")
            
        print("-" * 40)
        print("Done.")

    except Exception as e:
        print(f"\n[ERROR] Failed to fetch assets: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

import os
import requests
from datetime import datetime, timezone


def fetch_top20(logical_date: datetime) -> list[dict]:
    api_key = os.environ["COINGECKO_API_KEY"]
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 20,
        "page": 1,
        "sparkline": False
    }


    headers = {"x-cg-demo-api-key": api_key}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        raise requests.HTTPError(f"Expected status code 200, but got {response.status_code}")

    top_20 = [
        {
            "coin_id": coin["id"],
            "symbol": coin["symbol"],
            "name": coin["name"],
            "price_usd": coin["current_price"],
            "market_cap_usd": coin["market_cap"],
            "volume_24h_usd": coin["total_volume"],
            "price_change_pct_24h": coin["price_change_percentage_24h"],
            "snapshot_timestamp": logical_date.replace(tzinfo=timezone.utc),
            "source_version": "v3"
        }
        for coin in response.json()
    ]

    return top_20
import asyncio
import requests  # sync HTTP client


async def fetch_all_profiles(user_ids):
    profiles = []
    for user_id in user_ids:
        # Inefficient: a synchronous, blocking HTTP call inside an async
        # request-handling path — this blocks the entire event loop for
        # the duration of each request instead of awaiting a non-blocking
        # client (e.g. httpx.AsyncClient) or running requests concurrently.
        response = requests.get(f"https://api.internal/users/{user_id}")
        profiles.append(response.json())
    return profiles

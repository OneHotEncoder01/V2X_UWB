from pathlib import Path
import urllib.error
import urllib.request

from django.conf import settings
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import render

from .models import CamMessage


TILE_CACHE_DIR = settings.BASE_DIR / "static" / "tile_cache"
TILE_URL = "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
FALLBACK_TILE = b"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" fill="#edf3f5"/>
<path d="M0 64H256M0 128H256M0 192H256M64 0V256M128 0V256M192 0V256" stroke="#cbd6dd" stroke-width="1"/>
<text x="128" y="128" text-anchor="middle" dominant-baseline="middle" fill="#64748b" font-family="sans-serif" font-size="14">tile unavailable</text>
</svg>"""


def _message_dict(message):
    return {
        "id": message.id,
        "received_at": message.received_at.isoformat(),
        "generation_delta_time": message.generation_delta_time,
        "station_type": message.station_type,
        "latitude": message.latitude,
        "longitude": message.longitude,
        "altitude_m": message.altitude_m,
        "speed_mps": message.speed_mps,
        "speed_kmh": message.speed_mps * 3.6 if message.speed_mps is not None else None,
        "heading_deg": message.heading_deg,
        "drive_direction": message.drive_direction,
        "raw_hex": message.raw_hex,
    }


def dashboard(request):
    return render(request, "messages/dashboard.html")


def messages_api(request):
    try:
        limit = min(int(request.GET.get("limit", 100)), 500)
    except ValueError:
        limit = 100

    messages = CamMessage.objects.all()[:limit]
    return JsonResponse({"messages": [_message_dict(message) for message in messages]})


def latest_api(request):
    message = CamMessage.objects.first()
    return JsonResponse({"message": _message_dict(message) if message else None})


def map_tile(request, z, x, y):
    if z < 0 or z > 20 or x < 0 or y < 0:
        return HttpResponse(FALLBACK_TILE, content_type="image/svg+xml")

    cache_path = TILE_CACHE_DIR / str(z) / str(x) / f"{y}.png"
    if cache_path.exists():
        return HttpResponse(cache_path.read_bytes(), content_type="image/png")

    tile_url = TILE_URL.format(z=z, x=x, y=y)
    request_headers = {"User-Agent": "V2X-UWB-CAM-Dashboard/1.0"}

    try:
        with urllib.request.urlopen(
            urllib.request.Request(tile_url, headers=request_headers),
            timeout=8,
        ) as response:
            tile = response.read()
    except (urllib.error.URLError, TimeoutError):
        return HttpResponse(FALLBACK_TILE, content_type="image/svg+xml")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(tile)
    return HttpResponse(tile, content_type="image/png")

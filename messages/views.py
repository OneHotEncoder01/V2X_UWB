from pathlib import Path
import urllib.error
import urllib.request

from django.conf import settings
from django.db.models import Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render

from .models import CamMessage


TILE_CACHE_DIR = settings.BASE_DIR / "static" / "tile_cache"
TILE_URL = "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
FALLBACK_TILE = b"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" fill="#edf3f5"/>
<path d="M0 64H256M0 128H256M0 192H256M64 0V256M128 0V256M192 0V256" stroke="#cbd6dd" stroke-width="1"/>
<text x="128" y="128" text-anchor="middle" dominant-baseline="middle" fill="#64748b" font-family="sans-serif" font-size="14">tile unavailable</text>
</svg>"""

STATION_LABELS = {
    0: "Unknown",
    1: "Pedestrian",
    2: "Cyclist",
    3: "Moped",
    4: "Motorcycle",
    5: "Passenger Car",
    6: "Bus",
    7: "Light Truck",
    8: "Heavy Truck",
    9: "Trailer",
    10: "Special Vehicle",
    11: "Tram",
    15: "Road-Side Unit",
}


def _station_label(station_type):
    if station_type is None:
        return "Unknown"
    return STATION_LABELS.get(station_type, f"Type {station_type}")


def _message_dict(message):
    return {
        "id": message.id,
        "received_at": message.received_at.isoformat(),
        "station_id": message.station_id,
        "station_key": str(message.station_id) if message.station_id is not None else "unknown",
        "station_type": message.station_type,
        "station_type_label": _station_label(message.station_type),
        "generation_delta_time": message.generation_delta_time,
        "latitude": message.latitude,
        "longitude": message.longitude,
        "altitude_m": message.altitude_m,
        "speed_mps": message.speed_mps,
        "speed_kmh": message.speed_mps * 3.6 if message.speed_mps is not None else None,
        "heading_deg": message.heading_deg,
        "drive_direction": message.drive_direction,
        "raw_hex": message.raw_hex,
    }


# ── HTML views ───────────────────────────────────────────────────────────────

def dashboard(request):
    return render(request, "messages/dashboard.html")


def station_detail(request, station_key):
    if station_key == "unknown":
        qs = CamMessage.objects.filter(station_id__isnull=True)
    else:
        try:
            sid = int(station_key)
        except ValueError:
            raise Http404
        qs = CamMessage.objects.filter(station_id=sid)

    latest = qs.first()
    if latest is None:
        raise Http404

    context = {
        "station_key": station_key,
        "station_id": latest.station_id,
        "station_type": latest.station_type,
        "station_type_label": _station_label(latest.station_type),
    }
    return render(request, "messages/station_detail.html", context)


# ── JSON API ─────────────────────────────────────────────────────────────────

def messages_api(request):
    try:
        limit = min(int(request.GET.get("limit", 100)), 500)
    except ValueError:
        limit = 100

    qs = CamMessage.objects.all()

    station_key = request.GET.get("station")
    if station_key is not None:
        if station_key == "unknown":
            qs = qs.filter(station_id__isnull=True)
        else:
            try:
                qs = qs.filter(station_id=int(station_key))
            except ValueError:
                return JsonResponse({"messages": []})

    return JsonResponse({"messages": [_message_dict(m) for m in qs[:limit]]})


def stations_api(request):
    """Returns the latest message for each unique station_id."""
    latest_ids = (
        CamMessage.objects
        .values("station_id")
        .annotate(latest_id=Max("id"))
        .values_list("latest_id", flat=True)
    )
    stations_qs = CamMessage.objects.filter(id__in=latest_ids).order_by("-received_at")

    result = []
    for msg in stations_qs:
        sid = msg.station_id
        count = CamMessage.objects.filter(station_id=sid).count()
        result.append({
            "station_key": str(sid) if sid is not None else "unknown",
            "station_id": sid,
            "station_type": msg.station_type,
            "station_type_label": _station_label(msg.station_type),
            "message_count": count,
            "latest": _message_dict(msg),
        })

    return JsonResponse({"stations": result})


def latest_api(request):
    message = CamMessage.objects.first()
    return JsonResponse({"message": _message_dict(message) if message else None})


# ── Map tile proxy ────────────────────────────────────────────────────────────

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

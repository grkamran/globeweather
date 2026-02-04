from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse

import requests
from collections import defaultdict
from datetime import datetime, timezone as tz
import os
import re

from google.cloud import translate_v3 as translate
from google.oauth2 import service_account


# =========================
# Helpers
# =========================
def _get_json(url, params, timeout=25):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        try:
            return r.status_code, r.json(), None
        except Exception:
            return r.status_code, {"message": r.text}, None
    except requests.exceptions.Timeout:
        return 0, None, "timeout"
    except requests.exceptions.RequestException as e:
        return 0, None, f"network_error: {str(e)}"


def _fmt_local_hhmm(unix_ts: int, tz_offset_seconds: int):
    if not unix_ts:
        return None
    return datetime.fromtimestamp(unix_ts + tz_offset_seconds, tz=tz.utc).strftime("%H:%M")


def _day_length_str(sunrise_ts: int, sunset_ts: int):
    if not sunrise_ts or not sunset_ts or sunset_ts <= sunrise_ts:
        return "—"
    secs = sunset_ts - sunrise_ts
    h = secs // 3600
    m = (secs % 3600) // 60
    return f"{int(h)}h {int(m)}m"


def _normalize_lang(lang: str) -> str:
    if not lang:
        return "en"
    lang = (lang or "").strip().lower()
    if lang in ("en", "ru", "tr", "uk", "pl"):
        return lang
    return "en"


def _looks_english(text: str) -> bool:
    # если есть латинские буквы — почти наверняка англ
    return bool(re.search(r"[a-zA-Z]", text or ""))


# =========================
# Fallback translations (when Google creds not set or API fails)
# =========================
_FALLBACK = {
    "ru": {
        "clear sky": "ясно",
        "few clouds": "малооблачно",
        "scattered clouds": "переменная облачность",
        "broken clouds": "облачно с прояснениями",
        "overcast clouds": "пасмурно",
        "mist": "туман",
        "haze": "дымка",
        "fog": "туман",
        "smoke": "дым",
        "dust": "пыль",
        "sand": "песок",
        "ash": "пепел",
        "squalls": "шквалы",
        "tornado": "торнадо",
        "light rain": "небольшой дождь",
        "moderate rain": "умеренный дождь",
        "heavy intensity rain": "сильный дождь",
        "very heavy rain": "очень сильный дождь",
        "extreme rain": "экстремальный дождь",
        "freezing rain": "ледяной дождь",
        "shower rain": "ливневый дождь",
        "light snow": "небольшой снег",
        "snow": "снег",
        "heavy snow": "сильный снег",
        "sleet": "мокрый снег",
        "light shower sleet": "небольшой мокрый снег",
        "shower sleet": "мокрый снег",
        "thunderstorm": "гроза",
        "thunderstorm with rain": "гроза с дождём",
        "thunderstorm with light rain": "гроза с небольшим дождём",
        "thunderstorm with heavy rain": "гроза с сильным дождём",
    },
    "tr": {
        "clear sky": "açık",
        "few clouds": "az bulutlu",
        "scattered clouds": "parçalı bulutlu",
        "broken clouds": "çok bulutlu",
        "overcast clouds": "kapalı",
        "mist": "sis",
        "haze": "pus",
        "fog": "sis",
        "smoke": "duman",
        "dust": "toz",
        "sand": "kum",
        "ash": "kül",
        "squalls": "fırtına hamlesi",
        "tornado": "hortum",
        "light rain": "hafif yağmur",
        "moderate rain": "orta şiddette yağmur",
        "heavy intensity rain": "şiddetli yağmur",
        "very heavy rain": "çok şiddetli yağmur",
        "extreme rain": "aşırı yağmur",
        "freezing rain": "dondurucu yağmur",
        "shower rain": "sağanak",
        "light snow": "hafif kar",
        "snow": "kar",
        "heavy snow": "yoğun kar",
        "sleet": "sulu kar",
        "light shower sleet": "hafif sulu kar",
        "shower sleet": "sulu kar",
        "thunderstorm": "gök gürültülü fırtına",
        "thunderstorm with rain": "yağmurlu fırtına",
        "thunderstorm with light rain": "hafif yağmurlu fırtına",
        "thunderstorm with heavy rain": "şiddetli yağmurlu fırtına",
    },
    "uk": {
        "clear sky": "ясно",
        "few clouds": "малохмарно",
        "scattered clouds": "мінлива хмарність",
        "broken clouds": "хмарно з проясненнями",
        "overcast clouds": "похмуро",
        "mist": "туман",
        "haze": "імла",
        "fog": "туман",
        "smoke": "дим",
        "dust": "пил",
        "sand": "пісок",
        "ash": "попіл",
        "squalls": "шквали",
        "tornado": "торнадо",
        "light rain": "невеликий дощ",
        "moderate rain": "помірний дощ",
        "heavy intensity rain": "сильний дощ",
        "very heavy rain": "дуже сильний дощ",
        "extreme rain": "екстремальний дощ",
        "freezing rain": "крижаний дощ",
        "shower rain": "злива",
        "light snow": "невеликий сніг",
        "snow": "сніг",
        "heavy snow": "сильний сніг",
        "sleet": "мокрий сніг",
        "thunderstorm": "гроза",
        "thunderstorm with rain": "гроза з дощем",
        "thunderstorm with light rain": "гроза з невеликим дощем",
        "thunderstorm with heavy rain": "гроза з сильним дощем",
    },
    "pl": {
        "clear sky": "bezchmurnie",
        "few clouds": "małe zachmurzenie",
        "scattered clouds": "umiarkowane zachmurzenie",
        "broken clouds": "duże zachmurzenie",
        "overcast clouds": "pochmurno",
        "mist": "mgła",
        "haze": "zamglenie",
        "fog": "mgła",
        "smoke": "dym",
        "dust": "pył",
        "sand": "piasek",
        "ash": "popiół",
        "squalls": "szkwały",
        "tornado": "tornado",
        "light rain": "lekki deszcz",
        "moderate rain": "umiarkowany deszcz",
        "heavy intensity rain": "silny deszcz",
        "very heavy rain": "bardzo silny deszcz",
        "extreme rain": "ulewa ekstremalna",
        "freezing rain": "marznący deszcz",
        "shower rain": "deszcz przelotny",
        "light snow": "lekki śnieg",
        "snow": "śnieg",
        "heavy snow": "intensywny śnieg",
        "sleet": "deszcz ze śniegiem",
        "thunderstorm": "burza",
        "thunderstorm with rain": "burza z deszczem",
        "thunderstorm with light rain": "burza z lekkim deszczem",
        "thunderstorm with heavy rain": "burza z ulewnym deszczem",
    },
}


def _fallback_translate_one(desc: str, target_lang: str) -> str:
    target_lang = _normalize_lang(target_lang)
    if target_lang == "en":
        return desc
    if not desc:
        return desc
    key = (desc or "").strip().lower()
    return _FALLBACK.get(target_lang, {}).get(key, desc)


def _fallback_translate_many(descs, target_lang: str):
    return [_fallback_translate_one(x, target_lang) for x in (descs or [])]


# =========================
# Google Translate v3
# =========================
def _translate_texts(texts, target_lang: str):
    """
    Translate list of strings via Google Cloud Translation API v3.
    If creds missing/fail -> returns original.
    """
    target_lang = _normalize_lang(target_lang)
    if target_lang == "en":
        return texts

    project_id = getattr(settings, "GOOGLE_TRANSLATE_PROJECT_ID", None)
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not project_id or not cred_path:
        return texts

    try:
        credentials = service_account.Credentials.from_service_account_file(str(cred_path))
        client = translate.TranslationServiceClient(credentials=credentials)

        parent = f"projects/{project_id}/locations/global"
        response = client.translate_text(
            request={
                "parent": parent,
                "contents": texts,
                "mime_type": "text/plain",
                "target_language_code": target_lang,
            }
        )
        return [t.translated_text for t in response.translations]
    except Exception:
        return texts


def _translate_descriptions(desc_list, lang: str):
    """
    Smart translate:
    - try Google
    - if Google not available or returns English-like text -> fallback dictionary for those items
    """
    lang = _normalize_lang(lang)
    if lang == "en":
        return desc_list

    original = list(desc_list or [])
    google = _translate_texts(original, lang)

    # If google returned same English for some -> fallback only for those
    out = []
    for src, trg in zip(original, google):
        if (not trg) or (_looks_english(trg) and _looks_english(src)):
            out.append(_fallback_translate_one(src, lang))
        else:
            out.append(trg)
    return out


# =========================
# Weather fetch with hourly_by_date
# =========================
def _fetch_weather(city: str, lang: str = "en"):
    api_key = getattr(settings, "OPENWEATHER_API_KEY", "")
    if not api_key:
        return None, "OPENWEATHER_API_KEY is not set in settings.py"

    lang = _normalize_lang(lang)

    # 1) geocode city -> lat/lon
    geo_url = "https://api.openweathermap.org/geo/1.0/direct"
    code, geo, err = _get_json(geo_url, {"q": city, "limit": 1, "appid": api_key})
    if err:
        return None, (
            "OpenWeather geocoding failed: "
            f"{err}. (Network/VPN/Firewall may block api.openweathermap.org)"
        )
    if code != 200 or not isinstance(geo, list) or not geo:
        return None, "City not found."

    lat = float(geo[0].get("lat", 0.0))
    lon = float(geo[0].get("lon", 0.0))
    country = geo[0].get("country", "")
    city_name = geo[0].get("name", city)

    # 2) current weather
    w_url = "https://api.openweathermap.org/data/2.5/weather"
    code, w, err = _get_json(
        w_url,
        {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
    )
    if err:
        return None, f"OpenWeather current weather failed: {err}."
    if code != 200 or not isinstance(w, dict):
        msg = (w or {}).get("message", "weather fetch failed") if isinstance(w, dict) else "weather fetch failed"
        return None, msg

    weather0 = (w.get("weather") or [{}])[0]
    main = w.get("main", {}) or {}
    wind = w.get("wind", {}) or {}
    clouds = w.get("clouds", {}) or {}
    coord = w.get("coord", {}) or {}
    sys = w.get("sys", {}) or {}

    tz_offset = int(w.get("timezone", 0))
    sunrise_ts = int(sys.get("sunrise", 0) or 0)
    sunset_ts = int(sys.get("sunset", 0) or 0)

    current = {
        "city": w.get("name", city_name),
        "country": country or sys.get("country", ""),
        "description": weather0.get("description", "—"),
        "temp": float(main.get("temp", 0.0)),
        "feels_like": float(main.get("feels_like", 0.0)),
        "temp_min": float(main.get("temp_min", 0.0)),
        "temp_max": float(main.get("temp_max", 0.0)),
        "humidity": int(main.get("humidity", 0)),
        "wind_speed": float(wind.get("speed", 0.0)),
        "clouds": int(clouds.get("all", 0)),
        "lat": float(coord.get("lat", lat)),
        "lon": float(coord.get("lon", lon)),
        "timezone": tz_offset,
        "sunrise": sunrise_ts,
        "sunset": sunset_ts,
    }

    sun = {
        "sunrise": _fmt_local_hhmm(sunrise_ts, tz_offset) or "—",
        "sunset": _fmt_local_hhmm(sunset_ts, tz_offset) or "—",
        "day_length": _day_length_str(sunrise_ts, sunset_ts),
    }

    # 3) forecast (3-hour steps)
    f_url = "https://api.openweathermap.org/data/2.5/forecast"
    code, f, err = _get_json(
        f_url,
        {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
    )
    if err:
        return None, f"OpenWeather forecast failed: {err}."
    if code != 200 or not isinstance(f, dict) or "list" not in f:
        msg = (f or {}).get("message", "forecast fetch failed") if isinstance(f, dict) else "forecast fetch failed"
        return None, msg

    by_date = defaultdict(list)
    hourly_by_date = defaultdict(list)

    for item in f.get("list", []):
        dt_txt = item.get("dt_txt")  # "YYYY-MM-DD HH:MM:SS"
        if not dt_txt or len(dt_txt) < 19:
            continue

        date_key = dt_txt[:10]
        time_key = dt_txt[11:16]  # "HH:MM"
        by_date[date_key].append(item)

        w0 = (item.get("weather") or [{}])[0]
        m = item.get("main", {}) or {}
        wd = item.get("wind", {}) or {}
        pop = item.get("pop", 0.0)

        hourly_by_date[date_key].append({
            "time": time_key,
            "temp": float(m.get("temp", 0.0)),
            "feels_like": float(m.get("feels_like", 0.0)),
            "humidity": int(m.get("humidity", 0)),
            "wind_speed": float(wd.get("speed", 0.0)),
            "pop": float(pop) if isinstance(pop, (int, float)) else 0.0,
            "description": w0.get("description", "—"),
        })

    dates = sorted(by_date.keys())[:5]
    daily = []
    daily_descs = []

    for d in dates:
        items = by_date[d]
        temps = [
            x.get("main", {}).get("temp")
            for x in items
            if isinstance(x.get("main", {}).get("temp"), (int, float))
        ]
        if not temps:
            continue

        tmin = min(temps)
        tmax = max(temps)

        rep = next((x for x in items if (x.get("dt_txt", "").endswith("12:00:00"))), None)
        if rep is None:
            rep = items[len(items) // 2]

        w0 = (rep.get("weather") or [{}])[0]
        rep_main = rep.get("main", {}) or {}
        rep_wind = rep.get("wind", {}) or {}

        desc = w0.get("description", "—")
        daily_descs.append(desc)

        daily.append({
            "date": d,
            "min": float(tmin),
            "max": float(tmax),
            "description": desc,
            "humidity": int(rep_main.get("humidity", 0)),
            "wind_speed": float(rep_wind.get("speed", 0.0)),
        })

    # =========================
    # ✅ TRANSLATE ALL DESCRIPTIONS:
    # current + daily + hourly_by_date
    # =========================
    all_desc = []

    # current
    all_desc.append(current["description"])

    # daily
    all_desc.extend(daily_descs)

    # hourly (all items)
    hourly_keys = sorted(hourly_by_date.keys())
    hourly_positions = []  # (date, index_in_list)
    for dk in hourly_keys:
        for idx, obj in enumerate(hourly_by_date[dk]):
            all_desc.append(obj.get("description", "—"))
            hourly_positions.append((dk, idx))

    translated = _translate_descriptions(all_desc, lang)

    # write back
    ptr = 0
    if translated:
        current["description"] = translated[ptr]; ptr += 1

        for i in range(len(daily)):
            if ptr < len(translated):
                daily[i]["description"] = translated[ptr]
            ptr += 1

        for (dk, idx) in hourly_positions:
            if ptr < len(translated):
                hourly_by_date[dk][idx]["description"] = translated[ptr]
            ptr += 1

    # Sort hourly by time
    hourly_by_date_sorted = {}
    for dk, arr in hourly_by_date.items():
        hourly_by_date_sorted[dk] = sorted(arr, key=lambda x: x.get("time", "00:00"))

    return {
        "current": current,
        "daily": daily,
        "sun": sun,
        "hourly_by_date": hourly_by_date_sorted,  # ✅ important for day details
    }, None


# =========================
# Suggestions endpoint
# =========================
def _suggest_cities(q: str, limit: int = 7):
    api_key = getattr(settings, "OPENWEATHER_API_KEY", "")
    if not api_key:
        return None, "OPENWEATHER_API_KEY is not set in settings.py"

    q = (q or "").strip()
    if not q:
        return {"suggestions": []}, None

    geo_url = "https://api.openweathermap.org/geo/1.0/direct"
    code, geo, err = _get_json(geo_url, {"q": q, "limit": int(limit), "appid": api_key})
    if err:
        return None, f"OpenWeather geocoding failed: {err}."

    if code != 200 or not isinstance(geo, list):
        return {"suggestions": []}, None

    out = []
    for item in geo:
        name = item.get("name") or ""
        country = item.get("country") or ""
        state = item.get("state") or ""
        lat = item.get("lat")
        lon = item.get("lon")

        title = name
        subtitle_parts = []
        if state:
            subtitle_parts.append(state)
        if country:
            subtitle_parts.append(country)
        subtitle = ", ".join(subtitle_parts) if subtitle_parts else ""

        out.append({
            "title": title,
            "subtitle": subtitle,
            "lat": lat,
            "lon": lon,
        })

    return {"suggestions": out}, None


# =========================
# Views
# =========================
def home(request):
    return render(request, "home.html", {})


def api_search(request):
    city = (request.GET.get("city") or "").strip()
    lang = (request.GET.get("lang") or "en").strip()

    if not city:
        return JsonResponse({"error": "city is required"}, status=400)

    data, err = _fetch_weather(city, lang=lang)
    if err:
        return JsonResponse({"error": err}, status=503)

    return JsonResponse(data, status=200)


def api_suggest(request):
    q = (request.GET.get("q") or "").strip()
    limit = request.GET.get("limit") or "7"

    try:
        limit = max(3, min(10, int(limit)))
    except Exception:
        limit = 7

    data, err = _suggest_cities(q, limit=limit)
    if err:
        return JsonResponse({"error": err, "suggestions": []}, status=503)

    return JsonResponse(data, status=200)

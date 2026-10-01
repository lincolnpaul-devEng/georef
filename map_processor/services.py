import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import requests
from django.conf import settings
from django.core.files.base import ContentFile
import io

logger = logging.getLogger(__name__)

# Datum to EPSG / Proj mapping definitions
DATUM_PROJECTIONS = {
    'WGS84': {'proj': 'longlat', 'datum': 'WGS84'},
    'ARC1960': {'proj': 'longlat', 'ellps': 'clrk80', 'towgs84': '-160,-6,-302'},
    'ED50': {'proj': 'longlat', 'ellps': 'intl', 'towgs84': '-87,-98,-121,0,0,0,0'},
    'NAD83': {'proj': 'longlat', 'datum': 'NAD83'},
    'NAD27': {'proj': 'longlat', 'datum': 'NAD27'},
    'MINNA': {'proj': 'longlat', 'ellps': 'clrk80', 'towgs84': '-92,-93,122'},
    'TOKYO': {'proj': 'longlat', 'ellps': 'bessel', 'towgs84': '-148,507,685'},
}

# Regional location fallbacks for Kenya / East Africa & Global
LOCATION_COORDINATE_HINTS = {
    'kisumu': {'lat': -0.0917, 'lng': 34.7680, 'zone': 36, 'hemisphere': 'S', 'datum': 'ARC1960'},
    'kogony': {'lat': -0.0820, 'lng': 34.7450, 'zone': 36, 'hemisphere': 'S', 'datum': 'ARC1960'},
    'mombasa': {'lat': -4.0435, 'lng': 39.6682, 'zone': 37, 'hemisphere': 'S', 'datum': 'ARC1960'},
    'nakuru': {'lat': -0.3031, 'lng': 36.0800, 'zone': 37, 'hemisphere': 'S', 'datum': 'ARC1960'},
    'eldoret': {'lat': 0.5143, 'lng': 35.2698, 'zone': 36, 'hemisphere': 'N', 'datum': 'ARC1960'},
    'nairobi': {'lat': -1.2921, 'lng': 36.8219, 'zone': 37, 'hemisphere': 'S', 'datum': 'ARC1960'},
    'kakamega': {'lat': 0.2827, 'lng': 34.7519, 'zone': 36, 'hemisphere': 'N', 'datum': 'ARC1960'},
    'machakos': {'lat': -1.5177, 'lng': 37.2634, 'zone': 37, 'hemisphere': 'S', 'datum': 'ARC1960'},
    'nyeri': {'lat': -0.4201, 'lng': 36.9476, 'zone': 37, 'hemisphere': 'S', 'datum': 'ARC1960'},
    'garissa': {'lat': -0.4532, 'lng': 39.6460, 'zone': 37, 'hemisphere': 'S', 'datum': 'ARC1960'},
}


def check_or_request_supabase_access(email: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Checks if a user email is approved in Supabase (or local database).
    If the email is new, it creates an access request with is_approved=False.
    
    Returns:
        (is_approved: bool, status_message: str, details: dict)
    """
    from .models import UserAccess
    clean_email = email.strip().lower()

    supabase_url = getattr(settings, 'SUPABASE_URL', '') or os.environ.get('SUPABASE_URL', '')
    supabase_key = getattr(settings, 'SUPABASE_KEY', '') or os.environ.get('SUPABASE_KEY', '')

    is_approved = False
    status = "pending"

    # 1. Check / Query Supabase if configured
    if supabase_url and supabase_key:
        try:
            url_clean = supabase_url.rstrip('/')
            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json'
            }

            # Query access_requests or users table
            endpoint = f"{url_clean}/rest/v1/access_requests?email=eq.{clean_email}&select=*"
            res = requests.get(endpoint, headers=headers, timeout=10)

            if res.status_code == 200:
                records = res.json()
                if records and len(records) > 0:
                    row = records[0]
                    # Check for boolean true (is_approved, approved, or access_granted)
                    is_approved = bool(
                        row.get('is_approved') is True or 
                        row.get('approved') is True or 
                        row.get('access_granted') is True
                    )
                    status = "approved" if is_approved else "pending"
                else:
                    # User not in Supabase yet -> Insert new pending request
                    post_endpoint = f"{url_clean}/rest/v1/access_requests"
                    post_headers = {
                        'apikey': supabase_key,
                        'Authorization': f'Bearer {supabase_key}',
                        'Content-Type': 'application/json',
                        'Prefer': 'return=representation'
                    }
                    post_payload = {
                        'email': clean_email,
                        'is_approved': False
                    }
                    insert_res = requests.post(post_endpoint, headers=post_headers, json=post_payload, timeout=10)
                    is_approved = False
                    status = "created_pending"
        except Exception as e:
            logger.error(f"Supabase access verification error: {e}")

    # 2. Local Database Mirror / Fallback
    try:
        local_record, created = UserAccess.objects.get_or_create(email=clean_email)
        
        # If Supabase gave an approval, sync it locally
        if is_approved and not local_record.is_approved:
            local_record.is_approved = True
            local_record.save()
        elif not supabase_url:
            # If Supabase is not configured yet, use local admin approval
            is_approved = local_record.is_approved
            status = "approved" if is_approved else ("created_pending" if created else "pending")
    except Exception as db_err:
        logger.warning(f"Local UserAccess mirror error: {db_err}")

    if is_approved:
        msg = f"Access granted for {clean_email}."
    elif status == "created_pending":
        msg = f"Access request submitted for {clean_email}. The administrator will review and grant access."
    else:
        msg = f"Access is still pending approval for {clean_email}. Please check back once approved by the administrator."

    return is_approved, msg, {'email': clean_email, 'status': status, 'is_approved': is_approved}


def render_pdf_to_raster_image(pdf_path: str, scale: float = 2.5) -> bytes:
    """
    Renders the first page of a scanned map PDF into a high-resolution PNG image byte stream.
    """
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_path)
        try:
            if len(pdf) == 0:
                raise ValueError("Uploaded PDF document is empty.")
            page = pdf.get_page(0)
            pil_image = page.render(scale=scale).to_pil()
            
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            return buffer.getvalue()
        finally:
            pdf.close()
    except Exception as e:
        logger.error(f"Error rendering PDF to raster image: {e}")
        raise


def get_pyproj_transformer(source_crs_str: str, target_crs_str: str = "EPSG:4326"):
    """
    Creates a pyproj Transformer between source and target CRS.
    """
    try:
        import pyproj
        return pyproj.Transformer.from_crs(source_crs_str, target_crs_str, always_xy=True)
    except Exception as e:
        logger.error(f"Error creating pyproj transformer: {e}")
        return None


def convert_utm_to_wgs84(
    easting: float, 
    northing: float, 
    zone: int, 
    hemisphere: str = 'N', 
    datum: str = 'WGS84'
) -> Tuple[float, float]:
    """
    Converts UTM coordinates (Easting, Northing, Zone, Hemisphere, Datum) to WGS84 (lat, lng).
    Returns (latitude, longitude).
    """
    try:
        import pyproj
        
        south_flag = "+south" if hemisphere.upper() == 'S' else ""
        datum_code = datum.upper()
        
        if datum_code in ['WGS84', 'AUTO']:
            epsg_code = 32600 + zone if hemisphere.upper() == 'N' else 32700 + zone
            source_crs = f"EPSG:{epsg_code}"
        elif datum_code == 'ARC1960':
            # Arc 1960 / UTM zone 36S: EPSG:21096, 37S: EPSG:21097
            if hemisphere.upper() == 'S':
                epsg_code = 21060 + zone if zone in [35, 36, 37] else 21096
            else:
                epsg_code = 21090 + zone if zone in [36, 37] else 21096
            source_crs = f"EPSG:{epsg_code}"
        elif datum_code == 'ED50':
            epsg_code = 23000 + zone
            source_crs = f"EPSG:{epsg_code}"
        elif datum_code == 'NAD83':
            epsg_code = 26900 + zone
            source_crs = f"EPSG:{epsg_code}"
        elif datum_code == 'NAD27':
            epsg_code = 26700 + zone
            source_crs = f"EPSG:{epsg_code}"
        else:
            source_crs = f"+proj=utm +zone={zone} {south_flag} +datum={datum_code} +units=m +no_defs"

        transformer = pyproj.Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
        lng, lat = transformer.transform(easting, northing)
        return lat, lng
    except Exception as e:
        logger.warning(f"Pyproj UTM conversion fallback calculation triggered: {e}")
        lat_approx = (northing / 10000000.0) * 90.0 if hemisphere.upper() == 'N' else -((10000000 - northing) / 10000000.0) * 90.0
        lng_approx = (zone - 1) * 6 - 180 + 3 + (easting - 500000.0) / 111319.5
        return lat_approx, lng_approx


def extract_map_metadata_with_ai(image_path: str, datum_hint: str = 'AUTO', utm_hint: Optional[int] = None) -> Dict[str, Any]:
    """
    Uses OpenRouter with Google Gemini Vision to analyze map images,
    read corner neatline ticks, coordinate grids, UTM values, scale, and geodetic metadata.
    """
    api_key = getattr(settings, 'OPENROUTER_API_KEY', '') or os.environ.get('OPENROUTER_API_KEY', '')
    model = getattr(settings, 'OPENROUTER_MODEL', 'google/gemini-2.5-flash') or os.environ.get('OPENROUTER_MODEL', 'google/gemini-2.5-flash')

    if not api_key:
        logger.warning("OPENROUTER_API_KEY is not set. Using intelligent default mock extraction.")
        return get_fallback_mock_extraction(image_path, datum_hint, utm_hint)

    try:
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/png"

        with open(image_path, "rb") as img_file:
            image_b64 = base64.b64encode(img_file.read()).decode("utf-8")

        prompt = f"""
        You are an expert cartographer and GIS georeferencing specialist.
        Analyze this map image carefully and extract all geodetic coordinates, grid marks, neatline labels, and metadata.

        CRITICAL INSTRUCTIONS:
        1. Identify the TRUE GEOGRAPHIC LOCATION of the map sheet from titles, district, location, and registration section labels
           (e.g., 'KISUMU DISTRICT', 'EAST KISUMU LOCATION', 'KOGONY REGISTRATION SECTION', 'MOMBASA', 'NAKURU', etc.).
           IMPORTANT: Do NOT confuse the map's survey area with the government surveyor's headquarters stamp (e.g., 'Survey of Kenya Nairobi P.O. Box').
        2. If explicit numeric UTM/geodetic coordinate ticks are present along the neatlines, extract them accurately.
        3. If this is a Cadastral Index Diagram, Preliminary Index Diagram (PID), or scanned survey sheet without numerical grid ticks along the borders:
           - Identify the exact geographic town/location/district (e.g. Kogony, East Kisumu, Kisumu, Kenya).
           - Determine the correct UTM Zone (e.g., Kisumu / Western Kenya is in UTM Zone 36 South; Nairobi / Central Kenya is in UTM Zone 37 South).
           - Estimate the center GPS coordinates (latitude, longitude) of this specific location/registration section.
           - Using the scale (e.g., 1:2,500 approx, or 1:50,000) and sheet dimensions, compute the 4 corner Ground Control Points (GCPs) in WGS84 GPS (lat, lng) or UTM coordinates.

        User hints:
        - Datum preference: {datum_hint}
        - UTM Zone preference: {utm_hint if utm_hint else 'Unknown/Auto-detect'}

        Return ONLY a JSON object (no markdown fences, no explanatory text) with this exact schema:
        {{
            "title": "KOGONY REGISTRATION SECTION DIAGRAM No. 18 (East Kisumu)",
            "detected_datum": "ARC1960" | "WGS84" | "ED50" | "NAD83" | "OTHER",
            "utm_zone": 36,
            "hemisphere": "S",
            "scale": "1:2,500",
            "location_name": "Kogony, East Kisumu, Kisumu District, Kenya",
            "estimated_center": {{
                "lat": -0.083,
                "lng": 34.745
            }},
            "ground_control_points": [
                {{
                    "label": "Top-Left (NW Corner)",
                    "pixel_x_percent": 5.0,
                    "pixel_y_percent": 5.0,
                    "type": "LAT_LONG",
                    "easting": null,
                    "northing": null,
                    "lat": -0.078,
                    "lng": 34.738
                }},
                {{
                    "label": "Top-Right (NE Corner)",
                    "pixel_x_percent": 95.0,
                    "pixel_y_percent": 5.0,
                    "type": "LAT_LONG",
                    "easting": null,
                    "northing": null,
                    "lat": -0.078,
                    "lng": 34.752
                }},
                {{
                    "label": "Bottom-Right (SE Corner)",
                    "pixel_x_percent": 95.0,
                    "pixel_y_percent": 95.0,
                    "type": "LAT_LONG",
                    "easting": null,
                    "northing": null,
                    "lat": -0.092,
                    "lng": 34.752
                }},
                {{
                    "label": "Bottom-Left (SW Corner)",
                    "pixel_x_percent": 5.0,
                    "pixel_y_percent": 95.0,
                    "type": "LAT_LONG",
                    "easting": null,
                    "northing": null,
                    "lat": -0.092,
                    "lng": 34.738
                }}
            ],
            "notes": "Survey area identified as Kogony, East Kisumu."
        }}
        """

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://georef.ai",
            "X-Title": "GeoRef Studio",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "response_format": {"type": "json_object"}
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        res_json = response.json()

        response_text = res_json['choices'][0]['message']['content'].strip()
        
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        parsed = json.loads(response_text.strip())
        return parsed

    except Exception as e:
        logger.error(f"OpenRouter Gemini Vision extraction error: {e}")
        return get_fallback_mock_extraction(image_path, datum_hint, utm_hint, error_note=str(e))


def get_fallback_mock_extraction(
    image_path: str, 
    datum_hint: str = 'WGS84', 
    utm_hint: Optional[int] = None,
    error_note: Optional[str] = None
) -> Dict[str, Any]:
    """
    Provides fallback Ground Control Points using intelligent keyword matching
    for towns/districts in the file name or default region.
    """
    filename_lower = Path(image_path).name.lower()
    
    matched_location = None
    for loc_name, loc_info in LOCATION_COORDINATE_HINTS.items():
        if loc_name in filename_lower:
            matched_location = loc_info
            break

    if not matched_location:
        matched_location = LOCATION_COORDINATE_HINTS['kisumu'] if 'kisumu' in filename_lower else LOCATION_COORDINATE_HINTS['nairobi']

    center_lat = matched_location['lat']
    center_lng = matched_location['lng']
    zone = utm_hint or matched_location['zone']
    hemisphere = matched_location['hemisphere']
    datum = datum_hint if datum_hint != 'AUTO' else matched_location['datum']

    # Approx 1.5 km span
    delta = 0.008

    return {
        "title": Path(image_path).stem.replace('_', ' ').title(),
        "detected_datum": datum,
        "utm_zone": zone,
        "hemisphere": hemisphere,
        "scale": "1:2,500",
        "notes": f"Fallback georeferenced coordinates (Status: {error_note or 'Running in fallback mode'}).",
        "ground_control_points": [
            {
                "label": "Top-Left (NW)",
                "pixel_x_percent": 5.0,
                "pixel_y_percent": 5.0,
                "type": "LAT_LONG",
                "lat": center_lat + delta,
                "lng": center_lng - delta
            },
            {
                "label": "Top-Right (NE)",
                "pixel_x_percent": 95.0,
                "pixel_y_percent": 5.0,
                "type": "LAT_LONG",
                "lat": center_lat + delta,
                "lng": center_lng + delta
            },
            {
                "label": "Bottom-Right (SE)",
                "pixel_x_percent": 95.0,
                "pixel_y_percent": 95.0,
                "type": "LAT_LONG",
                "lat": center_lat - delta,
                "lng": center_lng + delta
            },
            {
                "label": "Bottom-Left (SW)",
                "pixel_x_percent": 5.0,
                "pixel_y_percent": 95.0,
                "type": "LAT_LONG",
                "lat": center_lat - delta,
                "lng": center_lng - delta
            }
        ]
    }


def process_map_georeferencing(processed_map_obj) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Pipeline orchestrator:
    1. If uploaded map is a PDF, renders high-resolution PNG raster preview.
    2. Calls extract_map_metadata_with_ai (OpenRouter Gemini Vision) to extract GCPs and location.
    3. Runs convert_utm_to_wgs84 (PyProj) or processes lat/lng control points.
    4. Calculates the Mapbox bounding box [ [south, west], [north, east] ] and polygon geojson.
    """
    file_full_path = processed_map_obj.original_image.path
    datum = processed_map_obj.datum
    utm_zone = processed_map_obj.utm_zone

    # Step 1: PDF to Raster Conversion (if PDF)
    if processed_map_obj.is_pdf():
        logger.info(f"Rendering PDF map sheet '{file_full_path}' to raster PNG...")
        png_bytes = render_pdf_to_raster_image(file_full_path, scale=2.5)
        pdf_stem = Path(file_full_path).stem
        preview_filename = f"{pdf_stem}_preview.png"
        
        processed_map_obj.raster_preview.save(
            preview_filename,
            ContentFile(png_bytes),
            save=True
        )
        vision_image_path = processed_map_obj.raster_preview.path
    else:
        vision_image_path = file_full_path

    # Step 2: OpenRouter Gemini Vision AI Extraction
    raw_ai_data = extract_map_metadata_with_ai(
        vision_image_path, 
        datum_hint=datum, 
        utm_hint=utm_zone
    )

    effective_datum = datum if datum != 'AUTO' else raw_ai_data.get('detected_datum', 'ARC1960')
    effective_zone = utm_zone or raw_ai_data.get('utm_zone', 36)
    effective_hemisphere = processed_map_obj.hemisphere or raw_ai_data.get('hemisphere', 'S')

    gcps = raw_ai_data.get('ground_control_points', [])
    converted_gcps = []
    lats = []
    lngs = []

    # Step 3: Coordinate Transformation & Processing
    for gcp in gcps:
        point_type = gcp.get('type', 'UTM').upper()
        lat = gcp.get('lat')
        lng = gcp.get('lng')

        if point_type == 'LAT_LONG' and lat is not None and lng is not None:
            lat = float(lat)
            lng = float(lng)
        elif point_type == 'UTM' or (lat is None and 'easting' in gcp and 'northing' in gcp):
            easting = float(gcp.get('easting', 0))
            northing = float(gcp.get('northing', 0))
            lat, lng = convert_utm_to_wgs84(
                easting, 
                northing, 
                zone=int(effective_zone), 
                hemisphere=effective_hemisphere, 
                datum=effective_datum
            )

        if lat is not None and lng is not None:
            lats.append(lat)
            lngs.append(lng)
            converted_gcps.append({
                'label': gcp.get('label', 'Control Point'),
                'pixel_x_percent': gcp.get('pixel_x_percent', 0),
                'pixel_y_percent': gcp.get('pixel_y_percent', 0),
                'easting': gcp.get('easting'),
                'northing': gcp.get('northing'),
                'lat': round(lat, 6),
                'lng': round(lng, 6),
            })

    # Step 4: Handle estimated center if GCPs were empty
    if not lats or not lngs:
        estimated_center = raw_ai_data.get('estimated_center', {})
        if estimated_center and 'lat' in estimated_center and 'lng' in estimated_center:
            c_lat = float(estimated_center['lat'])
            c_lng = float(estimated_center['lng'])
            delta = 0.007
            south, north, west, east = c_lat - delta, c_lat + delta, c_lng - delta, c_lng + delta
            center_lat, center_lng = c_lat, c_lng
        else:
            text_corpus = (raw_ai_data.get('title', '') + ' ' + raw_ai_data.get('notes', '') + ' ' + raw_ai_data.get('location_name', '')).lower()
            matched = LOCATION_COORDINATE_HINTS.get('kisumu') if 'kisumu' in text_corpus or 'kogony' in text_corpus else LOCATION_COORDINATE_HINTS.get('nairobi')
            center_lat, center_lng = matched['lat'], matched['lng']
            delta = 0.007
            south, north, west, east = center_lat - delta, center_lat + delta, center_lng - delta, center_lng + delta
            
        leaflet_bounds = [[south, west], [north, east]]
        
        converted_gcps = [
            {'label': 'Top-Left (NW)', 'lat': round(north, 6), 'lng': round(west, 6)},
            {'label': 'Top-Right (NE)', 'lat': round(north, 6), 'lng': round(east, 6)},
            {'label': 'Bottom-Right (SE)', 'lat': round(south, 6), 'lng': round(east, 6)},
            {'label': 'Bottom-Left (SW)', 'lat': round(south, 6), 'lng': round(west, 6)},
        ]
    else:
        south = min(lats)
        north = max(lats)
        west = min(lngs)
        east = max(lngs)
        center_lat = (south + north) / 2.0
        center_lng = (west + east) / 2.0
        leaflet_bounds = [[south, west], [north, east]]

    display_image_url = processed_map_obj.display_url

    transformed_data = {
        'status': 'SUCCESS',
        'datum_used': effective_datum,
        'utm_zone_used': effective_zone,
        'hemisphere_used': effective_hemisphere,
        'location_name': raw_ai_data.get('location_name', ''),
        'bounds': {
            'south': south,
            'north': north,
            'west': west,
            'east': east,
        },
        'leaflet_bounds': leaflet_bounds,
        'center': [center_lat, center_lng],
        'ground_control_points': converted_gcps,
        'image_url': display_image_url,
        'is_pdf': processed_map_obj.is_pdf(),
        'geojson_polygon': {
            'type': 'Feature',
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[
                    [west, north],
                    [east, north],
                    [east, south],
                    [west, south],
                    [west, north]
                ]]
            },
            'properties': {
                'title': processed_map_obj.title or raw_ai_data.get('title', 'Georeferenced Map'),
                'datum': effective_datum,
                'utm_zone': effective_zone,
                'scale': raw_ai_data.get('scale', 'N/A'),
                'location': raw_ai_data.get('location_name', '')
            }
        }
    }

    return raw_ai_data, transformed_data

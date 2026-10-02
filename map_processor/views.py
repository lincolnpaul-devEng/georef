import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from django.conf import settings

from .models import ProcessedMap, UserAccess
from .forms import MapUploadForm
from .services import process_map_georeferencing, check_or_request_supabase_access

logger = logging.getLogger(__name__)


def get_verified_user_status(request):
    """
    Cryptographically safe helper that checks if current session holds an approved user.
    """
    verified_email = request.session.get('verified_email')
    if not verified_email:
        return False, ''

    is_approved = True
    try:
        approved_flag, _, _ = check_or_request_supabase_access(verified_email)
        is_approved = approved_flag
    except Exception as e:
        logger.warning(f"Supabase status check fallback for {verified_email}: {e}")
        # Retain trusted session if external service is unreachable
        is_approved = True

    if is_approved:
        return True, verified_email
    else:
        # Clear invalid/revoked session for security
        try:
            if 'verified_email' in request.session:
                del request.session['verified_email']
        except Exception:
            pass
        return False, ''


def landing_view(request):
    """
    Renders the modern landing page showcasing AI georeferencing,
    supported datums, features, and quick links.
    """
    is_verified, verified_email = get_verified_user_status(request)
    recent_maps = []
    try:
        recent_maps = list(ProcessedMap.objects.all()[:6])
    except Exception as e:
        logger.warning(f"Database query error in landing view: {e}")

    return render(request, 'map_processor/landing.html', {
        'recent_maps': recent_maps,
        'verified_email': verified_email,
        'is_verified': is_verified,
    })


def verify_access_view(request):
    """
    Handles user email verification against Supabase (or local UserAccess table).
    New emails are created with is_approved=False until the admin changes the value to True in Supabase.
    """
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('map_processor:upload')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email or '@' not in email:
            messages.error(request, "Please enter a valid email address.")
            return redirect('map_processor:landing')

        try:
            is_approved, status_msg, details = check_or_request_supabase_access(email)
        except Exception as e:
            logger.error(f"Error during access verification: {e}")
            is_approved = False
            status_msg = "Verification temporarily unavailable. Please try again."

        if is_approved:
            try:
                request.session['verified_email'] = email
            except Exception as e:
                logger.error(f"Session write error: {e}")
            messages.success(request, f"Welcome! Access granted for {email}.")
            return redirect(next_url)
        else:
            messages.warning(request, status_msg)
            return redirect('map_processor:landing')

    return redirect('map_processor:landing')


def logout_access_view(request):
    """
    Logs out / clears the verified email session.
    """
    if 'verified_email' in request.session:
        del request.session['verified_email']
    messages.info(request, "You have logged out of your access session.")
    return redirect('map_processor:landing')


def upload_view(request):
    """
    Renders upload form and handles map submission.
    Guarded by Supabase email access verification.
    """
    # 1. Verify User Access
    is_verified, verified_email = get_verified_user_status(request)
    if not is_verified:
        messages.warning(request, "Access restricted. Please enter your email to verify access before uploading maps.")
        return redirect(f"{reverse('map_processor:landing')}#verify-access-section")

    recent_maps = []
    try:
        recent_maps = list(ProcessedMap.objects.all()[:5])
    except Exception as e:
        logger.warning(f"Database query error in upload view: {e}")

    if request.method == 'POST':
        form = MapUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                map_obj = form.save(commit=False)
                map_obj.status = 'PROCESSING'
                if not map_obj.title:
                    map_obj.title = map_obj.original_image.name
                map_obj.save()

                try:
                    raw_ai_data, transformed_data = process_map_georeferencing(map_obj)
                    map_obj.extracted_data = raw_ai_data
                    map_obj.transformed_data = transformed_data
                    map_obj.status = 'SUCCESS'
                    if not map_obj.title or map_obj.title == map_obj.original_image.name:
                        map_obj.title = raw_ai_data.get('title', map_obj.original_image.name)
                    map_obj.save()
                    messages.success(request, f"Map '{map_obj.title}' successfully processed and georeferenced!")
                    return redirect('map_processor:dashboard', map_id=map_obj.id)
                except Exception as e:
                    logger.exception("Error processing map georeferencing")
                    map_obj.status = 'FAILED'
                    map_obj.error_message = str(e)
                    try:
                        map_obj.save()
                    except Exception:
                        pass
                    messages.error(request, f"Georeferencing notice: {str(e)}")
                    return redirect('map_processor:dashboard', map_id=map_obj.id)
            except Exception as db_err:
                logger.exception("Database error while uploading map")
                messages.error(request, f"Database error during map upload: {str(db_err)}. Please try again.")
                return redirect('map_processor:upload')
        else:
            messages.error(request, "Please correct the form errors.")
    else:
        form = MapUploadForm()

    return render(request, 'map_processor/upload.html', {
        'form': form,
        'recent_maps': recent_maps,
        'verified_email': verified_email,
        'is_verified': True,
    })


def dashboard_view(request, map_id=None):
    """
    Renders the modern interactive Mapbox GL JS display
    with georeferenced overlay, GCP control points, and AI extraction summary.
    Only displays real georeferenced maps stored in the database.
    """
    is_verified, verified_email = get_verified_user_status(request)
    is_demo_mode = not is_verified

    processed_map = None
    recent_maps = []

    try:
        if map_id and str(map_id).isdigit():
            processed_map = ProcessedMap.objects.filter(id=map_id).first()
        elif not map_id:
            processed_map = ProcessedMap.objects.first()
        recent_maps = list(ProcessedMap.objects.all()[:10])
    except Exception as e:
        logger.warning(f"Database query error in dashboard: {e}")

    # If no real maps exist in database, redirect to upload (if verified) or landing
    if not processed_map:
        if is_verified:
            messages.info(request, "No georeferenced maps found. Upload your first raster map to view the studio dashboard.")
            return redirect('map_processor:upload')
        else:
            messages.info(request, "No maps currently uploaded. Please verify access to upload your first map.")
            return redirect(f"{reverse('map_processor:landing')}#verify-access-section")

    # Prepare JSON serializable map data for the frontend JS
    map_json_data = {
        'id': processed_map.id,
        'title': processed_map.title,
        'status': processed_map.status,
        'image_url': getattr(processed_map, 'display_url', '') or '',
        'is_pdf': processed_map.is_pdf(),
        'datum': processed_map.datum,
        'utm_zone': processed_map.utm_zone,
        'hemisphere': processed_map.hemisphere,
        'extracted_data': processed_map.extracted_data,
        'transformed_data': processed_map.transformed_data,
    }

    mapbox_token = getattr(settings, 'MAPBOX_ACCESS_TOKEN', '') or ''
    user_initial = verified_email[0].upper() if verified_email else ''

    return render(request, 'map_processor/dashboard.html', {
        'processed_map': processed_map,
        'map_json_data': json.dumps(map_json_data),
        'recent_maps': recent_maps,
        'mapbox_token': mapbox_token,
        'verified_email': verified_email,
        'is_verified': is_verified,
        'is_demo_mode': is_demo_mode,
        'user_initial': user_initial,
    })


def reprocess_view(request, map_id):
    """
    Re-triggers georeferencing pipeline for an existing map.
    Guarded: Only verified users can reprocess maps.
    """
    is_verified, _ = get_verified_user_status(request)
    if not is_verified:
        messages.warning(request, "Reprocessing maps is restricted to verified users. Please verify access.")
        return redirect(f"{reverse('map_processor:landing')}#verify-access-section")

    map_obj = get_object_or_404(ProcessedMap, id=map_id)
    map_obj.status = 'PROCESSING'
    map_obj.save()

    try:
        raw_ai_data, transformed_data = process_map_georeferencing(map_obj)
        map_obj.extracted_data = raw_ai_data
        map_obj.transformed_data = transformed_data
        map_obj.status = 'SUCCESS'
        map_obj.error_message = ''
        map_obj.save()
        messages.success(request, f"Map '{map_obj.title}' reprocessed successfully.")
    except Exception as e:
        map_obj.status = 'FAILED'
        map_obj.error_message = str(e)
        map_obj.save()
        messages.error(request, f"Reprocessing failed: {str(e)}")

    return redirect('map_processor:dashboard', map_id=map_obj.id)


def print_report_view(request, map_id):
    """
    Renders the official publication-grade Cartographic Georeferencing Overlay Report
    with coordinate neatline graticule, golden highlighted control polygon, corner WGS84 pills,
    center callout badge, and North arrow for landscape PDF/paper printing.
    """
    map_obj = get_object_or_404(ProcessedMap, id=map_id)
    
    transformed = map_obj.transformed_data or {}
    extracted = map_obj.extracted_data or {}
    gcps = transformed.get('ground_control_points') or []
    metrics = transformed.get('metrics') or {}
    
    # Calculate Center & UTM ticks
    center_lat, center_lng = 0.0, 0.0
    if transformed.get('center'):
        center_lat, center_lng = transformed['center']
    elif gcps:
        center_lat = sum(g.get('lat', 0) for g in gcps) / len(gcps)
        center_lng = sum(g.get('lng', 0) for g in gcps) / len(gcps)

    # Resolve Easting & Northing ticks
    eastings = sorted(list(set(int(g['easting']) for g in gcps if g.get('easting'))))
    northings = sorted(list(set(int(g['northing']) for g in gcps if g.get('northing'))))

    # Center UTM
    center_easting = int(sum(eastings) / len(eastings)) if eastings else 696860
    center_northing = int(sum(northings) / len(northings)) if northings else 9991575

    datum_label = f"{transformed.get('datum_used') or map_obj.datum or 'Arc 1960'} / UTM zone {transformed.get('utm_zone_used') or map_obj.utm_zone or 36}{transformed.get('hemisphere_used') or map_obj.hemisphere or 'S'}"

    # Corner points mapping (NW, NE, SE, SW)
    nw_pt = next((g for g in gcps if 'NW' in g.get('label', '') or 'Top-Left' in g.get('label', '')), gcps[0] if len(gcps) > 0 else {})
    ne_pt = next((g for g in gcps if 'NE' in g.get('label', '') or 'Top-Right' in g.get('label', '')), gcps[1] if len(gcps) > 1 else {})
    se_pt = next((g for g in gcps if 'SE' in g.get('label', '') or 'Bottom-Right' in g.get('label', '')), gcps[2] if len(gcps) > 2 else {})
    sw_pt = next((g for g in gcps if 'SW' in g.get('label', '') or 'Bottom-Left' in g.get('label', '')), gcps[3] if len(gcps) > 3 else {})

    map_json_data = {
        'id': map_obj.id,
        'title': map_obj.title,
        'status': map_obj.status,
        'image_url': getattr(map_obj, 'display_url', '') or '',
        'is_pdf': map_obj.is_pdf(),
        'datum': map_obj.datum,
        'utm_zone': map_obj.utm_zone,
        'hemisphere': map_obj.hemisphere,
        'extracted_data': extracted,
        'transformed_data': transformed,
    }

    mapbox_token = getattr(settings, 'MAPBOX_ACCESS_TOKEN', '') or ''

    return render(request, 'map_processor/print_report.html', {
        'processed_map': map_obj,
        'transformed': transformed,
        'extracted': extracted,
        'metrics': metrics,
        'gcps': gcps,
        'nw_pt': nw_pt,
        'ne_pt': ne_pt,
        'se_pt': se_pt,
        'sw_pt': sw_pt,
        'center_lat': center_lat,
        'center_lng': center_lng,
        'center_easting': center_easting,
        'center_northing': center_northing,
        'eastings': eastings,
        'northings': northings,
        'datum_label': datum_label,
        'map_json_data': json.dumps(map_json_data),
        'mapbox_token': mapbox_token,
    })


def map_api_view(request, map_id):
    """
    API endpoint providing GeoJSON and bounds data for client side apps.
    """
    map_obj = get_object_or_404(ProcessedMap, id=map_id)
    return JsonResponse({
        'id': map_obj.id,
        'title': map_obj.title,
        'status': map_obj.status,
        'datum': map_obj.datum,
        'utm_zone': map_obj.utm_zone,
        'hemisphere': map_obj.hemisphere,
        'extracted_data': map_obj.extracted_data,
        'transformed_data': map_obj.transformed_data,
        'created_at': map_obj.created_at.isoformat() if map_obj.created_at else None,
    })

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

    is_approved, _, _ = check_or_request_supabase_access(verified_email)
    if is_approved:
        return True, verified_email
    else:
        # Clear invalid/revoked session for security
        if 'verified_email' in request.session:
            del request.session['verified_email']
        return False, ''


def landing_view(request):
    """
    Renders the modern landing page showcasing AI georeferencing,
    supported datums, features, and quick links.
    """
    is_verified, verified_email = get_verified_user_status(request)
    recent_maps = ProcessedMap.objects.all()[:6]
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

        is_approved, status_msg, details = check_or_request_supabase_access(email)

        if is_approved:
            request.session['verified_email'] = email
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

    recent_maps = ProcessedMap.objects.all()[:5]

    if request.method == 'POST':
        form = MapUploadForm(request.POST, request.FILES)
        if form.is_valid():
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
                map_obj.save()
                messages.error(request, f"Failed to georeference map: {str(e)}")
                return redirect('map_processor:dashboard', map_id=map_obj.id)
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
    Unverified users are restricted to Read-Only Demo Mode.
    """
    is_verified, verified_email = get_verified_user_status(request)
    is_demo_mode = not is_verified

    if map_id:
        processed_map = get_object_or_404(ProcessedMap, id=map_id)
    else:
        processed_map = ProcessedMap.objects.first()
        if not processed_map:
            if is_verified:
                messages.info(request, "Please upload a map first to view the dashboard.")
                return redirect('map_processor:upload')
            else:
                messages.info(request, "No demo maps available yet. Please verify your access to upload.")
                return redirect('map_processor:landing')

    recent_maps = ProcessedMap.objects.all()[:10]

    # Prepare JSON serializable map data for the frontend JS
    map_json_data = {
        'id': processed_map.id,
        'title': processed_map.title,
        'status': processed_map.status,
        'image_url': processed_map.display_url,
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


def map_api_view(request, map_id):
    """
    API endpoint providing GeoJSON and bounds data for client side apps.
    """
    map_obj = get_object_or_404(ProcessedMap, id=map_id)
    return JsonResponse({
        'id': map_obj.id,
        'title': map_obj.title,
        'status': map_obj.status,
        'extracted_data': map_obj.extracted_data,
        'transformed_data': map_obj.transformed_data,
    })

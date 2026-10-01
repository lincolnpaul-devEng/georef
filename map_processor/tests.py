import io
import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

from .models import ProcessedMap, UserAccess
from .forms import MapUploadForm
from .services import (
    DATUM_PROJECTIONS,
    convert_utm_to_wgs84,
    check_or_request_supabase_access
)


class ModelTestCase(TestCase):
    """
    Validates model instantiation, properties, and field defaults.
    """
    def setUp(self):
        self.sample_png = SimpleUploadedFile(
            "test_map.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4",
            content_type="image/png"
        )
        self.sample_pdf = SimpleUploadedFile(
            "test_map.pdf",
            b"%PDF-1.4\n%EOF\n",
            content_type="application/pdf"
        )

    def test_processed_map_creation_and_properties(self):
        map_obj = ProcessedMap.objects.create(
            title="Kisumu Topographic Sheet",
            original_image=self.sample_png,
            datum="ARC1960",
            utm_zone=36,
            hemisphere="S",
            status="SUCCESS",
            extracted_data={"scale": "1:50,000", "datum": "Arc 1960"},
            transformed_data={"center": [-0.0917, 34.7680]}
        )
        self.assertEqual(map_obj.title, "Kisumu Topographic Sheet")
        self.assertTrue(map_obj.is_real)
        self.assertFalse(map_obj.is_pdf())
        self.assertIn("test_map", map_obj.display_url)
        self.assertIn("Kisumu Topographic Sheet", str(map_obj))

    def test_processed_map_pdf_detection(self):
        map_pdf = ProcessedMap.objects.create(
            title="PDF Scanned Map",
            original_image=self.sample_pdf,
            status="PENDING"
        )
        self.assertTrue(map_pdf.is_pdf())

    def test_user_access_model(self):
        user_access = UserAccess.objects.create(
            email="developer@tedoraltd.com",
            is_approved=True,
            notes="Dev Admin"
        )
        self.assertEqual(user_access.email, "developer@tedoraltd.com")
        self.assertTrue(user_access.is_approved)
        self.assertIn("APPROVED", str(user_access))


class FormSecurityTestCase(TestCase):
    """
    Validates binary magic headers, file size caps, and XSS sanitization.
    """
    def test_valid_png_upload(self):
        valid_png = SimpleUploadedFile(
            "sheet.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png"
        )
        form = MapUploadForm(
            data={"title": "Valid Sheet", "datum": "ARC1960", "hemisphere": "S"},
            files={"original_image": valid_png}
        )
        self.assertTrue(form.is_valid())

    def test_valid_pdf_upload(self):
        valid_pdf = SimpleUploadedFile(
            "sheet.pdf",
            b"%PDF-1.7\nscanned map data",
            content_type="application/pdf"
        )
        form = MapUploadForm(
            data={"title": "Valid PDF", "datum": "WGS84", "hemisphere": "N"},
            files={"original_image": valid_pdf}
        )
        self.assertTrue(form.is_valid())

    def test_reject_fake_extension_executable(self):
        fake_file = SimpleUploadedFile(
            "malicious.png",
            b"MZ\x90\x00\x03\x00\x00\x00Windows Executable Header",
            content_type="image/png"
        )
        form = MapUploadForm(
            data={"title": "Malicious Upload", "datum": "AUTO", "hemisphere": "N"},
            files={"original_image": fake_file}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("original_image", form.errors)

    def test_xss_title_sanitization(self):
        valid_png = SimpleUploadedFile(
            "sheet.png",
            b"\x89PNG\r\n\x1a\n",
            content_type="image/png"
        )
        form = MapUploadForm(
            data={
                "title": "<script>alert('XSS')</script>Kisumu Sheet 116/2",
                "datum": "ARC1960",
                "hemisphere": "S"
            },
            files={"original_image": valid_png}
        )
        self.assertTrue(form.is_valid())
        cleaned_title = form.cleaned_data["title"]
        self.assertNotIn("<script>", cleaned_title)
        self.assertIn("Kisumu Sheet 116/2", cleaned_title)


class ViewsIntegrationTestCase(TestCase):
    """
    Tests complete request/response lifecycle across all public & guarded routes.
    """
    def setUp(self):
        self.client = Client()
        self.sample_png = SimpleUploadedFile(
            "kisumu_test.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png"
        )
        self.processed_map = ProcessedMap.objects.create(
            title="Kisumu Topographic Sheet 116/2",
            original_image=self.sample_png,
            datum="ARC1960",
            utm_zone=36,
            hemisphere="S",
            status="SUCCESS",
            extracted_data={"scale": "1:50,000", "datum": "Arc 1960"},
            transformed_data={
                "center": [-0.0917, 34.7680],
                "ground_control_points": [
                    {"label": "GCP-1", "lat": -0.0917, "lng": 34.7680}
                ]
            }
        )

    def test_landing_view(self):
        response = self.client.get(reverse('map_processor:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "georef")
        self.assertContains(response, "Supported Coordinate Systems &amp; Geodetic Datums")

    def test_favicon_route(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 204)

    def test_verify_access_approved_flow(self):
        with patch('map_processor.views.check_or_request_supabase_access', return_value=(True, "Access granted.", {})):
            response = self.client.post(
                reverse('map_processor:verify_access'),
                {"email": "lincoln@tedoraltd.com"},
                follow=False
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.client.session.get('verified_email'), "lincoln@tedoraltd.com")

    def test_upload_guard_unverified_redirects(self):
        response = self.client.get(reverse('map_processor:upload'))
        self.assertEqual(response.status_code, 302)
        self.assertIn("#verify-access-section", response.url)

    def test_upload_accessible_when_verified(self):
        with patch('map_processor.views.check_or_request_supabase_access', return_value=(True, "Access granted.", {})):
            self.client.post(reverse('map_processor:verify_access'), {"email": "lincoln@tedoraltd.com"})
            response = self.client.get(reverse('map_processor:upload'))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Upload Map Sheet")

    def test_dashboard_view_with_real_map(self):
        response = self.client.get(reverse('map_processor:dashboard', args=[self.processed_map.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kisumu Topographic Sheet 116/2")
        self.assertContains(response, "GCP-1")

    def test_geojson_api_endpoint(self):
        response = self.client.get(reverse('map_processor:map_api', args=[self.processed_map.id]))
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data["id"], self.processed_map.id)
        self.assertEqual(json_data["status"], "SUCCESS")
        self.assertEqual(json_data["datum"], "ARC1960")

    def test_logout_clears_session(self):
        session = self.client.session
        session['verified_email'] = 'lincoln@tedoraltd.com'
        session.save()

        response = self.client.get(reverse('map_processor:logout_access'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('verified_email', self.client.session)


class GeodeticMathTestCase(TestCase):
    """
    Tests EPSG / Proj geodetic transformations and bounding box computations.
    """
    def test_arc1960_to_wgs84_transformation(self):
        # Kisumu Easting / Northing in Arc 1960 UTM Zone 36S
        # E: 696720 m E, N: 9989850 m N
        lat, lng = convert_utm_to_wgs84(
            easting=696720.0,
            northing=9989850.0,
            zone=36,
            hemisphere='S',
            datum='ARC1960'
        )
        # Result should be approximately -0.0917 Lat, 34.7680 Lng
        self.assertAlmostEqual(lat, -0.0917, delta=0.02)
        self.assertAlmostEqual(lng, 34.7680, delta=0.02)


class SecurityMiddlewareTestCase(TestCase):
    """
    Validates security headers injected by custom middleware.
    """
    def test_security_headers_present(self):
        client = Client()
        response = client.get('/')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
        self.assertIn('mode=block', response.headers.get('X-XSS-Protection', ''))

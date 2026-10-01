from django.db import models


class UserAccess(models.Model):
    """
    Stores access requests and approval status.
    Syncs with Supabase database table 'access_requests'.
    """
    email = models.EmailField(unique=True)
    is_approved = models.BooleanField(default=False, help_text="True when admin grants access.")
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name = "User Access Request"
        verbose_name_plural = "User Access Requests"
        ordering = ['-requested_at']

    def __str__(self):
        status_str = "APPROVED" if self.is_approved else "PENDING"
        return f"{self.email} ({status_str})"


class ProcessedMap(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    DATUM_CHOICES = [
        ('AUTO', 'Auto-detect via AI'),
        ('WGS84', 'WGS 84 (World Geodetic System)'),
        ('ED50', 'ED50 (European Datum 1950)'),
        ('NAD83', 'NAD83 (North American Datum 1983)'),
        ('NAD27', 'NAD27 (North American Datum 1927)'),
        ('ARC1960', 'Arc 1960 (East Africa)'),
        ('MINNA', 'Minna (Nigeria)'),
        ('TOKYO', 'Tokyo Datum (Japan)'),
    ]

    title = models.CharField(max_length=255, blank=True, default='')
    original_image = models.FileField(
        upload_to='maps/%Y/%m/%d/',
        help_text="Uploaded map file (PDF, PNG, JPEG, TIFF, WebP)."
    )
    raster_preview = models.ImageField(
        upload_to='previews/%Y/%m/%d/', 
        blank=True, 
        null=True,
        help_text="Rasterized PNG preview for Mapbox overlay and vision models (generated for PDFs)."
    )
    datum = models.CharField(max_length=50, choices=DATUM_CHOICES, default='AUTO')
    utm_zone = models.IntegerField(null=True, blank=True, help_text="UTM Zone number (1-60). Leave empty for auto-detection.")
    hemisphere = models.CharField(
        max_length=1,
        choices=[('N', 'Northern Hemisphere'), ('S', 'Southern Hemisphere')],
        default='N'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True, default='')
    
    # AI Vision and Math Output
    extracted_data = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="Raw metadata and ground control points extracted by Gemini Vision."
    )
    transformed_data = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="Calculated WGS84 coordinates, bounding box, and Mapbox overlay payload."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def display_url(self):
        """Returns the raster preview URL (if PDF) or original image URL."""
        if self.raster_preview:
            return self.raster_preview.url
        if self.original_image:
            return self.original_image.url
        return ''

    def is_pdf(self):
        return self.original_image.name.lower().endswith('.pdf') if self.original_image else False

    def __str__(self):
        return f"{self.title or self.original_image.name} ({self.status}) - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

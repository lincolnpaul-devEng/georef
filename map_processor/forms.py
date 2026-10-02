import re
from django import forms
from django.utils.html import strip_tags
from .models import ProcessedMap


class MapUploadForm(forms.ModelForm):
    MAX_FILE_SIZE_MB = 25

    class Meta:
        model = ProcessedMap
        fields = ['title', 'original_image', 'datum', 'utm_zone', 'hemisphere']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Topographic Map Sheet 142-A'
            }),
            'original_image': forms.FileInput(attrs={
                'class': 'form-control-file',
                'accept': 'image/png,image/jpeg,image/tiff,image/webp,application/pdf,.pdf'
            }),
            'datum': forms.Select(attrs={
                'class': 'form-select'
            }),
            'utm_zone': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '1 - 60 (Optional)',
                'min': 1,
                'max': 60
            }),
            'hemisphere': forms.Select(attrs={
                'class': 'form-select'
            })
        }

    def clean_title(self):
        title = self.cleaned_data.get('title', '')
        if title:
            # Strip any HTML or script tags to prevent stored XSS
            title = strip_tags(title).strip()
            # Remove any dangerous control characters
            title = re.sub(r'[\x00-\x1f\x7f]', '', title)
        return title

    def clean_original_image(self):
        uploaded_file = self.cleaned_data.get('original_image')
        if uploaded_file:
            # 1. Check File Size Limit
            if uploaded_file.size > self.MAX_FILE_SIZE_MB * 1024 * 1024:
                raise forms.ValidationError(
                    f"File size exceeds maximum limit of {self.MAX_FILE_SIZE_MB}MB."
                )

            # 2. Check File Extension
            ext = uploaded_file.name.lower().split('.')[-1]
            valid_exts = ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff', 'webp']
            if ext not in valid_exts:
                raise forms.ValidationError(
                    f"Unsupported file format (.{ext}). Please upload a PDF or an image (PNG, JPG, TIFF, WebP)."
                )

            # 3. Magic Header Validation (Inspect first 16 bytes for valid file signatures)
            try:
                uploaded_file.seek(0)
                header = uploaded_file.read(16)
                uploaded_file.seek(0)

                is_pdf = header.startswith(b'%PDF-')
                is_png = header.startswith(b'\x89PNG\r\n\x1a\n')
                is_jpg = header.startswith(b'\xff\xd8\xff')
                is_tiff = header.startswith(b'II*\x00') or header.startswith(b'MM\x00*')
                is_webp = b'WEBP' in header or header.startswith(b'RIFF')

                if not (is_pdf or is_png or is_jpg or is_tiff or is_webp):
                    raise forms.ValidationError(
                        "File content does not match a valid PDF or image signature. Upload rejected for security."
                    )
            except forms.ValidationError:
                raise
            except Exception:
                raise forms.ValidationError("Unable to verify file integrity.")

        return uploaded_file

    def clean_utm_zone(self):
        utm_zone = self.cleaned_data.get('utm_zone')
        if utm_zone is not None:
            if utm_zone < 1 or utm_zone > 60:
                raise forms.ValidationError("UTM Zone must be between 1 and 60.")
        return utm_zone


class MediaEvidenceUploadForm(forms.Form):
    """
    Form for uploading citizen incident photos and field video footage
    to extract embedded Exif GPS metadata and pinpoint exact capture location.
    """
    MAX_MEDIA_SIZE_MB = 100

    title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Incident Reference / Description (e.g., Field Report #402)'
        })
    )
    media_file = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control-file',
            'accept': 'image/jpeg,image/png,image/heic,image/tiff,video/mp4,video/quicktime,video/x-matroska,.jpg,.jpeg,.png,.heic,.tif,.tiff,.mp4,.mov,.mkv'
        })
    )

    def clean_title(self):
        title = self.cleaned_data.get('title', '')
        if title:
            title = strip_tags(title).strip()
            title = re.sub(r'[\x00-\x1f\x7f]', '', title)
        return title

    def clean_media_file(self):
        uploaded_file = self.cleaned_data.get('media_file')
        if uploaded_file:
            # 1. Size limit (100MB for video / photo files)
            if uploaded_file.size > self.MAX_MEDIA_SIZE_MB * 1024 * 1024:
                raise forms.ValidationError(
                    f"Media file exceeds {self.MAX_MEDIA_SIZE_MB}MB limit."
                )

            # 2. Extension check
            ext = uploaded_file.name.lower().split('.')[-1]
            valid_exts = ['jpg', 'jpeg', 'png', 'heic', 'tif', 'tiff', 'mp4', 'mov', 'mkv', 'avi']
            if ext not in valid_exts:
                raise forms.ValidationError(
                    f"Unsupported media format (.{ext}). Supported: JPG, PNG, HEIC, TIFF, MP4, MOV, MKV."
                )

        return uploaded_file


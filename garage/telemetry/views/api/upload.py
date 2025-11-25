"""
API upload endpoint for telemetry files.
"""

import gzip
import hashlib
import logging
import zlib
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from ...models import Session
from .auth import api_token_required

logger = logging.getLogger(__name__)


@csrf_exempt
@api_token_required
def api_upload(request):
    """
    API endpoint for uploading telemetry files with API token authentication.

    Security Notes:
    - CSRF exempt because this is a token-authenticated API endpoint
    - Authentication handled by @api_token_required decorator
    - TODO: Add rate limiting to prevent abuse (use django-ratelimit)
    - File validation includes extension and size checks

    Requires: Authorization: Token <api_token> header
    """
    # Only accept POST
    if request.method != 'POST':
        return JsonResponse({
            'error': 'Only POST method is allowed'
        }, status=405)

    # Check if file was uploaded
    if 'file' not in request.FILES:
        return JsonResponse({
            'error': 'No file provided'
        }, status=400)

    uploaded_file = request.FILES['file']

    # Validate file extension
    if not uploaded_file.name.lower().endswith('.ibt') and not uploaded_file.name.lower().endswith('.ibt.gz'):
        return JsonResponse({
            'error': 'Only .ibt files are allowed'
        }, status=400)

    # Check if file is gzipped by reading magic bytes
    file_start = uploaded_file.read(2)
    uploaded_file.seek(0)  # Reset to beginning

    if file_start == b'\x1f\x8b':  # Gzip magic number
        try:
            # Read and decompress the entire file
            compressed_data = uploaded_file.read()
            decompressed_data = gzip.decompress(compressed_data)

            # Create new in-memory file with decompressed data
            decompressed_file = InMemoryUploadedFile(
                file=BytesIO(decompressed_data),
                field_name='file',
                name=uploaded_file.name.replace('.gz', ''),  # Remove .gz extension if present
                content_type='application/octet-stream',
                size=len(decompressed_data),
                charset=None
            )
            uploaded_file = decompressed_file

        except gzip.BadGzipFile:
            return JsonResponse({
                'error': 'File appears corrupted - invalid gzip format'
            }, status=400)
        except (OSError, IOError, zlib.error) as e:
            return JsonResponse({
                'error': f'Decompression error: {str(e)}'
            }, status=400)

    # Validate file size (check against MAX_UPLOAD_SIZE from settings)
    max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 2147483648)  # 2GB default
    if uploaded_file.size > max_size:
        return JsonResponse({
            'error': f'File size exceeds maximum allowed size ({max_size / (1024**3):.1f} GB)'
        }, status=400)

    # Validate minimum file size (IBT files are typically > 1KB)
    if uploaded_file.size < 1024:
        return JsonResponse({
            'error': 'File appears to be too small to be a valid IBT file'
        }, status=400)

    # Calculate file hash for duplicate detection
    uploaded_file.seek(0)  # Reset file pointer to beginning
    hash_obj = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        hash_obj.update(chunk)
    file_hash = hash_obj.hexdigest()
    uploaded_file.seek(0)  # Reset for saving

    # Check for duplicate session
    existing_session = Session.objects.filter(
        driver=request.user,
        file_hash=file_hash
    ).first()

    if existing_session:
        logger.info(f"Duplicate upload detected: {uploaded_file.name} (session {existing_session.id})")
        return JsonResponse({
            'success': True,
            'duplicate': True,
            'session_id': existing_session.id,
            'filename': uploaded_file.name,
            'message': 'This session has already been uploaded'
        }, status=200)

    # Create session
    session = Session(
        driver=request.user,
        ibt_file=uploaded_file,
        file_hash=file_hash,
        processing_status='pending'
    )

    # Try to extract original file modification time from header
    original_mtime = request.META.get('HTTP_X_ORIGINAL_MTIME')
    if original_mtime:
        from django.utils.dateparse import parse_datetime
        parsed_mtime = parse_datetime(original_mtime)
        if parsed_mtime:
            session.session_date = parsed_mtime

    session.save()

    # Queue Celery task for processing
    from ...tasks import parse_ibt_file
    parse_ibt_file.delay(session.id)

    return JsonResponse({
        'success': True,
        'session_id': session.id,
        'filename': uploaded_file.name,
        'message': 'File uploaded successfully and queued for processing'
    }, status=201)

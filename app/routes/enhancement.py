"""
Image Enhancement — Ultrasound only.
Uses Replicate clarity-upscaler, uploads results to Cloudinary.
"""
import io
import sys
import base64
import requests
import replicate
import cloudinary
import cloudinary.uploader
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from PIL import Image
import os

enhancement_bp = Blueprint('enhancement', __name__)

REPLICATE_MODEL = "philz1337x/clarity-upscaler:dfad41707589d68ecdccd1dfa600d55a208f9310748e44bfe35b4a6291453d5e"

cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    api_key    = os.environ.get("CLOUDINARY_API_KEY",    ""),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", ""),
)


@enhancement_bp.route('/api/cv2-debug', methods=['GET'])
def cv2_debug():
    return jsonify({
        'python_version': sys.version,
        'cv2_version':    None,
        'cv2_error':      'cv2 removed — using Replicate clarity-upscaler',
        'libGL_so_files': [],
    })


def upload_to_cloudinary(img: Image.Image, folder: str) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    result = cloudinary.uploader.upload(buf, folder=folder, resource_type="image")
    return result["secure_url"]


def pil_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')


def run_clarity_upscaler(img: Image.Image) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    output = replicate.run(
        REPLICATE_MODEL,
        input={"image": buf},
    )

    url = output[0] if isinstance(output, list) else output
    resp = requests.get(str(url), timeout=120)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert('RGB')


@enhancement_bp.route('/api/enhance', methods=['POST', 'OPTIONS'])
@jwt_required()
def enhance():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    allowed = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    ext     = os.path.splitext(file.filename.lower())[1]
    if ext not in allowed:
        return jsonify({'error': f'Unsupported file type {ext}. Upload a PNG or JPEG ultrasound image.'}), 400

    if not os.environ.get("REPLICATE_API_TOKEN"):
        return jsonify({'error': 'REPLICATE_API_TOKEN not configured'}), 503

    try:
        raw  = file.read()
        orig = Image.open(io.BytesIO(raw)).convert('RGB')

        enhanced = run_clarity_upscaler(orig)

        cloud_ok = bool(os.environ.get("CLOUDINARY_CLOUD_NAME"))
        if cloud_ok:
            try:
                original_url = upload_to_cloudinary(orig,     "diagnovate/originals")
                enhanced_url = upload_to_cloudinary(enhanced, "diagnovate/enhanced")
            except Exception as e:
                print(f"Cloudinary upload failed: {e} — falling back to base64")
                cloud_ok = False

        if not cloud_ok:
            original_url = pil_to_base64(orig)
            enhanced_url = pil_to_base64(enhanced)

        return jsonify({
            'success':        True,
            'original_image': original_url,
            'enhanced_image': enhanced_url,
            'sr_method':      'Replicate clarity-upscaler',
            'original_size':  {'width': orig.size[0],     'height': orig.size[1]},
            'enhanced_size':  {'width': enhanced.size[0], 'height': enhanced.size[1]},
            'scan_type':      'Ultrasound',
        }), 200

    except Exception as e:
        print(f"ERROR in enhance: {e}")
        return jsonify({'error': str(e)}), 500

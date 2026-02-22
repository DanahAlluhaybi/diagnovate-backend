import os
import io
import base64
import numpy as np
import cv2
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from PIL import Image

enhancement_bp = Blueprint('enhancement', __name__)


def apply_clahe(img: Image.Image) -> Image.Image:
    img_np = np.array(img)

    # تحويل لـ LAB عشان نطبق CLAHE على channel الـ brightness فقط
    lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)

    # CLAHE على channel L
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l)

    # دمج القنوات
    lab_enhanced = cv2.merge([l_enhanced, a, b])
    enhanced_np = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2RGB)

    # sharpening kernel
    kernel = np.array([
        [0, -0.5,  0],
        [-0.5,  3, -0.5],
        [0, -0.5,  0]
    ])
    sharpened = cv2.filter2D(enhanced_np, -1, kernel)
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

    # upscale x2 بجودة عالية
    h, w = sharpened.shape[:2]
    upscaled = cv2.resize(sharpened, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)

    return Image.fromarray(upscaled)


@enhancement_bp.route('/api/enhance', methods=['POST'])
@jwt_required(optional=True)
def enhance_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided (field name must be "image")'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        image_bytes = file.read()
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return jsonify({'error': 'Uploaded file is not a valid image'}), 400

    if img.mode != 'RGB':
        img = img.convert('RGB')

    # حفظ الأصلية
    original_buffer = io.BytesIO()
    img.save(original_buffer, format='PNG')
    original_buffer.seek(0)
    original_bytes = original_buffer.read()

    # تصغير لو كبير
    max_size = 512
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.LANCZOS)

    try:
        enhanced_img = apply_clahe(img)
    except Exception as e:
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500

    enhanced_buffer = io.BytesIO()
    enhanced_img.save(enhanced_buffer, format='PNG')
    enhanced_buffer.seek(0)
    enhanced_bytes = enhanced_buffer.read()

    enhanced_b64 = base64.b64encode(enhanced_bytes).decode('utf-8')
    original_b64 = base64.b64encode(original_bytes).decode('utf-8')

    return jsonify({
        'success': True,
        'original': f'data:image/png;base64,{original_b64}',
        'enhanced': f'data:image/png;base64,{enhanced_b64}'
    }), 200
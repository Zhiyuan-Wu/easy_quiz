import os
import uuid
from pathlib import Path
from flask import Flask, request, jsonify
from transformers import AutoModel, AutoTokenizer
import torch
import base64

# ----------------------------
# 配置
# ----------------------------
MODEL_PATH = r'C:\dev\DeepSeek-OCR'
DEVICE = "cpu"  # 可根据环境改为 "cuda" 或 "mps"

# ----------------------------
# 初始化模型（全局加载一次）
# ----------------------------
print("Loading model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModel.from_pretrained(
    MODEL_PATH,
    _attn_implementation='eager',
    trust_remote_code=True,
    use_safetensors=True
)
model = model.eval().to(DEVICE)
print("Model loaded.")

# ----------------------------
# Flask App
# ----------------------------
app = Flask(__name__)
RESULT_BASE = Path("results")
RESULT_BASE.mkdir(exist_ok=True)

# ✅ 新增：根路径，用于服务状态检查
@app.route('/', methods=['GET'])
def home():
    return """
    <h2>✅ DeepSeek-OCR Service is Running!</h2>
    <p>Use <code>POST /ocr</code> with a PNG/JPG file to perform OCR.</p>
    <p>Example: <code>curl -F "file=@image.png" http://localhost:5000/ocr</code></p>
    """, 200

# OCR调试用接口，读取本地已有结果并固定返回a9fad0c3-9303-4326-a230-3be6cf801678下的结果
@app.route('/ocr/test', methods=['POST'])
def ocr_test_endpoint():
    request_id = 'a9fad0c3-9303-4326-a230-3be6cf801678'
    request_dir = RESULT_BASE / request_id
    if not request_dir.exists():
        return jsonify({"error": "Request ID not found"}), 404
    with open(request_dir / "result.mmd", 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    image_data = []
    images_dir = request_dir / "images"
    for img_file in sorted(images_dir.glob("*.jpg")):
        with open(img_file, 'rb') as f:
            image_data.append({
                "filename": "images/" + img_file.name,
                "data": base64.b64encode(f.read()).decode('utf-8')
            })
    return jsonify({"request_id": request_id, "markdown": markdown_content, "images": image_data})

# OCR 接口
@app.route('/ocr', methods=['POST'])
def ocr_endpoint():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        return jsonify({"error": "Only PNG/JPG images are allowed"}), 400

    # 创建唯一请求目录
    request_id = str(uuid.uuid4())
    request_dir = RESULT_BASE / request_id
    request_dir.mkdir(parents=True, exist_ok=True)

    # 保存上传的图片
    input_image_path = request_dir / "input.png"
    file.save(input_image_path)

    try:
        # prompt = "<image>\nFree OCR."
        prompt = "<image>\n<|grounding|>Convert the document to markdown."
        output_path = str(request_dir)

        # 执行 OCR 推理（会生成 result.mmd）
        model.infer(
            tokenizer=tokenizer,
            prompt=prompt,
            image_file=str(input_image_path),
            output_path=output_path,
            base_size=1024,
            image_size=640,
            crop_mode=True,
            test_compress=True,
            save_results=True
        )

        # 读取 result.mmd
        mmd_file = request_dir / "result.mmd"
        if mmd_file.exists():
            with open(mmd_file, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
        else:
            markdown_content = ""

        # 查找生成的图片文件并读取内容
        images_dir = request_dir / "images"
        image_data = []
        if images_dir.exists():
            # 按文件名排序，确保顺序一致
            for img_file in sorted(images_dir.glob("*.jpg")):
                with open(img_file, 'rb') as f:
                    image_data.append({
                        "filename": "images/" + img_file.name,
                        "data": base64.b64encode(f.read()).decode('utf-8')
                    })
            for img_file in sorted(images_dir.glob("*.png")):
                with open(img_file, 'rb') as f:
                    image_data.append({
                        "filename": "images/" + img_file.name,
                        "data": base64.b64encode(f.read()).decode('utf-8')
                    })

        return jsonify({
            "request_id": request_id,
            "markdown": markdown_content,
            "images": image_data
        })

    except Exception as e:
        import shutil
        shutil.rmtree(request_dir, ignore_errors=True)
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("Starting DeepSeek-OCR Web Server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
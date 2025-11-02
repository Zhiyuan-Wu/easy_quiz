import os
import uuid
import hashlib
import subprocess
import tempfile
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file
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

    # 读取文件内容并计算hash
    file_content = file.read()
    file.seek(0)  # 重置文件指针以便后续保存
    
    # 计算图像的hash作为请求ID
    image_hash = hashlib.sha256(file_content).hexdigest()[:32]
    request_id = image_hash
    request_dir = RESULT_BASE / request_id
    
    # 检查是否已存在结果
    mmd_file = request_dir / "result.mmd"
    if mmd_file.exists():
        # 如果结果文件存在，直接返回缓存的结果
        with open(mmd_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # 读取缓存的图片文件
        images_dir = request_dir / "images"
        image_data = []
        if images_dir.exists():
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
    
    # 如果不存在，创建目录并保存图片
    request_dir.mkdir(parents=True, exist_ok=True)
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

# LaTeX编译为PDF接口
@app.route('/compile-latex', methods=['POST'])
def compile_latex():
    """
    将LaTeX内容编译为PDF文件
    
    请求体:
    {
        "latex_content": "LaTeX内容",
        "compile_recipe": [  # 可选，如果不提供则使用默认配置
            ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"],
            ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"]
        ]
    }
    
    返回:
    {
        "success": true,
        "pdf_base64": "base64编码的PDF文件内容"
    }
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    latex_content = data.get('latex_content', '')
    
    if not latex_content:
        return jsonify({"error": "latex_content is required"}), 400
    
    # 获取编译命令序列（如果提供）
    compile_recipe = data.get('compile_recipe', None)
    if not compile_recipe:
        # 使用默认的编译命令序列
        compile_recipe = [
            ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"],
            ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"]
        ]
    
    # 创建临时目录
    temp_dir = Path(tempfile.mkdtemp())
    tex_file = temp_dir / "paper.tex"
    pdf_file = temp_dir / "paper.pdf"
    
    try:
        # 保存LaTeX内容
        with open(tex_file, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        # 执行编译命令序列
        for cmd_template in compile_recipe:
            cmd = []
            for arg in cmd_template:
                cmd.append(arg.replace('{output_dir}', str(temp_dir)).replace('{tex_file}', str(tex_file)))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(temp_dir)
            )
            
            if result.returncode != 0:
                print(f"Compilation warning: {result.stderr}")
                # 继续执行，某些警告不影响最终结果
        
        # 检查PDF是否生成
        if not pdf_file.exists():
            return jsonify({
                "error": "PDF compilation failed",
                "details": "PDF file was not generated"
            }), 500
        
        # 读取PDF文件并转换为base64
        with open(pdf_file, 'rb') as f:
            pdf_data = f.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        
        return jsonify({
            "success": True,
            "pdf_base64": pdf_base64
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Compilation timeout"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


if __name__ == '__main__':
    print("Starting DeepSeek-OCR Web Server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
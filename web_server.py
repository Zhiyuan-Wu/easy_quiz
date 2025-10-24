# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统Web服务器
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
import uuid
from werkzeug.utils import secure_filename
from question_manager import QuestionManager
from ocr_client import DeepSeekOCRClient
from config import WEB_CONFIG, QUESTION_TAGS, OCR_BASE_URL, LLM_CONFIG

app = Flask(__name__)

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 确保上传文件夹存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 初始化题目管理器
question_manager = QuestionManager()

# 初始化OCR客户端
ocr_client = DeepSeekOCRClient(OCR_BASE_URL)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """静态文件服务"""
    return send_from_directory('static', filename)

@app.route('/api/questions', methods=['POST'])
def add_question():
    """添加题目API"""
    try:
        data = request.get_json()
        
        # 验证必需字段
        if not data or 'latex_content' not in data:
            return jsonify({'success': False, 'message': '题目内容不能为空'}), 400
        
        latex_content = data['latex_content']
        tags = data.get('tags', [])
        reference_answer = data.get('reference_answer', '')
        source = data.get('source', '')
        image = data.get('image', [])
        
        # 添加题目
        question_id = question_manager.add_question(
            latex_content=latex_content,
            tags=tags,
            reference_answer=reference_answer,
            source=source,
            image=image
        )
        
        return jsonify({
            'success': True, 
            'message': '题目添加成功',
            'question_id': question_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/auto-tag', methods=['POST'])
def auto_tag_question():
    """自动打标和生成解答API"""
    try:
        data = request.get_json()
        
        if not data or 'latex_content' not in data:
            return jsonify({'success': False, 'message': '题目内容不能为空'}), 400
        
        latex_content = data['latex_content']
        source = data.get('source', '')
        
        # 自动打标和生成解答
        tags, answer = question_manager.auto_tag_and_answer(latex_content, source)
        
        return jsonify({
            'success': True,
            'tags': tags,
            'answer': answer
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/search', methods=['GET'])
def search_questions():
    """搜索题目API"""
    try:
        # 获取查询参数
        tags = request.args.getlist('tags')
        keyword = request.args.get('keyword', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        questions = []
        
        if tags:
            # 按标签查询
            questions = question_manager.get_questions_by_tags(tags)
        elif keyword:
            # 关键词搜索
            questions = question_manager.search_questions(keyword)
        else:
            # 获取所有题目
            questions = question_manager.get_all_questions(limit, offset)
        
        return jsonify({
            'success': True,
            'questions': questions,
            'total': len(questions)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/<int:question_id>', methods=['GET'])
def get_question(question_id):
    """获取单个题目详情API"""
    try:
        question = question_manager.get_question_by_id(question_id)
        
        if question:
            return jsonify({
                'success': True,
                'question': question
            })
        else:
            return jsonify({
                'success': False,
                'message': '题目不存在'
            }), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/<int:question_id>/answer', methods=['GET'])
def get_question_answer(question_id):
    """获取题目参考解答API"""
    try:
        answer = question_manager.get_reference_answer(question_id)
        
        if answer:
            return jsonify({
                'success': True,
                'answer': answer
            })
        else:
            return jsonify({
                'success': False,
                'message': '参考解答不存在'
            }), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """上传图片API"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        if file and allowed_file(file.filename):
            # 生成唯一文件名
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            unique_filename = f"{uuid.uuid4()}{ext}"
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            return jsonify({
                'success': True,
                'filename': unique_filename,
                'url': f'/uploads/{unique_filename}'
            })
        else:
            return jsonify({'success': False, 'message': '不支持的文件类型'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """提供上传的图片文件"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    """删除题目API"""
    try:
        success = question_manager.delete_question(question_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '题目删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '题目不存在'
            }), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/ocr-parse', methods=['POST'])
def ocr_parse():
    """OCR解析试卷API"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        if file and allowed_file(file.filename):
            # 保存临时文件
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            temp_filename = f"temp_{uuid.uuid4()}{ext}"
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            file.save(temp_path)
            
            try:
                # 调用OCR
                ocr_result = ocr_client.ocr_image(temp_path)
                markdown_content = ocr_result.get('markdown', '')
                
                # 调用大模型解析题目
                parsed_questions = question_manager.parse_exam_paper(markdown_content)
                
                return jsonify({
                    'success': True,
                    'questions': parsed_questions
                })
                
            except Exception as e:
                return jsonify({'success': False, 'message': f'OCR解析失败: {str(e)}'}), 500
            finally:
                # 删除临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        else:
            return jsonify({'success': False, 'message': '不支持的文件类型'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tags', methods=['GET'])
def get_tags():
    """获取所有可用标签API"""
    return jsonify({
        'success': True,
        'tags': QUESTION_TAGS
    })

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return jsonify({'success': False, 'message': '页面不存在'}), 404

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    return jsonify({'success': False, 'message': '服务器内部错误'}), 500

if __name__ == '__main__':
    # 确保templates目录存在
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    print(f"启动Web服务器: http://{WEB_CONFIG['host']}:{WEB_CONFIG['port']}")
    app.run(
        host=WEB_CONFIG['host'],
        port=WEB_CONFIG['port'],
        debug=WEB_CONFIG['debug']
    )

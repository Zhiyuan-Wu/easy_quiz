# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统Web服务器
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from functools import wraps
import json
import os
import uuid
import time
from werkzeug.utils import secure_filename
from question_manager import QuestionManager
from ocr_client import DeepSeekOCRClient
from system_manager import SystemManager
from export_renderer import ExportRenderer
from config import WEB_CONFIG, OCR_BASE_URL, LLM_CONFIG, SECRET_KEY, SYSTEM_DATABASE_PATH
from logger import get_logger

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 确保上传文件夹存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 初始化日志记录器
logger = get_logger()

# 初始化系统管理器
system_manager = SystemManager(SYSTEM_DATABASE_PATH)

# 初始化题目管理器
question_manager = QuestionManager(system_manager=system_manager)

# 初始化OCR客户端
ocr_client = DeepSeekOCRClient(OCR_BASE_URL)

# 初始化导出渲染器
export_renderer = ExportRenderer(UPLOAD_FOLDER)

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
@login_required
def index():
    """主页"""
    user = system_manager.get_user_by_id(session['user_id'])
    return render_template('index.html', user=user)

@app.route('/profile')
@login_required
def profile():
    """用户中心页面"""
    user = system_manager.get_user_by_id(session['user_id'])
    return render_template('user_profile.html', user=user)

@app.route('/login')
def login_page():
    """登录页面"""
    return render_template('login.html')

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册API"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        
        success, message = system_manager.register_user(username, password, email)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录API"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = system_manager.authenticate_user(username, password)
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({
                'success': True,
                'message': '登录成功',
                'user': user
            })
        else:
            return jsonify({
                'success': False,
                'message': '用户名或密码错误'
            })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出API"""
    session.clear()
    return jsonify({'success': True, 'message': '已登出'})

@app.route('/api/auth/current', methods=['GET'])
@login_required
def get_current_user():
    """获取当前登录用户信息API"""
    user = system_manager.get_user_by_id(session['user_id'])
    if user:
        return jsonify({
            'success': True,
            'user': user
        })
    return jsonify({'success': False, 'message': '未登录'}), 401

@app.route('/static/<path:filename>')
def static_files(filename):
    """静态文件服务"""
    return send_from_directory('static', filename)

@app.route('/api/questions', methods=['POST'])
@login_required
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
        visibility = data.get('visibility', 'public')  # 新增：可见范围，默认所有人
        
        # 添加题目
        question_id = question_manager.add_question(
            latex_content=latex_content,
            tags=tags,
            reference_answer=reference_answer,
            source=source,
            image=image,
            user_id=session['user_id'],
            visibility=visibility
        )
        
        return jsonify({
            'success': True, 
            'message': '题目添加成功',
            'question_id': question_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/auto-tag', methods=['POST'])
@login_required
def auto_tag_question():
    """自动打标、生成解答和LaTeX格式化API"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'success': False, 'message': '题目内容不能为空'}), 400
        
        content = data['content']
        source = data.get('source', '')
        user_id = session.get('user_id')
        
        logger.log_user_action(user_id, "自动打标和LaTeX格式化", f"内容长度: {len(content)}")
        
        # 自动打标、生成解答和LaTeX格式化
        tags, answer, latex_content = question_manager.auto_tag_and_answer(content, source)
        
        duration = time.time() - start_time
        logger.log_performance("自动打标API", duration, f"用户ID: {user_id}")
        
        return jsonify({
            'success': True,
            'tags': tags,
            'answer': answer,
            'latex_content': latex_content
        })
        
    except Exception as e:
        logger.log_error(e, f"自动打标API失败 - 用户ID: {session.get('user_id')}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/search', methods=['GET'])
@login_required
def search_questions():
    """搜索题目API"""
    try:
        # 获取查询参数
        tags = request.args.getlist('tags')
        keyword = request.args.get('keyword', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        # 获取当前用户ID
        current_user_id = session['user_id']
        
        questions = []
        
        if tags:
            # 按标签查询
            questions = question_manager.get_questions_by_tags(tags, current_user_id)
        elif keyword:
            # 关键词搜索
            questions = question_manager.search_questions(keyword, current_user_id)
        else:
            # 获取所有题目
            questions = question_manager.get_all_questions(limit, offset, current_user_id)
        
        return jsonify({
            'success': True,
            'questions': questions,
            'total': len(questions)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/<int:question_id>', methods=['GET'])
@login_required
def get_question(question_id):
    """获取单个题目详情API"""
    try:
        current_user_id = session['user_id']
        question = question_manager.get_question_by_id(question_id, current_user_id)
        
        if question:
            return jsonify({
                'success': True,
                'question': question
            })
        else:
            return jsonify({
                'success': False,
                'message': '题目不存在或无权访问'
            }), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/questions/stats', methods=['GET'])
@login_required
def get_question_stats():
    """获取题目统计信息API"""
    try:
        current_user_id = session['user_id']
        stats = question_manager.get_question_stats(current_user_id)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
@login_required
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
@login_required
def delete_question(question_id):
    """删除题目API"""
    try:
        current_user_id = session['user_id']
        success = question_manager.delete_question(question_id, current_user_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '题目删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '题目不存在或无权删除'
            }), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/ocr-parse', methods=['POST'])
@login_required
def ocr_parse():
    """OCR解析试卷API"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        if file and allowed_file(file.filename):
            # 保存上传的图片到/uplaod/upload_images/
            if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'upload_images')):
                os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'upload_images'))
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            unique_filename = f"{uuid.uuid4()}{ext}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'upload_images', unique_filename)
            file.save(file_path)
            
            try:
                # 调用OCR
                logger.log_system_info(f"开始OCR处理 - 文件: {file_path}")
                ocr_result = ocr_client.ocr_image(file_path)
                markdown_content = ocr_result.get('markdown', '')
                ocr_images = ocr_result.get('images', [])
                
                logger.log_ocr_result(ocr_result.get('request_id', 'unknown'), markdown_content, len(ocr_images))
                
                # 处理OCR返回的图片数据
                image_filename_mapping = {}  # 原始文件名 -> 本地保存路径的映射
                if ocr_images:
                    # 创建集中的图片目录
                    images_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'ocr_images')
                    if not os.path.exists(images_dir):
                        os.makedirs(images_dir)
                    
                    for img_data in ocr_images:
                        if isinstance(img_data, dict) and 'filename' in img_data and 'data' in img_data:
                            original_filename = img_data['filename']  # 如 "0.jpg", "1.jpg"
                            image_data = img_data['data']
                            
                            # 处理base64编码的图片数据
                            if isinstance(image_data, str):
                                # 如果是base64字符串，解码为bytes
                                import base64
                                image_bytes = base64.b64decode(image_data)
                            else:
                                # 如果已经是bytes，直接使用
                                image_bytes = image_data
                            
                            # 生成唯一文件名避免重名，但保留原始扩展名
                            name, ext = os.path.splitext(original_filename)
                            unique_filename = f"ocr_{uuid.uuid4().hex[:8]}_{original_filename}"
                            dest_path = os.path.join(images_dir, unique_filename)
                            
                            # 保存图片数据到本地
                            with open(dest_path, 'wb') as f:
                                f.write(image_bytes)
                            
                            # 记录映射关系：原始文件名 -> 本地相对路径
                            relative_path = f"/uploads/ocr_images/{unique_filename}"
                            image_filename_mapping[original_filename] = relative_path
                            logger.log_image_processing(original_filename, relative_path, "保存")
                
                # 调用大模型解析题目，传递文件名映射关系
                logger.log_system_info(f"开始解析试卷，markdown内容长度: {len(markdown_content)}, 可用图片数量: {len(image_filename_mapping)}")
                
                parsed_questions = question_manager.parse_exam_paper(markdown_content, image_filename_mapping)
                logger.log_question_parsing(len(parsed_questions), "试卷解析")
                
                if not parsed_questions:
                    return jsonify({
                        'success': False,
                        'message': '试卷解析完成，但没有识别出任何题目。请检查试卷图片质量或内容格式。'
                    })
                
                return jsonify({
                    'success': True,
                    'questions': parsed_questions
                })
                
            except Exception as e:
                return jsonify({'success': False, 'message': f'OCR解析失败: {str(e)}'}), 500

        else:
            return jsonify({'success': False, 'message': '不支持的文件类型'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tags', methods=['GET'])
def get_tags():
    """获取所有可用标签API"""
    try:
        tags = system_manager.get_all_tags(limit=20)
        tag_names = [tag['name'] for tag in tags]
        return jsonify({
            'success': True,
            'tags': tag_names
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/export-paper', methods=['POST'])
@login_required
def export_paper():
    """导出试卷API"""
    try:
        data = request.get_json()
        questions = data.get('questions', [])
        title = data.get('title', '数学试卷')
        mode = data.get('mode', 'questions')  # questions 或 with-answers
        format_type = data.get('format', 'latex')  # latex, docx, 或 pdf
        
        if not questions:
            return jsonify({'success': False, 'message': '没有题目可导出'}), 400
        
        # 保存导出历史
        question_ids = [q.get('id') for q in questions if q.get('id')]
        if question_ids:
            system_manager.save_export_history(
                user_id=session['user_id'],
                title=title,
                question_ids=question_ids,
                export_format=format_type,
                export_mode=mode
            )
        
        # 生成文件内容
        if format_type == 'latex':
            content = export_renderer.render_latex(questions, mode, title)
            mimetype = 'text/plain'
            filename = f'{title}_{uuid.uuid4().hex[:8]}.tex'
        elif format_type == 'docx':
            file_path = export_renderer.render_docx(questions, mode, title)
            return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), 
                                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        elif format_type == 'pdf':
            file_path = export_renderer.render_pdf(questions, mode, title)
            return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), 
                                     as_attachment=True, mimetype='application/pdf')
        else:
            return jsonify({'success': False, 'message': '不支持的格式'}), 400
        
        # 对于LaTeX，直接返回内容
        from flask import Response
        return Response(
            content,
            mimetype=mimetype,
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user/exports', methods=['GET'])
@login_required
def get_user_exports():
    """获取用户导出记录API"""
    try:
        user_id = session['user_id']
        exports = system_manager.get_export_history(user_id, limit=50)
        return jsonify({
            'success': True,
            'exports': exports
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user/reset-password', methods=['POST'])
@login_required
def reset_password():
    """重置密码API"""
    try:
        data = request.get_json()
        user_id = session['user_id']
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        success, message = system_manager.update_password(user_id, old_password, new_password)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user/re-export/<int:export_id>', methods=['GET'])
@login_required
def get_re_export_data(export_id):
    """获取重新导出数据API"""
    try:
        user_id = session['user_id']
        export_data = system_manager.get_export_by_id(export_id)
        
        if not export_data or export_data['user_id'] != user_id:
            return jsonify({'success': False, 'message': '导出记录不存在或无权访问'}), 404
        
        # 根据题目ID获取题目详情
        questions = []
        for question_id in export_data['question_ids']:
            question = question_manager.get_question_by_id(question_id, user_id)
            if question:
                questions.append(question)
        
        return jsonify({
            'success': True,
            'export': export_data,
            'questions': questions
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


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

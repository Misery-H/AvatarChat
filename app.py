# 导入必要的模块
from flask import Flask, request, jsonify, Response, send_file, send_from_directory
import json
import os
import uuid
import logging
import time
import hashlib
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge, BadRequest
from services.image_service import ImageProcessingService
from services.voice_service import VoiceService
from services.chat_service import ChatService
from config.config_loader import config_loader, ConfigurationError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 创建日志目录
Path('logs').mkdir(exist_ok=True)

# 配置请求特定日志
request_logger = logging.getLogger('request')
request_logger.setLevel(logging.INFO)
request_handler = logging.FileHandler('logs/requests.log')
request_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
request_logger.addHandler(request_handler)

# 配置错误日志
error_logger = logging.getLogger('error')
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler('logs/errors.log')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s - %(exc_info)s'))
error_logger.addHandler(error_handler)

# Flask应用配置
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB文件大小限制
app.config['JSON_SORT_KEYS'] = False  # 保持JSON键顺序
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['GENERATED_FOLDER'] = 'generated'
app.config['TEMPLATES_FOLDER'] = 'templates'
app.config['STATIC_FOLDER'] = 'static'

# 导入并注册中间件
from middleware import register_middleware
register_middleware(app)

# 使用配置加载器初始化服务
try:
    # 加载配置
    keys_config = config_loader.load_keys()
    prompts_config = config_loader.load_prompts()
    
    # 创建合并配置以向后兼容现有服务
    config = {
        **keys_config,
        'prompts': prompts_config
    }
    
    # 初始化服务
    image_service = ImageProcessingService(config)
    voice_service = VoiceService(config)
    chat_service = ChatService(config)
    
    logger.info("服务初始化成功")
    
except ConfigurationError as e:
    logger.error(f"启动时配置错误: {e}")
    raise
except Exception as e:
    logger.error(f"服务初始化失败: {e}")
    raise

# 全局会话存储 (生产环境中应使用Redis或数据库)
user_sessions = {}

# ==================== MD5和准备工作检查辅助函数 ====================

def calculate_file_md5(file_path):
    """计算文件的MD5值"""
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"计算MD5失败: {e}")
        return None

def find_existing_image_by_md5(md5_hash, original_filename):
    """根据MD5查找已存在的图像文件"""
    uploads_dir = Path('uploads')
    if not uploads_dir.exists():
        return None
    
    for file_path in uploads_dir.glob('*'):
        if file_path.is_file():
            if calculate_file_md5(file_path) == md5_hash and file_path != original_filename:
                print(f"找到相同图像: {file_path}")
                return str(file_path)
    return None

def check_preparation_completeness(image_uuid, original_image_path):
    """检查指定图像的准备工作是否完整 - 修复分割图像检查"""
    # 分割图像是中间产物，不作为最终检查项
    required_files = {
        'variations': [
            f'generated/avatars/{image_uuid}_variation_1.png',
            f'generated/avatars/{image_uuid}_variation_2.png',
            f'generated/avatars/{image_uuid}_variation_3.png',
            f'generated/avatars/{image_uuid}_variation_4.png'
        ],
        'expressions': [
            f'generated/expressions/{image_uuid}_happy.mp4',
            f'generated/expressions/{image_uuid}_sad.mp4',
            f'generated/expressions/{image_uuid}_surprised.mp4'
        ],
        'personality': f'generated/personality/{image_uuid}_personality.json'
    }
    
    missing_files = {}
    
    # 检查头像变体
    missing_variations = []
    for variation_path in required_files['variations']:
        if not Path(variation_path).exists():
            missing_variations.append(variation_path)
    if missing_variations:
        missing_files['variations'] = missing_variations
        
    # 检查表情动画
    missing_expressions = []
    for expression_path in required_files['expressions']:
        if not Path(expression_path).exists():
            missing_expressions.append(expression_path)
    if missing_expressions:
        missing_files['expressions'] = missing_expressions
    
    # 检查人格数据
    personality_path = Path(required_files['personality'])
    if not personality_path.exists():
        missing_files['personality'] = str(personality_path)
    
    # 计算完成百分比
    total_categories = 3  # variations, expressions, personality
    completed_categories = total_categories - len(missing_files)
    completion_percentage = int((completed_categories / total_categories) * 100)
    
    return missing_files, completion_percentage

def complete_missing_preparation(image_uuid, original_image_path, missing_files):
    """补齐缺失的准备工作"""
    completed_files = {}
    
    try:
        # 补齐分割图像
        if 'segmented_image' in missing_files:
            try:
                segmented_path = image_service.segment_image(original_image_path)
                completed_files['segmented_image'] = segmented_path
                logger.info(f"补齐分割图像: {segmented_path}")
            except Exception as e:
                logger.warning(f"分割图像失败，使用原图: {e}")
                completed_files['segmented_image'] = original_image_path
        
        # 补齐头像变体
        if 'variations' in missing_files:
            try:
                segmented_image = completed_files.get('segmented_image', original_image_path)
                variations = image_service.generate_cartoon_variations(segmented_image, image_uuid)
                completed_files['variations'] = variations
                logger.info(f"补齐头像变体: {len(variations)}个")
            except Exception as e:
                logger.error(f"生成头像变体失败: {e}")
                completed_files['variations'] = []
        
        # 补齐表情动画
        if 'expressions' in missing_files and completed_files.get('variations'):
            try:
                # 使用第一个变体生成表情
                selected_variation = completed_files['variations'][0]
                expressions = image_service.generate_expressions(selected_variation, image_uuid)
                completed_files['expressions'] = expressions
                logger.info(f"补齐表情动画: {len(expressions)}个")
            except Exception as e:
                logger.error(f"生成表情动画失败: {e}")
                completed_files['expressions'] = {}
        
        # 补齐人格数据
        if 'personality' in missing_files:
            try:
                # 使用第一个变体或分割图像生成人格
                avatar_image = completed_files.get('variations', [None])[0] or completed_files.get('segmented_image', original_image_path)
                personality_result = chat_service.generate_personality(avatar_image, image_uuid)
                
                # 检查人格生成是否成功
                if isinstance(personality_result, dict) and 'error' in personality_result:
                    # 人格生成失败，使用默认人格
                    logger.warning(f"人格生成失败，使用默认人格: {personality_result['error']}")
                    personality = {
                        "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                        "habits": ["喜欢学习新知识", "经常为朋友着想"],
                        "voice_tone": "温和"
                    }
                elif isinstance(personality_result, dict) and 'personality_data' in personality_result:
                    # 人格生成成功，提取人格数据
                    personality = personality_result['personality_data']
                else:
                    # 其他情况，使用默认人格
                    logger.warning("人格生成返回格式异常，使用默认人格")
                    personality = {
                        "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                        "habits": ["喜欢学习新知识", "经常为朋友着想"],
                        "voice_tone": "温和"
                    }
                
                completed_files['personality'] = personality
                logger.info(f"补齐人格数据: {personality}")
            except Exception as e:
                logger.error(f"生成人格失败: {e}")
                # 使用默认人格
                completed_files['personality'] = {
                    "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                    "habits": ["喜欢学习新知识", "经常为朋友着想"],
                    "voice_tone": "温和"
                }
        
        return completed_files
        
    except Exception as e:
        logger.error(f"补齐准备工作失败: {e}")
        return completed_files

# ==================== 准备阶段API端点 ====================

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """上传并处理初始图像（支持MD5重复检查）"""
    try:
        # 验证请求
        if 'image' not in request.files:
            return jsonify({
                'error': True,
                'message': '未提供图像文件',
                'code': 'NO_FILE'
            }), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({
                'error': True,
                'message': '未选择文件',
                'code': 'NO_FILENAME'
            }), 400
        
        # 验证文件类型
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        filename = file.filename or ''
        file_ext = Path(filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return jsonify({
                'error': True,
                'message': f'不支持的文件类型。支持的格式: {", ".join(allowed_extensions)}',
                'code': 'INVALID_FORMAT'
            }), 400
        
        # 生成会话ID和图像UUID
        session_id = str(uuid.uuid4())
        image_uuid = str(uuid.uuid4())  # 专门用于文件命名的UUID
        
        # 临时保存文件以计算MD5
        original_filename = file.filename or 'upload.jpg'
        file_ext = Path(original_filename).suffix.lower()
        # 使用UUID作为临时文件名
        temp_filename = f"temp_{image_uuid}{file_ext}"
        temp_path = Path('uploads') / temp_filename
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        
        file.save(temp_path)
        
        # 计算文件MD5
        file_md5 = calculate_file_md5(temp_path)
        if not file_md5:
            return jsonify({
                'error': True,
                'message': '文件处理失败',
                'code': 'FILE_PROCESSING_ERROR'
            }), 500
        
        logger.info(f"文件MD5: {file_md5}")
        
        # 检查是否已存在相同MD5的文件
        existing_image_path = find_existing_image_by_md5(file_md5, temp_path)
        
        if existing_image_path:
            logger.info(f"发现相同图像，MD5: {file_md5}, 文件: {existing_image_path}")
            
            # 删除临时文件
            temp_path.unlink()
            
            # 从现有图像路径提取image_uuid
            existing_image_uuid = Path(existing_image_path).stem
            
            # 检查准备工作完整性
            missing_files, completion_percentage = check_preparation_completeness(existing_image_uuid, existing_image_path)
            
            if len(missing_files) == 0:
                # 准备工作已完整，直接进入聊天流程
                logger.info(f"准备工作已完整，直接进入聊天: {session_id}")
                
                # 加载人格数据
                personality_file_path = f'generated/personality/{existing_image_uuid}_personality.json'
                personality_data = {}
                try:
                    if Path(personality_file_path).exists():
                        with open(personality_file_path, 'r', encoding='utf-8') as f:
                            personality_data = json.load(f)
                        logger.info(f"成功加载人格数据: {personality_data}")
                    else:
                        logger.warning(f"人格文件不存在: {personality_file_path}")
                        # 使用默认人格数据
                        personality_data = {
                            "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                            "habits": ["喜欢学习新知识", "经常为朋友着想"],
                            "voice_tone": "温和"
                        }
                except Exception as e:
                    logger.error(f"加载人格数据失败: {e}")
                    # 使用默认人格数据
                    personality_data = {
                        "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                        "habits": ["喜欢学习新知识", "经常为朋友着想"],
                        "voice_tone": "温和"
                    }
                
                # 重新构建会话数据
                user_sessions[session_id] = {
                    'session_id': session_id,
                    'image_uuid': existing_image_uuid,  # 添加image_uuid字段
                    'original_image_path': existing_image_path,  # 修正字段名
                    'segmented_image': f'temp/segmented_{existing_image_uuid}.jpg',
                    'variations': [f'generated/avatars/{existing_image_uuid}_variation_{i}.png' for i in range(1, 5)],
                    'expressions': {
                        'happy': f'generated/expressions/{existing_image_uuid}_happy.mp4',
                        'sad': f'generated/expressions/{existing_image_uuid}_sad.mp4',
                        'surprised': f'generated/expressions/{existing_image_uuid}_surprised.mp4'
                    },
                    'personality_file': personality_file_path,
                    'personality': personality_data,  # 添加实际的人格数据
                    'status': 'ready_for_chat',
                    'created_at': int(time.time()),
                    'step': 'preparation_complete',
                    'md5': file_md5
                }
                
                return jsonify({
                    'error': False,
                    'session_id': session_id,
                    'message': '检测到相同图像，准备工作已完整，可直接开始聊天',
                    'data': {
                        'status': 'ready_for_chat',
                        'redirect_to_chat': True,
                        'preparation_complete': True,
                        'completion_percentage': completion_percentage
                    }
                })
            else:
                # 准备工作不完整，需要补齐
                logger.info(f"准备工作不完整，开始补齐: {session_id}")
                logger.info(f"缺失文件: {missing_files}")
                
                try:
                    # 补齐缺失的准备工作
                    completed_files = complete_missing_preparation(
                        existing_image_uuid,  # 使用image_uuid而不是session_id
                        existing_image_path, 
                        missing_files
                    )
                    
                    # 更新会话数据
                    user_sessions[session_id] = {
                        'session_id': session_id,
                        'image_uuid': existing_image_uuid,  # 添加image_uuid字段
                        'original_image_path': existing_image_path, # 修复：使用正确的键名
                        'segmented_image': completed_files.get('segmented_image', existing_image_path),
                        'variations': completed_files.get('variations', []),
                        'expressions': completed_files.get('expressions', {}),
                        'personality': completed_files.get('personality'),  # 使用personality字段保持一致性
                        'status': 'preparation_completed',
                        'created_at': int(time.time()),
                        'step': 'preparation_complete',
                        'md5': file_md5,
                        'auto_completed': True
                    }
                    
                    return jsonify({
                        'error': False,
                        'session_id': session_id,
                        'message': '检测到相同图像，已自动补齐准备工作',
                        'data': {
                            'status': 'preparation_completed',
                            'redirect_to_chat': True,
                            'auto_completed': True,
                            'completed_files': completed_files
                        }
                    })
                    
                except Exception as e:
                    logger.error(f"补齐准备工作失败: {e}")
                    # 如果补齐失败，按新图像处理
                    pass
        
        # 新图像处理流程
        # 将临时文件移动到正式位置，使用image_uuid作为文件名
        final_filename = f"{image_uuid}{file_ext}"
        upload_path = Path('uploads') / final_filename
        temp_path.rename(upload_path)
        
        logger.info(f"新图像已上传: {upload_path}")
        
        # 处理图像 - 分割
        try:
            segmented_path = image_service.segment_image(upload_path)
            logger.info(f"图像分割完成: {segmented_path}")
        except Exception as e:
            logger.error(f"图像分割失败: {e}")
            # 如果分割失败，使用原图
            segmented_path = str(upload_path)
        
        # 存储会话数据
        user_sessions[session_id] = {
            'session_id': session_id,
            'image_uuid': image_uuid,  # 添加image_uuid字段
            'original_image_path': str(upload_path), # 修正字段名
            'segmented_image': segmented_path,
            'status': 'uploaded',
            'created_at': int(time.time()),
            'step': 'image_uploaded',
            'md5': file_md5
        }
        
        return jsonify({
            'error': False,
            'session_id': session_id,
            'message': '图像上传和处理成功',
            'data': {
                'original_image': str(upload_path),
                'segmented_image': segmented_path,
                'next_step': 'generate_variations',
                'is_new_image': True
            }
        })
        
    except Exception as e:
        logger.error(f"图像上传失败: {e}")
        return jsonify({
            'error': True,
            'message': f'上传失败: {str(e)}',
            'code': 'UPLOAD_ERROR'
        }), 500

@app.route('/api/avatar-variations', methods=['POST'])
def generate_avatar_variations():
    """生成卡通头像变体"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'error': True,
                'message': '请求数据为空',
                'code': 'NO_DATA'
            }), 400
        
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({
                'error': True,
                'message': '缺少会话ID',
                'code': 'NO_SESSION_ID'
            }), 400
        
        if session_id not in user_sessions:
            return jsonify({
                'error': True,
                'message': '无效的会话ID',
                'code': 'INVALID_SESSION'
            }), 400
        
        session = user_sessions[session_id]
        segmented_image = session['segmented_image']
        image_uuid = session['image_uuid']  # 获取image_uuid
        
        # 更新状态
        session['status'] = 'generating_variations'
        session['step'] = 'generating_variations'
        
        logger.info(f"开始生成头像变体: {session_id}, 图像UUID: {image_uuid}")
        
        # 生成卡通变体
        try:
            variations = image_service.generate_cartoon_variations(segmented_image, image_uuid)
            logger.info(f"生成了 {len(variations)} 个头像变体")
        except Exception as e:
            logger.error(f"头像变体生成失败: {e}")
            return jsonify({
                'error': True,
                'message': f'头像变体生成失败: {str(e)}',
                'code': 'GENERATION_ERROR'
            }), 500
        
        # 更新会话数据
        session.update({
            'variations': variations,
            'status': 'variations_ready',
            'step': 'variations_generated',
            'variations_count': len(variations)
        })
        
        # 构建返回的URL列表
        variation_urls = []
        for i, variation_path in enumerate(variations):
            filename = Path(variation_path).name
            variation_urls.append({
                'index': i,
                'url': f'/api/image/{filename}',
                'path': variation_path
            })
        
        return jsonify({
            'error': False,
            'message': '头像变体生成成功',
            'data': {
                'session_id': session_id,
                'variations': variation_urls,
                'count': len(variations),
                'next_step': 'select_avatar'
            }
        })
        
    except Exception as e:
        logger.error(f"头像变体生成失败: {e}")
        return jsonify({
            'error': True,
            'message': f'变体生成失败: {str(e)}',
            'code': 'VARIATION_ERROR'
        }), 500

@app.route('/api/select-avatar', methods=['POST'])
def select_avatar():
    """选择头像并生成表情动画"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'error': True,
                'message': '请求数据为空',
                'code': 'NO_DATA'
            }), 400
        
        session_id = data.get('session_id')
        selected_index = data.get('selected_index')
        
        if not session_id:
            return jsonify({
                'error': True,
                'message': '缺少会话ID',
                'code': 'NO_SESSION_ID'
            }), 400
        
        if selected_index is None:
            return jsonify({
                'error': True,
                'message': '缺少选择索引',
                'code': 'NO_SELECTION'
            }), 400
        
        if session_id not in user_sessions:
            return jsonify({
                'error': True,
                'message': '无效的会话ID',
                'code': 'INVALID_SESSION'
            }), 400
        
        session = user_sessions[session_id]
        variations = session.get('variations', [])
        image_uuid = session['image_uuid']  # 获取image_uuid
        
        if selected_index >= len(variations) or selected_index < 0:
            return jsonify({
                'error': True,
                'message': f'无效的选择索引。有效范围: 0-{len(variations)-1}',
                'code': 'INVALID_INDEX'
            }), 400
        
        selected_avatar = variations[selected_index]
        
        # 更新状态
        session['status'] = 'processing_selection'
        session['step'] = 'generating_expressions'
        session['selected_avatar'] = selected_avatar
        session['selected_index'] = selected_index
        
        logger.info(f"开始为会话 {session_id} 生成表情和人格，图像UUID: {image_uuid}")
        
        # 同时进行表情生成和人格生成
        expressions = {}
        personality = {}
        
        try:
            # 生成表情动画
            logger.info("生成表情动画...")
            expressions = image_service.generate_expressions(selected_avatar, image_uuid)
            logger.info(f"生成了 {len(expressions)} 种表情动画")
        except Exception as e:
            logger.error(f"表情生成失败: {e}")
            # 创建默认表情映射
            expressions = {emotion: f"{image_uuid}_{emotion}_placeholder.mp4" 
                         for emotion in config['prompts']['expressions'].keys()}
        
        try:
            # 生成人格特征
            logger.info("生成AI人格...")
            personality_result = chat_service.generate_personality(selected_avatar, image_uuid)
            logger.info(f"人格生成完成: {personality_result}")
            
            # 检查人格生成是否成功
            if isinstance(personality_result, dict) and 'error' in personality_result:
                # 人格生成失败，使用默认人格
                logger.warning(f"人格生成失败，使用默认人格: {personality_result['error']}")
                personality = {
                    "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                    "habits": ["喜欢学习新知识", "经常为朋友着想"],
                    "voice_tone": "温和"
                }
            elif isinstance(personality_result, dict) and 'personality_data' in personality_result:
                # 人格生成成功，提取人格数据
                personality = personality_result['personality_data']
            else:
                # 其他情况，使用默认人格
                logger.warning("人格生成返回格式异常，使用默认人格")
                personality = {
                    "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                    "habits": ["喜欢学习新知识", "经常为朋友着想"],
                    "voice_tone": "温和"
                }
        except Exception as e:
            logger.error(f"人格生成失败: {e}")
            # 使用默认人格
            personality = {
                "personality": ["友善热情", "乐于助人", "充满好奇心", "积极乐观"],
                "habits": ["喜欢学习新知识", "经常为朋友着想"],
                "voice_tone": "温和"
            }
        
        # 更新聊天服务的人格
        chat_service.update_personality(personality)
        
        # 更新会话数据
        session.update({
            'expressions': expressions,
            'personality': personality,
            'status': 'ready',
            'step': 'preparation_complete',
            'completed_at': int(time.time())
        })
        
        # 构建表情URL列表
        expression_urls = {}
        for emotion, video_path in expressions.items():
            if Path(video_path).exists():
                filename = Path(video_path).name
                expression_urls[emotion] = f'/api/expression-video/{filename}'
            else:
                expression_urls[emotion] = None
        
        logger.info(f"头像设置完成: {session_id}")
        
        return jsonify({
            'error': False,
            'message': '头像设置完成',
            'data': {
                'session_id': session_id,
                'selected_avatar': {
                    'index': selected_index,
                    'url': f'/api/image/{Path(selected_avatar).name}'
                },
                'personality': personality,
                'expressions': expression_urls,
                'personality_data': personality,
                'next_step': 'start_chat'
            }
        })
        
    except Exception as e:
        logger.error(f"头像选择失败: {e}")
        return jsonify({
            'error': True,
            'message': f'头像选择失败: {str(e)}',
            'code': 'SELECTION_ERROR'
        }), 500

@app.route('/api/preparation-status/<session_id>', methods=['GET'])
def get_preparation_status(session_id):
    """获取准备阶段状态"""
    try:
        if session_id not in user_sessions:
            return jsonify({
                'error': True,
                'message': '会话不存在',
                'code': 'SESSION_NOT_FOUND'
            }), 404
        
        session = user_sessions[session_id]
        
        # 构建状态响应
        status_data = {
            'session_id': session_id,
            'status': session.get('status', 'unknown'),
            'step': session.get('step', 'unknown'),
            'created_at': session.get('created_at'),
            'completed_at': session.get('completed_at')
        }
        
        # 根据当前状态添加相关数据
        if session.get('status') == 'variations_ready':
            status_data['variations_count'] = session.get('variations_count', 0)
        if session.get('status') == 'ready':
            status_data['personality_summary'] = session.get('personality_summary', '')
            status_data['available_expressions'] = list(session.get('expressions', {}).keys())
        
        return jsonify({
            'error': False,
            'data': status_data
        })
        
    except Exception as e:
        logger.error(f"状态查询失败: {e}")
        return jsonify({
            'error': True,
            'message': f'状态查询失败: {str(e)}',
            'code': 'STATUS_ERROR'
        }), 500

# ==================== 聊天阶段API端点 ====================

@app.route('/api/start-recording', methods=['POST'])
def start_recording():
    """开始语音录制会话"""
    try:
        data = request.get_json() or {}
        main_session_id = data.get('session_id')  # 主会话ID（可选）
        
        # 创建录音会话
        recording_session_id = voice_service.start_recording_session()
        
        return jsonify({
            'error': False,
            'recording_session_id': recording_session_id,
            'main_session_id': main_session_id,
            'message': '录音已开始'
        })
        
    except Exception as e:
        logger.error(f"启动录音失败: {e}")
        return jsonify({
            'error': True,
            'message': f'启动录音失败: {str(e)}',
            'code': 'RECORDING_START_ERROR'
        }), 500

@app.route('/api/stop-recording', methods=['POST'])
def stop_recording():
    """停止录音并获取转录结果"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'error': True,
                'message': '请求数据为空',
                'code': 'NO_DATA'
            }), 400
        
        recording_session_id = data.get('recording_session_id')
        if not recording_session_id:
            return jsonify({
                'error': True,
                'message': '缺少录音会话ID',
                'code': 'NO_RECORDING_SESSION'
            }), 400
        
        # 停止录音并获取结果
        result = voice_service.stop_recording_session(recording_session_id)
        
        transcribed_text = result.get('text', '')
        error_msg = result.get('error')
        
        if error_msg:
            return jsonify({
                'error': True,
                'message': f'录音处理失败: {error_msg}',
                'code': 'RECORDING_PROCESS_ERROR'
            }), 500
        
        return jsonify({
            'error': False,
            'transcribed_text': transcribed_text,
            'recording_session_id': recording_session_id,
            'message': '录音停止并转录完成'
        })
        
    except Exception as e:
        logger.error(f"停止录音失败: {e}")
        return jsonify({
            'error': True,
            'message': f'停止录音失败: {str(e)}',
            'code': 'RECORDING_STOP_ERROR'
        }), 500

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """发送文本消息给AI并获取回复 - 支持多轮对话和流式输出"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'error': True,
                'message': '请求数据为空',
                'code': 'NO_DATA'
            }), 400
        
        message = data.get('message', '').strip()
        session_id = data.get('session_id')  # 聊天会话ID
        enable_stream = data.get('stream', False)  # 是否启用流式输出
        
        if not message:
            return jsonify({
                'error': True,
                'message': '消息内容不能为空',
                'code': 'EMPTY_MESSAGE'
            }), 400
        
        logger.info(f"处理消息 (会话: {session_id}, 流式: {enable_stream}): {message}")
        
        # 从user_sessions获取个性化数据并更新聊天服务
        personality_data = None
        if session_id and session_id in user_sessions:
            session_data = user_sessions[session_id]
            personality_data = session_data.get('personality', {})
            
            # 如果找到有效的个性化数据，更新聊天服务
            if personality_data and isinstance(personality_data, dict) and 'error' not in personality_data:
                logger.info(f"为会话 {session_id} 设置个性化数据")
                chat_service.update_personality_for_session(session_id, personality_data)
            else:
                logger.warning(f"会话 {session_id} 缺少有效的个性化数据，将使用默认设置")
        
        # 使用聊天服务处理消息 - 包含会话管理
        result = chat_service.process_message(
            message=message, 
            session_id=session_id,
            message_type="text",
            enable_stream=enable_stream
        )
        
        if result.get('error'):
            return jsonify({
                'error': True,
                'message': f'消息处理失败: {result.get("error")}',
                'code': 'CHAT_PROCESSING_ERROR'
            }), 500
        
        ai_reply = result.get('reply', '')
        emotion = result.get('emotion', 'happy')
        message_id = result.get('message_id')
        actual_session_id = result.get('session_id')  # 获取实际的会话ID
        
        # 如果是流式输出，直接返回流式响应
        if enable_stream and result.get('stream'):
            return jsonify({
                'error': False,
                'message_id': message_id,
                'session_id': actual_session_id,
                'user_message': message,
                'stream': True,
                'emotion': emotion,
                'timestamp': result.get('timestamp', int(time.time())),
                'message': '开始流式输出，请使用 /api/stream-chat 接口获取实时内容'
            })
        
        # 普通输出处理
        # 生成语音回复
        voice_config = {
            'voice': 'longxiaochun_v2',  # 修复语音配置：使用CosyVoice v2音色
            'model': 'cosyvoice-v2',
            'format': 'wav'
        }
        
        audio_url = None
        try:
            if ai_reply:
                # 生成音频会话ID
                audio_session_id = f"msg_{message_id}"
                audio_path = voice_service.text_to_speech(ai_reply, audio_session_id, voice_config)
                if audio_path:
                    filename = Path(audio_path).name
                    audio_url = f"/api/audio/{filename}"
                    logger.info(f"语音生成完成: {audio_url}")
        except Exception as e:
            logger.error(f"语音合成失败: {e}")
        
        # 获取表情视频
        expression_video_url = None
        if actual_session_id and emotion:
            try:
                # 从会话中获取image_uuid
                session_data = user_sessions.get(actual_session_id, {})
                image_uuid = session_data.get('image_uuid')
                
                # 如果当前会话没有image_uuid，尝试从最新的会话中获取
                if not image_uuid and user_sessions:
                    # 查找最近的包含image_uuid的会话
                    for sid, sdata in sorted(user_sessions.items(), 
                                           key=lambda x: x[1].get('created_at', 0), 
                                           reverse=True):
                        if sdata.get('image_uuid'):
                            image_uuid = sdata.get('image_uuid')
                            logger.info(f"从会话 {sid} 获取到image_uuid: {image_uuid}")
                            # 更新当前会话的image_uuid
                            session_data['image_uuid'] = image_uuid
                            break
                
                if image_uuid:
                    expression_video_path = chat_service.select_expression_video(emotion, image_uuid)
                    if expression_video_path and Path(expression_video_path).exists():
                        filename = Path(expression_video_path).name
                        expression_video_url = f"/api/expression-video/{filename}"
                        logger.info(f"找到表情视频: {expression_video_url}")
                    else:
                        logger.warning(f"未找到情感 {emotion} 对应的视频文件 (image_uuid: {image_uuid})")
                else:
                    logger.warning(f"会话 {actual_session_id} 缺少image_uuid")
                    # 尝试列出所有会话的image_uuid以便调试
                    session_uuids = {sid: sdata.get('image_uuid') for sid, sdata in user_sessions.items()}
                    logger.debug(f"所有会话的image_uuid: {session_uuids}")
            except Exception as e:
                logger.error(f"表情视频选择失败: {e}")
        
        response_data = {
            'error': False,
            'message_id': message_id,
            'session_id': actual_session_id,
            'user_message': message,
            'response': ai_reply,  # 修复字段名：前端期望response字段
            'ai_reply': ai_reply,  # 保留原字段以兼容
            'emotion': emotion,
            'audio_url': audio_url,
            'expression_video': expression_video_url,  # 修复字段名：前端期望expression_video字段
            'expression_video_url': expression_video_url,  # 保留原字段以兼容
            'timestamp': result.get('timestamp', int(time.time())),
            'full_reply': result.get('full_reply')  # 包含情感标签的完整回复
        }
        
        logger.info(f"消息处理完成 (会话: {actual_session_id}) - 情感: {emotion}, 音频: {bool(audio_url)}, 视频: {bool(expression_video_url)}")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"消息发送失败: {e}")
        return jsonify({
            'error': True,
            'message': f'消息处理失败: {str(e)}',
            'code': 'MESSAGE_ERROR'
        }), 500

@app.route('/api/chat-session/<session_id>', methods=['GET'])
def get_chat_session(session_id):
    """获取聊天会话信息和历史"""
    try:
        # 获取会话信息
        session_info = chat_service.get_session_info(session_id)
        if not session_info:
            return jsonify({
                'error': True,
                'message': '会话不存在',
                'code': 'SESSION_NOT_FOUND'
            }), 404
        
        # 获取聊天历史
        include_system = request.args.get('include_system', 'false').lower() == 'true'
        chat_history = chat_service.get_chat_history(session_id, include_system)
        
        return jsonify({
            'error': False,
            'session_info': session_info,
            'chat_history': chat_history,
            'message_count': len(chat_history)
        })
        
    except Exception as e:
        logger.error(f"获取聊天会话失败: {e}")
        return jsonify({
            'error': True,
            'message': f'获取会话失败: {str(e)}',
            'code': 'SESSION_ERROR'
        }), 500

@app.route('/api/chat-session/<session_id>', methods=['DELETE'])
def clear_chat_session(session_id):
    """清空指定会话的聊天历史"""
    try:
        chat_service.clear_chat_history(session_id)
        
        return jsonify({
            'error': False,
            'message': f'会话 {session_id} 聊天历史已清空',
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"清空聊天会话失败: {e}")
        return jsonify({
            'error': True,
            'message': f'清空会话失败: {str(e)}',
            'code': 'CLEAR_SESSION_ERROR'
        }), 500

@app.route('/api/update-personality', methods=['POST'])
def update_personality():
    """为指定会话更新人格数据"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'error': True,
                'message': '请求数据为空',
                'code': 'NO_DATA'
            }), 400
        
        session_id = data.get('session_id')
        personality_data = data.get('personality_data')
        
        if not session_id:
            return jsonify({
                'error': True,
                'message': '缺少会话ID',
                'code': 'NO_SESSION_ID'
            }), 400
        
        if not personality_data:
            return jsonify({
                'error': True,
                'message': '缺少人格数据',
                'code': 'NO_PERSONALITY_DATA'
            }), 400
        
        # 更新会话的人格数据
        chat_service.update_personality_for_session(session_id, personality_data)
        
        return jsonify({
            'error': False,
            'message': f'会话 {session_id} 人格数据已更新',
            'session_id': session_id,
            'personality_data': personality_data
        })
        
    except Exception as e:
        logger.error(f"更新人格数据失败: {e}")
        return jsonify({
            'error': True,
            'message': f'更新人格数据失败: {str(e)}',
            'code': 'UPDATE_PERSONALITY_ERROR'
        }), 500

# ==================== 文件服务端点 ====================

@app.route('/api/image/<filename>')
def serve_image(filename):
    """提供生成的头像图片"""
    try:
        # 检查generated/avatars目录
        avatars_path = Path('generated/avatars') / filename
        if avatars_path.exists():
            return send_file(avatars_path)
        
        # 检查static/avatars目录
        static_path = Path('static/avatars') / filename
        if static_path.exists():
            return send_file(static_path)
        
        # 检查uploads目录
        upload_path = Path('uploads') / filename
        if upload_path.exists():
            return send_file(upload_path)
        
        return jsonify({
            'error': True,
            'message': '图片文件未找到',
            'code': 'IMAGE_NOT_FOUND'
        }), 404
        
    except Exception as e:
        logger.error(f"图片服务失败: {e}")
        return jsonify({
            'error': True,
            'message': f'图片服务失败: {str(e)}',
            'code': 'IMAGE_SERVE_ERROR'
        }), 500

@app.route('/api/audio/<filename>')
def serve_audio(filename):
    """提供生成的音频文件"""
    try:
        # 检查generated/audio目录
        audio_path = Path('generated/audio') / filename
        if audio_path.exists():
            return send_file(audio_path, mimetype='audio/wav')
        
        # 检查static/audio目录
        static_path = Path('static/audio') / filename
        if static_path.exists():
            return send_file(static_path, mimetype='audio/wav')
        
        return jsonify({
            'error': True,
            'message': '音频文件未找到',
            'code': 'AUDIO_NOT_FOUND'
        }), 404
        
    except Exception as e:
        logger.error(f"音频服务失败: {e}")
        return jsonify({
            'error': True,
            'message': f'音频服务失败: {str(e)}',
            'code': 'AUDIO_SERVE_ERROR'
        }), 500

@app.route('/api/expression-video/<filename>')
def serve_expression_video(filename):
    """提供表情视频文件"""
    try:
        # 检查generated/expressions目录
        video_path = Path('generated/expressions') / filename
        if video_path.exists():
            return send_file(video_path, mimetype='video/mp4')
        
        # 检查static/expressions目录
        static_path = Path('static/expressions') / filename
        if static_path.exists():
            return send_file(static_path, mimetype='video/mp4')
        
        return jsonify({
            'error': True,
            'message': '表情视频未找到',
            'code': 'VIDEO_NOT_FOUND'
        }), 404
        
    except Exception as e:
        logger.error(f"视频服务失败: {e}")
        return jsonify({
            'error': True,
            'message': f'视频服务失败: {str(e)}',
            'code': 'VIDEO_SERVE_ERROR'
        }), 500

# ==================== 前端页面端点 ====================

@app.route('/')
def serve_prepare_page():
    """提供准备阶段页面"""
    try:
        return send_file('templates/prepare.html')
    except FileNotFoundError:
        return jsonify({
            'error': True,
            'message': '准备页面模板未找到',
            'code': 'TEMPLATE_NOT_FOUND'
        }), 404

@app.route('/prepare')
def serve_prepare_page_alt():
    """提供准备页面（备用路由）"""
    try:
        return send_file('templates/prepare.html')
    except FileNotFoundError:
        return jsonify({
            'error': True,
            'message': '准备页面模板未找到',
            'code': 'TEMPLATE_NOT_FOUND'
        }), 404

@app.route('/chat')
def serve_chat_page():
    """提供聊天页面"""
    try:
        return send_file('templates/chat.html')
    except FileNotFoundError:
        return jsonify({
            'error': True,
            'message': '聊天页面模板未找到',
            'code': 'TEMPLATE_NOT_FOUND'
        }), 404

@app.route('/api/preparation-status')
def get_preparation_status_general():
    """获取准备工作状态（不需要session_id参数）- 修复版本"""
    try:
        # 获取session_id (可以从cookie、session、或query参数获取)
        session_id = request.args.get('session_id')
        
        if not session_id:
            # 如果没有session_id，检查是否有活跃的会话
            if user_sessions:
                # 使用最新的会话
                session_id = max(user_sessions.keys(), key=lambda k: user_sessions[k].get('created_at', 0))
                logger.info(f"自动选择最新会话: {session_id}")
            else:
                logger.warning("没有活跃的会话")
                return jsonify({
                    'error': False,
                    'is_ready': False,
                    'message': '没有活跃的会话',
                    'redirect_to': '/'
                })
        
        if session_id not in user_sessions:
            logger.warning(f"会话不存在: {session_id}")
            return jsonify({
                'error': False,
                'is_ready': False,
                'message': '会话不存在',
                'redirect_to': '/'
            })
        
        session = user_sessions[session_id]
        logger.info(f"检查会话 {session_id} 的准备状态")
        
        # 获取image_uuid
        image_uuid = session.get('image_uuid')
        original_image_path = session.get('original_image_path')
        
        if not image_uuid or not original_image_path:
            logger.warning(f"会话 {session_id} 缺少必要数据: image_uuid={image_uuid}, original_image_path={original_image_path}")
            return jsonify({
                'error': False,
                'is_ready': False,
                'message': '会话数据不完整',
                'redirect_to': '/'
            })
        
        # 使用修复过的文件完整性检查函数
        try:
            missing_files, completion_percentage = check_preparation_completeness(image_uuid, original_image_path)
            is_ready = len(missing_files) == 0
            
            logger.info(f"文件完整性检查结果 - 准备就绪: {is_ready}, 完成度: {completion_percentage}%, 缺失文件: {list(missing_files.keys())}")
            
        except Exception as e:
            logger.error(f"文件完整性检查失败: {e}")
            is_ready = False
            completion_percentage = 0
            missing_files = {'check_failed': ['文件检查失败']}
        
        # 检查人格数据是否有效
        personality_valid = False
        if is_ready:
            personality = session.get('personality', {})
            if not personality or 'error' in personality:
                logger.warning(f"会话 {session_id} 人格数据无效: {personality}")
                is_ready = False
            elif not isinstance(personality, dict):
                logger.warning(f"会话 {session_id} 人格数据格式错误")
                is_ready = False
            else:
                # 检查人格数据的基本字段
                required_personality_fields = ['personality', 'habits', 'voice_tone']
                personality_valid = all(field in personality for field in required_personality_fields)
                if not personality_valid:
                    missing_fields = [field for field in required_personality_fields if field not in personality]
                    logger.warning(f"会话 {session_id} 缺少人格字段: {missing_fields}")
                    is_ready = False
        
        # 构建详细的响应数据
        response_data = {
            'error': False,
            'is_ready': is_ready,
            'session_id': session_id,
            'status': session.get('status', 'unknown'),
            'step': session.get('step', 'unknown'),
            'completion_percentage': completion_percentage,
            'message': '会话就绪' if is_ready else '会话未就绪，需要完成准备工作',
            'redirect_to': '/chat' if is_ready else '/',
            'details': {
                'files_ready': len(missing_files) == 0,
                'personality_ready': personality_valid,
                'image_uuid': image_uuid,
                'missing_files': list(missing_files.keys()) if missing_files else []
            }
        }
        
        if is_ready:
            logger.info(f"会话 {session_id} 准备完成，可以进入聊天")
        else:
            logger.info(f"会话 {session_id} 未准备完成: 文件就绪={len(missing_files) == 0}, 人格就绪={personality_valid}")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"获取准备状态失败: {e}")
        return jsonify({
            'error': False,
            'is_ready': False,
            'message': '状态检查失败，请重新开始',
            'redirect_to': '/',
            'details': {
                'error_message': str(e)
            }
        })

# ==================== 工具端点 ====================

@app.route('/api/health')
def health_check():
    """健康检查端点"""
    try:
        # 简单检查服务状态
        service_status = {
            'image_service': 'ok',
            'voice_service': 'ok', 
            'chat_service': 'ok'
        }
        
        return jsonify({
            'status': 'healthy',
            'message': 'AI Avatar Chat API 运行正常',
            'services': service_status,
            'timestamp': int(time.time())
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'message': f'健康检查失败: {str(e)}',
            'timestamp': int(time.time())
        }), 500

@app.route('/api/sessions/<session_id>/cleanup', methods=['POST'])
def cleanup_session(session_id):
    """清理会话数据"""
    try:
        if session_id not in user_sessions:
            return jsonify({
                'error': True,
                'message': '会话不存在',
                'code': 'SESSION_NOT_FOUND'
            }), 404
        
        # 清理会话数据
        del user_sessions[session_id]
        
        # 清理相关文件
        try:
            voice_service.cleanup_session(session_id)
        except Exception as e:
            logger.warning(f"语音服务清理失败: {e}")
        
        logger.info(f"会话已清理: {session_id}")
        
        return jsonify({
            'error': False,
            'message': '会话清理完成',
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"会话清理失败: {e}")
        return jsonify({
            'error': True,
            'message': f'会话清理失败: {str(e)}',
            'code': 'CLEANUP_ERROR'
        }), 500

@app.route('/api/debug/sessions')
def debug_sessions():
    """调试：查看当前会话（仅开发环境）"""
    if not app.debug:
        return jsonify({
            'error': True,
            'message': '仅在调试模式下可用',
            'code': 'DEBUG_ONLY'
        }), 403
    
    sessions_info = {}
    for sid, session in user_sessions.items():
        sessions_info[sid] = {
            'status': session.get('status'),
            'step': session.get('step'),
            'created_at': session.get('created_at'),
            'variations_count': session.get('variations_count', 0),
            'has_personality': bool(session.get('personality')),
            'expressions_count': len(session.get('expressions', {}))
        }
    
    return jsonify({
        'error': False,
        'sessions_count': len(sessions_info),
        'sessions': sessions_info
    })

# ==================== 测试和调试端点 ====================

@app.route('/audio_test.html')
def audio_test_page():
    """音频测试页面"""
    try:
        test_file = Path("audio_test.html")
        if test_file.exists():
            return send_file(test_file, mimetype='text/html')
        else:
            return jsonify({
                'error': True,
                'message': '音频测试页面不存在',
                'code': 'TEST_PAGE_NOT_FOUND'
            }), 404
    except Exception as e:
        logger.error(f"音频测试页面服务失败: {e}")
        return jsonify({
            'error': True,
            'message': f'测试页面服务失败: {str(e)}',
            'code': 'TEST_PAGE_ERROR'
        }), 500

@app.route('/api/audio-debug/<filename>')
def debug_audio_file(filename):
    """调试音频文件，返回详细信息"""
    try:
        # 检查generated/audio目录
        audio_path = Path('generated/audio') / filename
        static_path = Path('static/audio') / filename
        
        file_info = {
            'filename': filename,
            'generated_exists': audio_path.exists(),
            'static_exists': static_path.exists(),
            'generated_size': audio_path.stat().st_size if audio_path.exists() else 0,
            'static_size': static_path.stat().st_size if static_path.exists() else 0
        }
        
        # 检查文件格式
        target_path = audio_path if audio_path.exists() else static_path
        if target_path.exists():
            try:
                import wave
                with wave.open(str(target_path), 'rb') as wav:
                    file_info['wav_format'] = {
                        'channels': wav.getnchannels(),
                        'width': wav.getsampwidth(),
                        'rate': wav.getframerate(),
                        'frames': wav.getnframes(),
                        'duration': wav.getnframes() / wav.getframerate()
                    }
                    
                # 检查文件头
                with open(target_path, 'rb') as f:
                    header = f.read(12)
                    file_info['header_valid'] = header[:4] == b'RIFF' and header[8:12] == b'WAVE'
                    file_info['header_hex'] = header.hex()
                    
            except Exception as e:
                file_info['format_error'] = str(e)
        
        return jsonify({
            'error': False,
            'data': file_info
        })
        
    except Exception as e:
        logger.error(f"音频调试失败: {e}")
        return jsonify({
            'error': True,
            'message': f'音频调试失败: {str(e)}',
            'code': 'AUDIO_DEBUG_ERROR'
        }), 500

if __name__ == '__main__':
    # 创建必要的目录
    required_directories = [
        'uploads', 'temp/processing', 'temp/sessions', 'temp/audio',
        'generated/avatars', 'generated/expressions', 'generated/audio', 
        'static/avatars', 'static/expressions', 'static/audio',
        'templates', 'logs'
    ]
    
    for dir_name in required_directories:
        Path(dir_name).mkdir(parents=True, exist_ok=True)
    
    logger.info("AI Avatar Chat 应用启动")
    logger.info("准备阶段API端点:")
    logger.info("  POST /api/upload-image - 上传并处理图像")
    logger.info("  POST /api/avatar-variations - 生成头像变体") 
    logger.info("  POST /api/select-avatar - 选择头像并生成表情")
    logger.info("  GET  /api/preparation-status/<session_id> - 获取准备状态")
    logger.info("聊天阶段API端点:")
    logger.info("  POST /api/start-recording - 开始录音")
    logger.info("  POST /api/stop-recording - 停止录音")
    logger.info("  POST /api/send-message - 发送消息")
    logger.info("文件服务端点:")
    logger.info("  GET  /api/image/<filename> - 获取图片")
    logger.info("  GET  /api/audio/<filename> - 获取音频")
    logger.info("  GET  /api/expression-video/<filename> - 获取表情视频")
    
    app.run(debug=True, port=5000, host='0.0.0.0')
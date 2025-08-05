#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# type: ignore
"""
聊天服务 - 改进版多轮对话和流式输出支持
集成Qwen LLM对话、情感检测、人格生成等功能
"""

import json
import base64
import re
import uuid
import time
import os
from typing import Dict, List, Optional, Tuple, Generator
from dashscope import Generation
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ChatService:
    """聊天服务类，提供LLM对话、情感检测、人格生成等功能"""
    
    def __init__(self, config: Dict, personality_data: Optional[Dict] = None):
        """
        初始化聊天服务
        
        Args:
            config: 包含API密钥和提示词的配置字典
            personality_data: 可选的人格数据
        """
        self.config = config
        self.personality_data = personality_data or {}
        
        # DashScope API配置
        self.dashscope_api_key = config['dashscope']['api_key']
        
        # 会话管理 - 支持多个用户会话
        self.user_sessions = {}
        
        # 可用的表情类型
        self.available_emotions = list(config['prompts']['expressions'].keys())
        
        logger.info("聊天服务初始化完成")
    
    def _setup_system_prompt(self, personality_data: Optional[Dict] = None) -> str:
        """
        设置系统提示词和人格 - 确保第一次发送时包含完整的角色性格和响应格式要求
        
        Args:
            personality_data: 可选的人格数据
            
        Returns:
            完整的系统提示词
        """
        base_prompt = self.config['prompts']['chat_system']
        
        if personality_data:
            personality_text = self._format_personality(personality_data)
            system_prompt = base_prompt.format(personality=personality_text)
        else:
            # 如果没有具体人格，使用默认的详细系统提示词
            system_prompt = """你是一个友好、智能的AI助手，具有以下特征：

**角色特征：**
- 性格开朗、乐于助人
- 善于理解用户需求并提供有用的回答
- 具有同理心，能够根据对话内容调整情感状态
- 喜欢与用户进行有趣的对话交流

**响应格式要求：**
1. 请自然地回复用户消息，语言风格要友好亲切
2. 在每个回复的末尾，必须使用 [EMOTION: 情感状态] 标签来表达你当前的情感
3. 可选的情感状态包括：happy（开心）、sad（难过）、surprised（惊讶）
4. 根据对话内容和上下文选择最适合的情感状态
5. 保持对话的连贯性，记住之前的对话内容

**示例回复格式：**
用户："你好！"
助手："你好！很高兴见到你，有什么我可以帮助你的吗？ [EMOTION: happy]"

请严格按照以上要求进行回复。"""
        
        logger.info("系统提示词设置完成")
        return system_prompt
    
    def _format_personality(self, personality_data: Dict) -> str:
        """
        将人格数据格式化为可读文本
        
        Args:
            personality_data: 人格数据字典
            
        Returns:
            格式化后的人格描述文本
        """
        formatted = []
        
        if 'personality' in personality_data and personality_data['personality']:
            formatted.append("**角色人格特征：**")
            for trait in personality_data['personality']:
                formatted.append(f"- {trait}")
        
        if 'habits' in personality_data and personality_data['habits']:
            formatted.append("\n**行为习惯：**")
            for habit in personality_data['habits']:
                formatted.append(f"- {habit}")
        
        if 'voice_tone' in personality_data:
            formatted.append(f"\n**语调风格：** {personality_data['voice_tone']}")
        
        # 添加响应格式要求
        formatted.append(f"\n**响应格式要求：**")
        formatted.append("- 请保持角色一致性，体现上述人格特征")
        formatted.append("- 在每个回复末尾添加 [EMOTION: 状态] 标签")
        formatted.append("- 情感状态选择：happy, sad, surprised")
        formatted.append("- 根据对话内容和角色性格选择合适的情感反应")
        
        return "\n".join(formatted)
    
    def get_or_create_session(self, session_id: Optional[str] = None) -> str:
        """
        获取或创建聊天会话
        
        Args:
            session_id: 可选的会话ID
            
        Returns:
            会话ID
        """
        if session_id and session_id in self.user_sessions:
            return session_id
        
        # 创建新会话
        new_session_id = session_id or str(uuid.uuid4())
        
        # 设置系统提示词
        system_prompt = self._setup_system_prompt(self.personality_data)
        
        # 初始化会话历史
        self.user_sessions[new_session_id] = {
            'chat_history': [
                {"role": "system", "content": system_prompt}
            ],
            'created_at': time.time(),
            'last_activity': time.time()
        }
        
        logger.info(f"创建新聊天会话: {new_session_id}")
        return new_session_id
    
    def process_message(self, message: str, session_id: Optional[str] = None, message_type: str = "text", enable_stream: bool = False) -> Dict:
        """
        处理用户消息并生成AI回复 - 支持多轮对话和流式输出
        
        Args:
            message: 用户消息内容
            session_id: 会话ID
            message_type: 消息类型 ("text" 或 "voice")
            enable_stream: 是否启用流式输出
            
        Returns:
            包含AI回复和情感状态的字典
        """
        try:
            if not message.strip():
                return {
                    "reply": "我没有听清楚，你能再说一遍吗？",
                    "emotion": "thinking",
                    "message_id": str(uuid.uuid4()),
                    "session_id": session_id
                }
            
            # 获取或创建会话
            session_id = self.get_or_create_session(session_id)
            session_data = self.user_sessions[session_id]
            chat_history = session_data['chat_history']
            
            # 添加用户消息到历史
            chat_history.append({
                "role": "user",
                "content": message
            })
            
            # 准备发送给API的消息格式（完全符合DashScope标准）
            messages = [{"role": msg["role"], "content": msg["content"]} for msg in chat_history]
            
            logger.info(f"发送多轮对话消息 (会话: {session_id}), 消息数量: {len(messages)}")
            
            if enable_stream:
                # 流式输出处理
                return self._process_stream_response(messages, session_id, message)
            else:
                # 普通调用处理
                return self._process_normal_response(messages, session_id, message)
                
        except Exception as e:
            logger.error(f"消息处理失败: {e}")
            return {
                "reply": "抱歉，我遇到了一些问题。让我们继续聊天吧！",
                "emotion": "sad",
                "message_id": str(uuid.uuid4()),
                "session_id": session_id,
                "error": str(e)
            }
    
    def _process_normal_response(self, messages: List[Dict], session_id: str, user_message: str) -> Dict:
        """
        处理普通API调用响应
        
        Args:
            messages: 消息历史
            session_id: 会话ID
            user_message: 用户消息
            
        Returns:
            处理结果
        """
        # 调用DashScope Generation API（参考用户提供的示例）
        response = Generation.call(
            api_key=self.dashscope_api_key,
            model="qwen-plus",
            messages=messages,  # type: ignore
            result_format='message'
        )
        
        # 获取AI回复
        if hasattr(response, 'output') and hasattr(response.output, 'choices') and response.output.choices:
            ai_reply = response.output.choices[0].message.content  # type: ignore
            if not isinstance(ai_reply, str):
                ai_reply = str(ai_reply) if ai_reply else "抱歉，我遇到了一些问题，请稍后再试。"
        else:
            logger.error("消息处理API调用失败")
            ai_reply = "抱歉，我遇到了一些问题，请稍后再试。"
        
        # 添加AI回复到历史
        session_data = self.user_sessions[session_id]
        session_data['chat_history'].append({
            "role": "assistant", 
            "content": ai_reply
        })
        session_data['last_activity'] = time.time()
        
        # 提取情感状态
        emotion = self._extract_emotion(ai_reply)
        
        # 清理回复文本(移除情感标签)
        clean_reply = self._clean_reply_text(ai_reply)
        
        # 限制聊天历史长度
        self._trim_chat_history(session_id)
        
        result = {
            "reply": clean_reply,
            "emotion": emotion,
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "timestamp": int(time.time()),
            "full_reply": ai_reply  # 包含情感标签的完整回复
        }
        
        logger.info(f"消息处理完成 (会话: {session_id}) - 情感: {emotion}, 回复长度: {len(clean_reply)}")
        return result
    
    def _process_stream_response(self, messages: List[Dict], session_id: str, user_message: str) -> Dict:
        """
        处理流式API调用响应 - 参考用户提供的流式输出示例
        
        Args:
            messages: 消息历史
            session_id: 会话ID
            user_message: 用户消息
            
        Returns:
            处理结果（包含生成器）
        """
        try:
            # 调用DashScope流式API（参考用户提供的示例）
            responses = Generation.call(
                api_key=self.dashscope_api_key,
                model="qwen-plus",
                messages=messages,
                result_format='message',
                stream=True,
                incremental_output=True
            )
            
            # 流式内容收集
            def stream_generator():
                full_content = ""
                for response in responses:
                    if hasattr(response, 'output') and response.output.choices:
                        content = response.output.choices[0].message.content
                        if content:
                            full_content += content
                            yield content
                
                # 流式输出完成后，处理完整内容
                if full_content:
                    # 添加AI回复到历史
                    session_data = self.user_sessions[session_id]
                    session_data['chat_history'].append({
                        "role": "assistant", 
                        "content": full_content
                    })
                    session_data['last_activity'] = time.time()
                    
                    # 限制聊天历史长度
                    self._trim_chat_history(session_id)
            
            result = {
                "reply": "",  # 流式输出时回复为空
                "emotion": "thinking",  # 初始情感状态
                "message_id": str(uuid.uuid4()),
                "session_id": session_id,
                "timestamp": int(time.time()),
                "stream": True,
                "stream_generator": stream_generator()
            }
            
            logger.info(f"开始流式输出处理 (会话: {session_id})")
            return result
            
        except Exception as e:
            logger.error(f"流式输出处理失败: {e}")
            # 降级到普通调用
            return self._process_normal_response(messages, session_id, user_message)
    
    def generate_personality(self, avatar_image_path: str, image_uuid: str) -> Dict:
        """
        基于头像图像生成AI人格特征
        
        Args:
            avatar_image_path: 头像图像路径
            image_uuid: 图像UUID
            
        Returns:
            包含人格数据的字典
        """
        try:
            # 使用简化的文本模式生成人格
            personality_prompt = self.config['prompts']['personality_generation']
            
            # 构建消息（纯文本模式）
            messages = [
                {
                    'role': 'system', 
                    'content': '你是一个专业的AI人格分析专家。你需要为虚拟角色生成详细的人格特征，确保返回的内容是有效的JSON格式。'
                },
                {
                    'role': 'user', 
                    'content': f'''请基于以下要求生成一个AI助手的人格特征：

{personality_prompt}

请严格按照以下JSON格式返回结果，不要添加任何其他文字说明：

{{
    "personality": ["性格特征1", "性格特征2", "性格特征3", "性格特征4"],
    "habits": ["行为习惯1", "行为习惯2", "行为习惯3"],
    "voice_tone": "语调风格"
}}

要求：
1. personality字段：包含3-5个积极的性格特征
2. habits字段：包含2-3个有趣的行为习惯 
3. voice_tone字段：使用一个词描述语调（如：温和、活泼、幽默等）
4. 确保所有内容都适合友好的AI助手角色
5. 只返回JSON对象，不要添加任何解释文字'''
                }
            ]
            
            # 调用DashScope API生成人格（使用文本模型）
            response = Generation.call(
                api_key=self.dashscope_api_key,
                model="qwen-plus",  # 使用文本模型而不是视觉模型
                messages=messages,
                result_format='message'
            )
            
            if hasattr(response, 'output') and hasattr(response.output, 'choices') and response.output.choices:
                ai_response = response.output.choices[0].message.content
                
                # 解析JSON响应
                try:
                    personality_data = json.loads(ai_response)
                    validated_data = self._validate_personality_data(personality_data)
                    
                    # 为指定会话更新人格数据
                    if image_uuid:
                        self.update_personality_for_session(image_uuid, validated_data)
                    
                    logger.info(f"人格生成成功 (会话: {image_uuid})")
                    return {
                            "personality_data": validated_data,
                            "session_id": image_uuid,
                            "timestamp": int(time.time())
                        }
                    
                except json.JSONDecodeError as e:
                    logger.error(f"人格数据JSON解析失败: {e}")
                    return {"error": f"人格数据解析失败: {str(e)}"}
            else:
                logger.error("人格生成API调用失败 - 无法获取响应")
                return {"error": "人格生成API调用失败"}
                
        except Exception as e:
            logger.error(f"人格生成失败: {e}")
            return {"error": str(e)}
    
    def update_personality_for_session(self, session_id: str, personality_data: Dict):
        """
        为指定会话更新人格数据并重新设置系统提示词
        
        Args:
            session_id: 会话ID
            personality_data: 新的人格数据
        """
        try:
            # 确保会话存在
            if session_id not in self.user_sessions:
                session_id = self.get_or_create_session(session_id)
            
            # 更新系统提示词
            new_system_prompt = self._setup_system_prompt(personality_data)
            
            # 更新会话的第一条消息（系统提示词）
            session_data = self.user_sessions[session_id]
            if session_data['chat_history'] and session_data['chat_history'][0]['role'] == 'system':
                session_data['chat_history'][0]['content'] = new_system_prompt
            else:
                session_data['chat_history'].insert(0, {"role": "system", "content": new_system_prompt})
            
            logger.info(f"会话 {session_id} 的人格数据已更新")
        except Exception as e:
            logger.error(f"更新会话人格数据失败: {e}")
    
    def _validate_personality_data(self, data: Dict) -> Dict:
        """
        验证和标准化人格数据
        
        Args:
            data: 原始人格数据
            
        Returns:
            验证后的人格数据
        """
        validated = {
            "personality": [],
            "habits": [],
            "voice_tone": "friendly"
        }
        
        if isinstance(data, dict):
            if "personality" in data and isinstance(data["personality"], list):
                validated["personality"] = [str(trait) for trait in data["personality"][:5]]  # 最多5个特征
            
            if "habits" in data and isinstance(data["habits"], list):
                validated["habits"] = [str(habit) for habit in data["habits"][:3]]  # 最多3个习惯
            
            if "voice_tone" in data and isinstance(data["voice_tone"], str):
                validated["voice_tone"] = str(data["voice_tone"])
        
        return validated
    
    def _extract_emotion(self, ai_reply: str) -> str:
        """
        从AI回复中提取情感状态
        
        Args:
            ai_reply: AI的原始回复
            
        Returns:
            提取的情感状态
        """
        # 查找[EMOTION: xxx]格式的情感标签
        emotion_pattern = r'\[EMOTION:\s*(\w+)\]'
        emotion_match = re.search(emotion_pattern, ai_reply, re.IGNORECASE)
        
        if emotion_match:
            detected_emotion = emotion_match.group(1).lower()
            # 检查是否是有效的情感类型
            if detected_emotion in self.available_emotions:
                return detected_emotion
        
        # 如果没有找到有效的情感标签，使用情感关键词检测
        return self._detect_emotion_by_keywords(ai_reply)
    
    def _detect_emotion_by_keywords(self, text: str) -> str:
        """
        通过关键词检测情感状态
        
        Args:
            text: 要分析的文本
            
        Returns:
            检测到的情感状态
        """
        text_lower = text.lower()
        
        # 情感关键词映射
        emotion_keywords = {
            'happy': ['开心', '高兴', '快乐', '兴奋', '愉快', '😊', '哈哈', '太好了', '棒'],
            'sad': ['难过', '伤心', '沮丧', '失望', '悲伤', '😢', '遗憾', '可惜'],
            'surprised': ['惊讶', '震惊', '意外', '没想到', '哇', '天哪', '😲', '不敢相信'],
            # 'angry': ['生气', '愤怒', '恼火', '讨厌', '烦人', '😠', '气死了'],
            # 'thinking': ['想想', '思考', '考虑', '分析', '研究', '🤔', '让我想想', '嗯'],
            # 'excited': ['兴奋', '激动', '太棒了', '厉害', '精彩', '🎉', '耶']
        }
        
        for emotion, keywords in emotion_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return emotion
        
        return 'happy'  # 默认情感
    
    def _clean_reply_text(self, ai_reply: str) -> str:
        """
        清理AI回复文本，移除情感标签
        
        Args:
            ai_reply: 原始AI回复
            
        Returns:
            清理后的回复文本
        """
        # 移除[EMOTION: xxx]标签
        emotion_pattern = r'\[EMOTION:\s*\w+\]'
        cleaned = re.sub(emotion_pattern, '', ai_reply, flags=re.IGNORECASE)
        return cleaned.strip()
    
    def _trim_chat_history(self, session_id: str, max_messages: int = 20):
        """
        限制聊天历史长度，保留系统提示词
        
        Args:
            session_id: 会话ID
            max_messages: 最大消息数量
        """
        if session_id not in self.user_sessions:
            return
        
        chat_history = self.user_sessions[session_id]['chat_history']
        
        if len(chat_history) > max_messages:
            # 保留系统提示词和最近的消息
            system_message = chat_history[0] if chat_history and chat_history[0]['role'] == 'system' else None
            recent_messages = chat_history[-(max_messages-1):]
            
            if system_message:
                self.user_sessions[session_id]['chat_history'] = [system_message] + recent_messages
            else:
                self.user_sessions[session_id]['chat_history'] = recent_messages
    
    def select_expression_video(self, emotion: str, image_uuid: str) -> Optional[str]:
        """
        根据情感选择对应的表情视频
        
        Args:
            emotion: 情感状态
            image_uuid: 图像UUID
            
        Returns:
            表情视频文件路径，如果没有找到返回None
        """
        try:
            if emotion not in self.available_emotions:
                emotion = "happy"  # 默认表情
            
            # 构建视频文件路径，使用image_uuid
            video_filename = f"{image_uuid}_{emotion}.mp4"
            
            # 检查generated目录
            video_path = Path("generated/expressions") / video_filename
            if video_path.exists():
                return str(video_path)
            
            # 检查static目录
            static_video_path = Path("static/expressions") / video_filename
            if static_video_path.exists():
                return str(static_video_path)
            
            logger.warning(f"未找到表情视频: {video_filename}")
            
            # 尝试查找通用表情视频（不带image_uuid的默认视频）
            generic_video_filename = f"default_{emotion}.mp4"
            generic_video_path = Path("static/expressions") / generic_video_filename
            if generic_video_path.exists():
                logger.info(f"使用通用表情视频: {generic_video_filename}")
                return str(generic_video_path)
            
            # 如果都没有找到，返回None（前端可以显示静态头像）
            return None
            
        except Exception as e:
            logger.error(f"表情视频选择失败: {e}")
            return None
    
    def get_chat_history(self, session_id: Optional[str] = None, include_system: bool = False) -> List[Dict]:
        """
        获取聊天历史
        
        Args:
            session_id: 会话ID
            include_system: 是否包含系统消息
            
        Returns:
            聊天历史列表
        """
        if not session_id or session_id not in self.user_sessions:
            return []
        
        chat_history = self.user_sessions[session_id]['chat_history']
        
        if include_system:
            return chat_history.copy()
        else:
            # 排除系统消息
            return [msg for msg in chat_history if msg["role"] != "system"]
    
    def clear_chat_history(self, session_id: Optional[str] = None):
        """
        清空聊天历史，保留系统提示词
        
        Args:
            session_id: 会话ID，如果为None则清空所有会话
        """
        if session_id and session_id in self.user_sessions:
            # 清空指定会话
            chat_history = self.user_sessions[session_id]['chat_history']
            if chat_history and chat_history[0]["role"] == "system":
                system_message = chat_history[0]
                self.user_sessions[session_id]['chat_history'] = [system_message]
            else:
                self.user_sessions[session_id]['chat_history'] = []
                # 重新设置系统提示词
                session_id = self.get_or_create_session(session_id)
            
            logger.info(f"会话 {session_id} 聊天历史已清空")
        elif session_id is None:
            # 清空所有会话
            self.user_sessions.clear()
            logger.info("所有聊天历史已清空")
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        获取会话信息
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话信息或None
        """
        if session_id in self.user_sessions:
            session_data = self.user_sessions[session_id]
            return {
                "session_id": session_id,
                "created_at": session_data['created_at'],
                "last_activity": session_data['last_activity'],
                "message_count": len(session_data['chat_history']) - 1,  # 减去系统消息
                "active": time.time() - session_data['last_activity'] < 3600  # 1小时内活跃
            }
        return None
    
    def cleanup_expired_sessions(self, max_age_hours: int = 24):
        """
        清理过期的会话
        
        Args:
            max_age_hours: 最大会话年龄（小时）
        """
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        expired_sessions = []
        
        for session_id, session_data in self.user_sessions.items():
            if current_time - session_data['last_activity'] > max_age_seconds:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.user_sessions[session_id]
            logger.info(f"清理过期会话: {session_id}")
        
        if expired_sessions:
            logger.info(f"清理了 {len(expired_sessions)} 个过期会话")

    # 保持向后兼容性的方法
    def update_personality(self, new_personality_data: Dict):
        """
        更新人格数据（向后兼容方法）
        
        Args:
            new_personality_data: 新的人格数据
        """
        try:
            validated_data = self._validate_personality_data(new_personality_data)
            self.personality_data = validated_data
            logger.info("全局人格数据已更新")
        except Exception as e:
            logger.error(f"更新人格数据失败: {e}")
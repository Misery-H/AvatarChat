#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音处理服务 - 使用DashScope实时语音识别API和CosyVoice语音合成
集成最新的阿里云语音识别、CosyVoice语音合成等功能
"""

import json
import time
import threading
import uuid
import os
import signal
import queue
import wave
import io
from pathlib import Path
from typing import Dict, Optional, Callable
import logging

import dashscope
import pyaudio
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback, AudioFormat

logger = logging.getLogger(__name__)

class TextToSpeechCallback(ResultCallback):
    """语音合成回调处理类 - 修复WAV格式问题"""
    
    def __init__(self, audio_file_path: str, enable_playback: bool = False):
        """
        初始化语音合成回调
        
        Args:
            audio_file_path: 音频文件保存路径
            enable_playback: 是否启用实时播放
        """
        self.audio_file_path = audio_file_path
        self.enable_playback = enable_playback
        self.audio_file = None
        self.wav_file = None
        self.player = None
        self.stream = None
        self.synthesis_complete = False
        self.error_message = None
        self.audio_data_buffer = io.BytesIO()  # 用于缓存音频数据
        self.total_frames = 0
        
    def on_open(self):
        """连接建立时的回调"""
        try:
            logger.info(f"语音合成连接已建立，保存到: {self.audio_file_path}")
            
            # 确保目录存在
            Path(self.audio_file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 初始化WAV文件写入器
            self.wav_file = wave.open(self.audio_file_path, 'wb')
            self.wav_file.setnchannels(1)  # 单声道
            self.wav_file.setsampwidth(2)  # 16位
            self.wav_file.setframerate(22050)  # 22050Hz采样率
            
            # 如果启用实时播放，初始化播放设备
            if self.enable_playback:
                self.player = pyaudio.PyAudio()
                self.stream = self.player.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=22050,
                    output=True
                )
                logger.info("音频播放设备已初始化")
        except Exception as e:
            logger.error(f"语音合成初始化失败: {e}")
            self.error_message = str(e)

    def on_complete(self):
        """语音合成完成回调"""
        logger.info("语音合成完成，所有音频数据已接收")
        self.synthesis_complete = True

    def on_error(self, message: str):
        """语音合成错误回调"""
        logger.error(f"语音合成出现异常：{message}")
        self.error_message = message
        self.synthesis_complete = True

    def on_close(self):
        """连接关闭回调"""
        logger.info("语音合成连接已关闭")
        
        # 关闭WAV文件
        if self.wav_file:
            try:
                self.wav_file.close()
                logger.info(f"WAV文件已保存: {self.audio_file_path}, 总帧数: {self.total_frames}")
                
                # 验证WAV文件格式
                self._verify_wav_file()
            except Exception as e:
                logger.error(f"关闭WAV文件失败: {e}")
            finally:
                self.wav_file = None
            
        # 停止播放器
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.player:
            self.player.terminate()
            
        self.synthesis_complete = True

    def on_event(self, message):
        """事件回调"""
        pass

    def on_data(self, data: bytes) -> None:
        """音频数据回调 - 修复格式处理"""
        try:
            if not data:
                return
                
            # 写入WAV文件
            if self.wav_file:
                self.wav_file.writeframes(data)
                self.total_frames += len(data) // 2  # 16位音频，每2字节一帧
                
            # 实时播放
            if self.enable_playback and self.stream:
                self.stream.write(data)
                
            logger.debug(f"接收音频数据: {len(data)} 字节")
        except Exception as e:
            logger.error(f"处理音频数据失败: {e}")
            self.error_message = str(e)
            
    def _verify_wav_file(self):
        """验证生成的WAV文件格式"""
        try:
            if not Path(self.audio_file_path).exists():
                raise Exception("WAV文件不存在")
                
            file_size = Path(self.audio_file_path).stat().st_size
            if file_size < 44:  # WAV文件最小44字节头部
                raise Exception(f"WAV文件太小: {file_size} 字节")
                
            # 检查WAV文件头
            with open(self.audio_file_path, 'rb') as f:
                header = f.read(12)
                if header[:4] != b'RIFF':
                    raise Exception("WAV文件缺少RIFF头")
                if header[8:12] != b'WAVE':
                    raise Exception("WAV文件缺少WAVE标识")
                    
            # 尝试用wave库读取
            with wave.open(self.audio_file_path, 'rb') as wav:
                channels = wav.getnchannels()
                width = wav.getsampwidth()
                rate = wav.getframerate()
                frames = wav.getnframes()
                duration = frames / rate if rate > 0 else 0
                
                logger.info(f"WAV文件验证成功: {channels}ch, {width*8}bit, {rate}Hz, {duration:.2f}s, {file_size} bytes")
                
                if channels != 1 or width != 2 or rate != 22050:
                    logger.warning(f"WAV格式非标准: {channels}ch, {width*8}bit, {rate}Hz")
                    
        except Exception as e:
            logger.error(f"WAV文件验证失败: {e}")
            # 如果验证失败，尝试创建一个占位符文件
            self._create_fallback_wav()
            
    def _create_fallback_wav(self):
        """创建占位符WAV文件"""
        try:
            import numpy as np
            
            logger.info("创建占位符WAV文件")
            
            # 生成1秒静音
            sample_rate = 22050
            duration = 1.0
            frames = int(sample_rate * duration)
            silence = np.zeros(frames, dtype=np.int16)
            
            with wave.open(self.audio_file_path, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(silence.tobytes())
                
            logger.info(f"占位符WAV文件已创建: {self.audio_file_path}")
            
        except Exception as e:
            logger.error(f"创建占位符WAV失败: {e}")

class VoiceRecognitionCallback(RecognitionCallback):
    """语音识别回调处理类"""
    
    def __init__(self, session_id: str, result_queue: queue.Queue):
        """
        初始化回调处理器
        
        Args:
            session_id: 录音会话ID
            result_queue: 结果队列
        """
        self.session_id = session_id
        self.result_queue = result_queue
        self.final_text = ""
        self.partial_text = ""
        self.mic = None
        self.stream = None
        self.is_open = False
        
    def on_open(self) -> None:
        """连接打开时的回调"""
        try:
            logger.info(f"语音识别连接已建立: {self.session_id}")
            self.mic = pyaudio.PyAudio()
            self.stream = self.mic.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=3200
            )
            self.is_open = True
            
            # 通知连接已建立
            self.result_queue.put({
                'type': 'connection',
                'status': 'open',
                'session_id': self.session_id
            })
        except Exception as e:
            logger.error(f"音频设备初始化失败: {e}")
            self.result_queue.put({
                'type': 'error',
                'message': f'音频设备初始化失败: {str(e)}',
                'session_id': self.session_id
            })

    def on_close(self) -> None:
        """连接关闭时的回调"""
        logger.info(f"语音识别连接已关闭: {self.session_id}")
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
            self.stream = None
            
        if self.mic:
            try:
                self.mic.terminate()
            except:
                pass
            self.mic = None
            
        self.is_open = False
        
        # 通知连接已关闭
        self.result_queue.put({
            'type': 'connection',
            'status': 'closed',
            'session_id': self.session_id,
            'final_text': self.final_text
        })

    def on_error(self, result: RecognitionResult) -> None:
        """识别错误回调"""
        error_message = result.get_sentence()
        logger.error(f"语音识别错误: {error_message}")
        self.result_queue.put({
            'type': 'error',
            'message': str(error_message),
            'session_id': self.session_id
        })

    def on_event(self, result: RecognitionResult) -> None:
        """识别结果事件回调"""
        try:
            sentence = result.get_sentence()
            
            # 确保sentence是字典类型且包含text字段
            if isinstance(sentence, dict) and 'text' in sentence and sentence['text'].strip():
                text = sentence['text'].strip()
                
                if RecognitionResult.is_sentence_end(sentence):
                    # 完整句子识别完成
                    self.final_text = text
                    logger.info(f"识别到完整句子: {text}")
                    self.result_queue.put({
                        'type': 'final_result',
                        'text': text,
                        'session_id': self.session_id,
                        'request_id': result.get_request_id(),
                        'usage': result.get_usage(sentence)
                    })
                else:
                    # 部分识别结果
                    self.partial_text = text
                    self.result_queue.put({
                        'type': 'partial_result',
                        'text': text,
                        'session_id': self.session_id
                    })
        except Exception as e:
            logger.error(f"处理识别结果时出错: {e}")

class VoiceService:
    """语音处理服务类，提供语音识别、语音合成、录音管理等功能"""
    
    def __init__(self, config: Dict):
        """
        初始化语音服务
        
        Args:
            config: 包含API密钥的配置字典
        """
        self.config = config
        
        # 设置DashScope API Key
        api_key = config.get('dashscope', {}).get('api_key')
        if api_key:
            dashscope.api_key = api_key
        else:
            logger.warning("DashScope API密钥未配置")
        
        # 创建音频文件目录
        self.audio_dir = Path("generated/audio")
        self.static_audio_dir = Path("static/audio")
        self.temp_audio_dir = Path("temp/audio")
        
        for dir_path in [self.audio_dir, self.static_audio_dir, self.temp_audio_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # 语音服务配置
        self.active_sessions = {}
        self.recognition_sessions = {}
        
        logger.info("DashScope语音服务初始化完成")
    
    def start_recording_session(self, session_id: Optional[str] = None) -> str:
        """
        开始新的录音会话 - 使用DashScope实时语音识别
        
        Args:
            session_id: 可选的会话ID，如果不提供则自动生成
            
        Returns:
            会话ID
        """
        if not session_id:
            session_id = str(uuid.uuid4())
        
        try:
            # 创建结果队列
            result_queue = queue.Queue()
            
            # 创建回调处理器
            callback = VoiceRecognitionCallback(session_id, result_queue)
            
            # 创建Recognition实例
            recognition = Recognition(
                model='paraformer-realtime-v2',  # 使用最新的多语种模型
                format='pcm',
                sample_rate=16000,
                semantic_punctuation_enabled=False,  # 关闭语义断句以支持情感识别
                language_hints=['zh', 'en'],  # 支持中英文
                callback=callback
            )
            
            # 启动识别
            recognition.start()
            
            # 创建会话记录
            session_data = {
                'session_id': session_id,
                'status': 'recording',
                'start_time': time.time(),
                'recognition': recognition,
                'callback': callback,
                'result_queue': result_queue,
                'final_text': '',
                'error': None
            }
            
            self.active_sessions[session_id] = session_data
            self.recognition_sessions[session_id] = session_data
            
            # 启动音频流处理线程
            self._start_audio_streaming(session_id)
            
            logger.info(f"开始DashScope录音会话: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"启动录音会话失败: {e}")
            raise Exception(f"启动录音会话失败: {str(e)}")
    
    def _start_audio_streaming(self, session_id: str):
        """启动音频流处理线程"""
        def audio_stream_worker():
            session_data = self.active_sessions[session_id]
            recognition = session_data['recognition']
            callback = session_data['callback']
            
            try:
                # 等待连接建立
                timeout = 10  # 10秒超时
                start_time = time.time()
                
                while not callback.is_open and (time.time() - start_time) < timeout:
                    time.sleep(0.1)
                
                if not callback.is_open:
                    raise Exception("音频连接建立超时")
                
                # 开始音频流传输
                while callback.is_open and session_data.get('status') == 'recording':
                    try:
                        if callback.stream:
                            data = callback.stream.read(3200, exception_on_overflow=False)
                            recognition.send_audio_frame(data)
                        time.sleep(0.01)  # 短暂休眠避免CPU占用过高
                    except Exception as e:
                        logger.error(f"音频流传输错误: {e}")
                        break
                        
            except Exception as e:
                logger.error(f"音频流处理线程错误: {e}")
                session_data['error'] = str(e)
        
        # 启动线程
        thread = threading.Thread(target=audio_stream_worker, daemon=True)
        thread.start()
    
    def stop_recording_session(self, session_id: str) -> Dict:
        """
        停止录音会话并获取识别结果
        
        Args:
            session_id: 会话ID
            
        Returns:
            识别结果字典
        """
        try:
            if session_id not in self.active_sessions:
                return {"error": "会话不存在", "text": "", "session_id": session_id}
            
            session_data = self.active_sessions[session_id]
            
            # 更新会话状态
            session_data['status'] = 'stopping'
            
            # 停止识别
            recognition = session_data['recognition']
            callback = session_data['callback']
            result_queue = session_data['result_queue']
            
            recognition.stop()
            
            # 等待识别结果
            final_text = ""
            timeout = 10  # 10秒超时
            start_wait = time.time()
            
            while time.time() - start_wait < timeout:
                try:
                    result = result_queue.get(timeout=1)
                    if result['type'] == 'final_result':
                        final_text = result['text']
                        break
                    elif result['type'] == 'connection' and result['status'] == 'closed':
                        final_text = result.get('final_text', callback.final_text)
                        break
                except queue.Empty:
                    continue
            
            # 如果没有获取到最终结果，使用回调中的最后文本
            if not final_text:
                final_text = callback.final_text
            
            # 清理会话
            del self.active_sessions[session_id]
            if session_id in self.recognition_sessions:
                del self.recognition_sessions[session_id]
            
            logger.info(f"录音会话结束: {session_id}, 识别结果: {final_text}")
            
            return {
                "text": final_text,
                "session_id": session_id,
                "duration": time.time() - session_data['start_time'],
                "error": session_data.get('error')
            }
            
        except Exception as e:
            logger.error(f"停止录音会话失败: {e}")
            return {"error": str(e), "text": "", "session_id": session_id}
    
    def text_to_speech(self, text: str, session_id: str, voice_config: Optional[Dict] = None) -> str:
        """
        将文本转换为语音 - 使用DashScope CosyVoice API
        
        Args:
            text: 要转换的文本
            session_id: 会话ID
            voice_config: 语音配置参数
            
        Returns:
            生成的音频文件路径
        """
        try:
            if not text.strip():
                raise ValueError("文本内容不能为空")
            
            # 默认语音配置
            config = {
                "voice": "longxiaochun_v2",  # 使用CosyVoice v2音色
                "model": "cosyvoice-v2",
                "format": "wav"
            }
            
            if voice_config:
                config.update(voice_config)
            
            # 生成音频文件名和路径
            audio_filename = f"{session_id}_tts_{int(time.time())}.wav"
            audio_path = self.audio_dir / audio_filename
            static_audio_path = self.static_audio_dir / audio_filename
            
            logger.info(f"开始语音合成: {text[:50]}...")
            start_time = time.time()
            
            # 创建语音合成回调
            callback = TextToSpeechCallback(str(audio_path), enable_playback=False)
            
            # 实例化SpeechSynthesizer
            synthesizer = SpeechSynthesizer(
                model=config["model"],
                voice=config["voice"],
                format=AudioFormat.PCM_22050HZ_MONO_16BIT,
                callback=callback
            )
            
            # 将文本分片进行流式合成（每片不超过2000字符）
            text_chunks = self._split_text_for_synthesis(text, max_chunk_size=2000)
            
            # 逐步发送文本片段
            for chunk in text_chunks:
                if chunk.strip():
                    synthesizer.streaming_call(chunk)
                    time.sleep(0.05)  # 短暂延迟
            
            # 结束流式语音合成（必须调用，否则可能导致结尾部分文本无法转换）
            synthesizer.streaming_complete()
            
            # 等待合成完成
            timeout = 30  # 30秒超时
            wait_start = time.time()
            while not callback.synthesis_complete and (time.time() - wait_start) < timeout:
                time.sleep(0.1)
            
            if callback.error_message:
                raise Exception(f"语音合成失败: {callback.error_message}")
            
            if not callback.synthesis_complete:
                raise Exception("语音合成超时")
            
            # 检查音频文件是否成功生成
            if not audio_path.exists() or audio_path.stat().st_size == 0:
                raise Exception("音频文件生成失败")
            
            # 复制到静态文件目录
            import shutil
            shutil.copy2(audio_path, static_audio_path)
            
            synthesis_time = time.time() - start_time
            file_size = audio_path.stat().st_size
            
            logger.info(f"语音合成完成: {audio_path}, 耗时: {synthesis_time:.2f}秒, 大小: {file_size} 字节")
            logger.info(f"RequestID: {synthesizer.get_last_request_id()}, 首包延迟: {synthesizer.get_first_package_delay()}毫秒")
            
            return str(audio_path)
                
        except Exception as e:
            logger.error(f"文本转语音失败: {e}")
            # 如果语音合成失败，创建一个简短的占位符音频
            try:
                fallback_path = self._create_fallback_audio(str(audio_path), text)
                logger.info(f"已创建占位符音频: {fallback_path}")
                return fallback_path
            except:
                raise Exception(f"语音合成失败且无法创建占位符: {str(e)}")

    def _split_text_for_synthesis(self, text: str, max_chunk_size: int = 2000) -> list:
        """
        将文本分片以满足语音合成API的长度限制
        
        Args:
            text: 原始文本
            max_chunk_size: 每片最大字符数
            
        Returns:
            文本片段列表
        """
        if len(text) <= max_chunk_size:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # 优先按句号分割
        sentences = text.replace('。', '。\n').replace('！', '！\n').replace('？', '？\n').split('\n')
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # 如果当前片段加上新句子仍在限制内
            if len(current_chunk) + len(sentence) <= max_chunk_size:
                current_chunk += sentence
            else:
                # 保存当前片段，开始新片段
                if current_chunk:
                    chunks.append(current_chunk)
                
                # 如果单个句子超过限制，需要进一步分割
                if len(sentence) > max_chunk_size:
                    for i in range(0, len(sentence), max_chunk_size):
                        chunks.append(sentence[i:i + max_chunk_size])
                    current_chunk = ""
                else:
                    current_chunk = sentence
        
        # 添加最后一个片段
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    def _create_fallback_audio(self, file_path: str, text: str) -> str:
        """
        创建占位符音频文件（当真实语音合成失败时使用）
        
        Args:
            file_path: 音频文件路径
            text: 原始文本（用于计算音频长度）
            
        Returns:
            音频文件路径
        """
        try:
            import wave
            import numpy as np
            
            # 根据文本长度计算音频时长（每个字符约0.15秒）
            duration = max(1.0, len(text) * 0.15)
            sample_rate = 22050
            frames = int(sample_rate * duration)
            
            # 生成简单的蜂鸣音提示
            frequency = 800  # 较高的频率作为提示音
            audio_data = np.sin(2 * np.pi * frequency * np.linspace(0, duration, frames))
            
            # 添加淡入淡出效果
            fade_frames = min(frames // 10, 1000)
            audio_data[:fade_frames] *= np.linspace(0, 1, fade_frames)
            audio_data[-fade_frames:] *= np.linspace(1, 0, fade_frames)
            
            audio_data = (audio_data * 32767 * 0.3).astype(np.int16)  # 适中音量
            
            with wave.open(file_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16位
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data.tobytes())
                
            return file_path
                
        except Exception as e:
            logger.error(f"创建占位符音频失败: {e}")
            raise
    
    def get_session_status(self, session_id: str) -> Dict:
        """
        获取录音会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话状态信息
        """
        if session_id not in self.active_sessions:
            return {"error": "会话不存在", "session_id": session_id}
        
        session_data = self.active_sessions[session_id]
        return {
            "session_id": session_id,
            "status": session_data['status'],
            "duration": time.time() - session_data['start_time'],
            "error": session_data.get('error')
        }
    
    def cleanup_expired_sessions(self, max_age_seconds: int = 300):
        """
        清理过期的会话（超过5分钟）
        
        Args:
            max_age_seconds: 最大会话年龄（秒）
        """
        current_time = time.time()
        expired_sessions = []
        
        for session_id, session_data in self.active_sessions.items():
            if current_time - session_data['start_time'] > max_age_seconds:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            try:
                self.stop_recording_session(session_id)
                logger.info(f"清理过期会话: {session_id}")
            except Exception as e:
                logger.error(f"清理会话失败: {e}")
    
    def cleanup_session(self, session_id: str):
        """
        清理指定会话的数据和相关文件
        
        Args:
            session_id: 要清理的会话ID
        """
        try:
            # 停止录音会话（如果正在进行）
            if session_id in self.active_sessions:
                try:
                    self.stop_recording_session(session_id)
                except Exception as e:
                    logger.warning(f"停止录音会话失败: {e}")
            
            # 清理音频文件
            self._cleanup_session_files(session_id)
            
            logger.info(f"会话清理完成: {session_id}")
            
        except Exception as e:
            logger.error(f"清理会话 {session_id} 失败: {e}")
    
    def _cleanup_session_files(self, session_id: str):
        """
        清理会话相关的音频文件
        
        Args:
            session_id: 会话ID
        """
        import glob
        
        # 清理各个目录中的会话相关文件
        directories = [self.audio_dir, self.static_audio_dir, self.temp_audio_dir]
        
        for directory in directories:
            # 查找包含session_id的文件
            pattern = str(directory / f"*{session_id}*")
            session_files = glob.glob(pattern)
            
            for file_path in session_files:
                try:
                    os.remove(file_path)
                    logger.debug(f"删除文件: {file_path}")
                except Exception as e:
                    logger.warning(f"删除文件失败 {file_path}: {e}")
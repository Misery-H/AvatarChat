#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图像处理服务
集成阿里云图像分割、图像重绘、图像转视频等API
"""

import os
import io
import json
import base64
import requests
import time
import uuid
from pathlib import Path
from PIL import Image, ImageOps
from typing import List, Dict, Optional, Union
from urllib.request import urlopen
from alibabacloud_imageseg20191230.client import Client as ImageSegClient
from alibabacloud_imageseg20191230.models import SegmentCommonImageAdvanceRequest
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions
from http import HTTPStatus
from dashscope import ImageSynthesis, VideoSynthesis
import logging

logger = logging.getLogger(__name__)

class ImageProcessingService:
    """图像处理服务类，提供图像分割、卡通化、表情生成等功能"""
    
    def __init__(self, config: Dict):
        """
        初始化图像处理服务
        
        Args:
            config: 包含API密钥的配置字典
        """
        self.config = config
        
        # 初始化阿里云图像分割客户端
        self.seg_config = Config(
            access_key_id=config['alibaba_cloud']['access_key_id'],
            access_key_secret=config['alibaba_cloud']['access_key_secret'],
            endpoint='imageseg.cn-shanghai.aliyuncs.com',
            region_id='cn-shanghai'
        )
        self.seg_client = ImageSegClient(self.seg_config)
        
        # DashScope API配置
        self.dashscope_api_key = config['dashscope']['api_key']
        
        # 创建必要的目录
        self.upload_dir = Path("uploads")
        self.temp_dir = Path("temp/processing")
        self.avatars_dir = Path("generated/avatars")
        self.expressions_dir = Path("generated/expressions")
        self.static_avatars_dir = Path("static/avatars")
        self.static_expressions_dir = Path("static/expressions")
        
        for dir_path in [self.upload_dir, self.temp_dir, self.avatars_dir, 
                        self.expressions_dir, self.static_avatars_dir, 
                        self.static_expressions_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def resize_image(self, img_path: Path, max_side: int = 2000) -> Path:
        """
        调整图像大小，保持纵横比
        
        Args:
            img_path: 图像文件路径
            max_side: 最大边长限制
            
        Returns:
            调整后的图像路径
        """
        try:
            img = Image.open(img_path)
            img = ImageOps.exif_transpose(img)
            
            w, h = img.size
            if max(w, h) <= max_side:
                return img_path
            
            # 计算缩放比例
            scale = max_side / max(w, h)
            new_size = (int(w * scale), int(h * scale))
            
            # 使用适当的重采样方法
            img_resized = img.resize(new_size)
            
            # 生成新文件名
            resized_path = self.temp_dir / f"resized_{img_path.name}"
            
            # 保存调整后的图像
            if img_path.suffix.lower() in ['.jpg', '.jpeg']:
                img_resized.save(resized_path, format='JPEG', quality=90, optimize=True)
            else:
                img_resized.save(resized_path, optimize=True)
            logger.info(f"图像已调整大小: {img_path} -> {resized_path}")
            
            return resized_path
            
        except Exception as e:
            logger.error(f"图像大小调整失败: {e}")
            raise
    
    def segment_image(self, image_path: Union[str, Path]) -> str:
        """
        使用阿里云API进行图像主体分割
        
        Args:
            image_path: 输入图像路径
            
        Returns:
            分割后的图像路径
        """
        try:
            image_path = Path(image_path)
            
            # 先调整图像大小
            resized_path = self.resize_image(image_path)
            
            # 创建分割请求
            request = SegmentCommonImageAdvanceRequest()
            
            # 读取图像文件
            with open(resized_path, 'rb') as f:
                request.image_urlobject = f
                
                # 设置运行时选项
                runtime = RuntimeOptions()
                
                # 调用API
                response = self.seg_client.segment_common_image_advance(request, runtime)
                
                if response.body and response.body.data and response.body.data.image_url:
                    # 下载分割后的图像
                    segmented_url = response.body.data.image_url
                    segmented_data = urlopen(segmented_url).read()
                    
                    # 保存分割后的图像
                    segmented_filename = f"segmented_{uuid.uuid4().hex[:8]}_{image_path.name}"
                    segmented_path = self.temp_dir / segmented_filename
                    
                    with open(segmented_path, 'wb') as f:
                        f.write(segmented_data)
                    
                    logger.info(f"图像分割完成: {segmented_path}")
                    return str(segmented_path)
                else:
                    raise Exception("图像分割API返回无效响应")
                    
        except Exception as e:
            logger.error(f"图像分割失败: {e}")
            raise
    
    def generate_cartoon_variations(self, image_path: str, image_uuid: str) -> List[str]:
        """
        生成4个卡通化变体 - 使用异步调用
        
        Args:
            image_path: 分割后的图像路径
            image_uuid: 图像UUID，用于文件命名
            
        Returns:
            生成的卡通化图像路径列表
        """
        try:
            # 获取卡通化提示词
            cartoon_prompts = self.config['prompts']['cartoon_generation']
            
            if len(cartoon_prompts) < 4:
                raise ValueError("需要至少4个卡通化提示词")
            
            generated_paths = []
            
            for i, prompt in enumerate(cartoon_prompts[:4]):
                try:
                    logger.info(f"开始生成卡通变体 {i+1}/{len(cartoon_prompts[:4])}: {prompt}")
                    
                    # 调用异步万象图像编辑API
                    result_path = self._call_wanx_image_edit_async(
                        image_path, prompt, image_uuid, f"variation_{i+1}"
                    )
                    generated_paths.append(result_path)
                    logger.info(f"卡通变体 {i+1} 生成完成: {result_path}")
                    
                    # 添加延迟避免API限流
                    time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"生成卡通变体 {i+1} 失败: {e}")
                    # 生成占位图像
                    placeholder_path = self._create_placeholder_image(
                        image_uuid, f"variation_{i+1}_placeholder"
                    )
                    generated_paths.append(placeholder_path)
            
            logger.info(f"生成了 {len(generated_paths)} 个卡通化变体")
            return generated_paths
                
        except Exception as e:
            logger.error(f"卡通化变体生成失败: {e}")
            raise
    
    def generate_expressions(self, avatar_path: str, image_uuid: str) -> Dict[str, str]:
        """
        为选定的头像生成6种表情动画 - 使用异步调用
        
        Args:
            avatar_path: 选定的头像路径
            image_uuid: 图像UUID，用于文件命名
            
        Returns:
            表情名称到视频文件路径的映射
        """
        try:
            # 获取表情提示词
            expression_prompts = self.config['prompts']['expressions']
            
            expression_videos = {}
            
            for emotion, prompt in expression_prompts.items():
                try:
                    logger.info(f"开始生成表情 {emotion}: {prompt}")
                    
                    # 调用图像转视频API
                    video_path = self._call_image_to_video(
                        avatar_path, prompt, image_uuid, emotion
                    )
                    expression_videos[emotion] = video_path
                    logger.info(f"表情 {emotion} 生成完成: {video_path}")
                    
                    # 添加延迟避免API限流
                    time.sleep(3)
                    
                except Exception as e:
                    logger.error(f"生成表情 {emotion} 失败: {e}")
                    # 创建占位符
                    placeholder_path = self._create_placeholder_video(image_uuid, emotion)
                    expression_videos[emotion] = placeholder_path
            
            logger.info(f"生成了 {len(expression_videos)} 个表情动画")
            return expression_videos
            
        except Exception as e:
            logger.error(f"表情动画生成失败: {e}")
            raise
    
    def _call_wanx_image_edit_async(self, image_path: str, prompt: str, image_uuid: str, 
                                   variation_name: str) -> str:
        """
        异步调用万象图像编辑API进行卡通化
        
        Args:
            image_path: 图像文件路径
            prompt: 生成提示词
            image_uuid: 图像UUID，用于文件命名
            variation_name: 变体名称
            
        Returns:
            生成的图像文件路径
        """
        try:
            logger.info(f"开始异步图像编辑任务: {variation_name}")
            
            # 使用文件路径方式调用异步API
            file_url = f"file://{os.path.abspath(image_path)}"
            
            # 发起异步调用 - 使用正确的参数格式
            rsp = ImageSynthesis.async_call(
                api_key=self.dashscope_api_key,
                model="wanx-v1",
                prompt=f"将这个图像转换为卡通风格: {prompt}",
                ref_image_url=file_url,
                size="1024*1024",
                n=1
            )
            
            # 检查初始响应
            if rsp.status_code != HTTPStatus.OK:
                raise Exception(f"异步调用失败 - 状态码: {rsp.status_code}, 错误: {rsp.code}, 消息: {rsp.message}")
            
            # 获取任务ID
            task_id = rsp.output.task_id
            task_status = rsp.output.task_status
            logger.info(f"异步任务已提交: {task_id}, 初始状态: {task_status}")
            
            # 等待任务完成 - 使用轮询方式检查状态
            max_wait_time = 300  # 5分钟超时
            check_interval = 10  # 每10秒检查一次
            waited_time = 0
            
            while waited_time < max_wait_time:
                # 检查任务状态
                status_rsp = ImageSynthesis.fetch(rsp)
                
                if status_rsp.status_code != HTTPStatus.OK:
                    raise Exception(f"查询任务状态失败 - 状态码: {status_rsp.status_code}")
                
                current_status = status_rsp.output.task_status
                logger.info(f"任务状态: {current_status} (已等待 {waited_time}s)")
                
                if current_status == "SUCCEEDED":
                    # 任务成功完成
                    logger.info("任务执行成功，获取结果...")
                    break
                elif current_status == "FAILED":
                    raise Exception("任务执行失败")
                elif current_status in ["PENDING", "RUNNING"]:
                    # 任务还在进行中，继续等待
                    time.sleep(check_interval)
                    waited_time += check_interval
                else:
                    raise Exception(f"未知任务状态: {current_status}")
            
            if waited_time >= max_wait_time:
                raise Exception("任务超时")
            
            # 获取最终结果
            final_rsp = status_rsp
            
            # 检查结果
            if not hasattr(final_rsp.output, 'results') or not final_rsp.output.results:
                raise Exception("API返回空结果")
            
            image_url = final_rsp.output.results[0].url
            logger.info(f"任务完成，图像URL: {image_url}")
            
            # 下载生成的图像
            image_response = requests.get(image_url, timeout=60)
            if image_response.status_code != 200:
                raise Exception(f"下载生成图像失败: {image_response.status_code}")
            
            # 保存图像文件
            filename = f"{image_uuid}_{variation_name}.png"
            file_path = self.avatars_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(image_response.content)
            
            # 同时保存到静态文件目录
            static_path = self.static_avatars_dir / filename
            with open(static_path, 'wb') as f:
                f.write(image_response.content)
            
            logger.info(f"图像已保存: {file_path}")
            return str(file_path)
                
        except Exception as e:
            logger.error(f"异步图像编辑失败: {e}")
            raise
    
    def _call_image_to_video(self, image_path: str, prompt: str, image_uuid: str, 
                            emotion: str) -> str:
        """
        调用图像转视频API生成表情动画 - 使用正确的VideoSynthesis API
        
        Args:
            image_path: 图像文件路径
            prompt: 动画提示词
            image_uuid: 图像UUID，用于文件命名
            emotion: 表情名称
            
        Returns:
            生成的视频文件路径
        """
        try:
            logger.info(f"开始图像转视频任务: {emotion}")
            
            # 使用文件路径方式调用API
            img_url = f"file://{os.path.abspath(image_path)}"
            
            # 调用VideoSynthesis API - 使用正确的参数格式
            logger.info(f"调用VideoSynthesis API，模型: wanx2.1-i2v-turbo")
            rsp = VideoSynthesis.call(
                api_key=self.dashscope_api_key,
                model='wanx2.1-i2v-turbo',
                prompt=prompt,
                img_url=img_url
            )
            
            # 检查响应
            if rsp.status_code != HTTPStatus.OK:
                raise Exception(f"API调用失败 - 状态码: {rsp.status_code}, 错误: {rsp.code}, 消息: {rsp.message}")
            
            # 检查输出
            if not hasattr(rsp.output, 'video_url') or not rsp.output.video_url:
                raise Exception("API返回空视频URL")
            
            video_url = rsp.output.video_url
            task_id = getattr(rsp.output, 'task_id', 'unknown')
            task_status = getattr(rsp.output, 'task_status', 'SUCCEEDED')
            
            logger.info(f"视频生成成功 - 任务ID: {task_id}, 状态: {task_status}")
            logger.info(f"视频URL: {video_url}")
            
            # 下载生成的视频
            logger.info("开始下载生成的视频...")
            video_response = requests.get(video_url, timeout=120)
            if video_response.status_code != 200:
                raise Exception(f"下载生成视频失败: {video_response.status_code}")
            
            # 保存视频文件
            filename = f"{image_uuid}_{emotion}.mp4"
            file_path = self.expressions_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(video_response.content)
            
            # 同时保存到静态文件目录
            static_path = self.static_expressions_dir / filename
            with open(static_path, 'wb') as f:
                f.write(video_response.content)
            
            file_size = len(video_response.content) / 1024  # KB
            logger.info(f"视频已保存: {file_path} ({file_size:.1f}KB)")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"图像转视频失败: {e}")
            raise
    
    def _create_placeholder_image(self, image_uuid: str, name: str) -> str:
        """创建占位图像"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # 创建简单的占位图像
            img = Image.new('RGB', (512, 512), color='lightgray')
            draw = ImageDraw.Draw(img)
            
            # 添加文本
            text = f"Placeholder\n{name}"
            draw.text((256, 256), text, fill='black', anchor='mm')
            
            filename = f"{image_uuid}_{name}.png"
            file_path = self.avatars_dir / filename
            img.save(file_path)
            
            # 也保存到静态目录
            static_path = self.static_avatars_dir / filename
            img.save(static_path)
            
            return str(file_path)
            
        except Exception as e:
            logger.error(f"创建占位图像失败: {e}")
            return ""
    
    def _create_placeholder_video(self, image_uuid: str, emotion: str) -> str:
        """创建占位视频"""
        try:
            # 返回占位视频路径 (可以是一个静态的占位视频)
            filename = f"{image_uuid}_{emotion}_placeholder.mp4"
            file_path = self.expressions_dir / filename
            
            # 这里可以创建一个简单的静态视频或者返回预设的占位视频
            logger.warning(f"使用占位视频: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"创建占位视频失败: {e}")
            return "" 
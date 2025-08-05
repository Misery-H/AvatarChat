#!/usr/bin/env python3
import shutil
from pathlib import Path

def copy_video_placeholders():
    image_uuid = "cf322739-d529-4767-8070-93d997120e51"
    expressions_dir = Path("generated/expressions")
    static_expressions_dir = Path("static/expressions")
    
    # 现有的视频（作为模板）
    template_video = expressions_dir / f"{image_uuid}_happy.mp4"
    
    # 需要创建的缺失表情
    missing_emotions = ["excited", "thinking", "angry"]
    
    for emotion in missing_emotions:
        target_file = expressions_dir / f"{image_uuid}_{emotion}.mp4"
        static_target = static_expressions_dir / f"{image_uuid}_{emotion}.mp4"
        
        try:
            # 复制到generated目录
            shutil.copy2(template_video, target_file)
            print(f"✅ 创建: {target_file.name}")
            
            # 复制到static目录  
            static_expressions_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_video, static_target)
            print(f"✅ 创建: {static_target}")
            
        except Exception as e:
            print(f"❌ 创建失败 {emotion}: {e}")

if __name__ == "__main__":
    copy_video_placeholders()
    print("占位符视频创建完成") 
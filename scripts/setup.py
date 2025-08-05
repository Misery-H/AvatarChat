#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Avatar Chat 项目初始化脚本
"""

import os
import sys
import json
import shutil
from pathlib import Path

def create_directories():
    """创建项目所需的目录结构"""
    directories = [
        'uploads', 'temp/processing', 'temp/sessions', 'temp/audio',
        'generated/avatars', 'generated/expressions', 'generated/audio', 
        'static/avatars', 'static/expressions', 'static/audio', 'static/images',
        'logs', 'deploy'
    ]
    
    print("📁 创建目录结构...")
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"   ✅ {directory}")
    
    print(f"✨ 共创建 {len(directories)} 个目录")

def setup_config():
    """设置配置文件"""
    print("\n⚙️  配置文件设置...")
    
    # 检查key.json是否存在
    key_file = Path('config/key.json')
    key_example = Path('config/key.json.example')
    
    if not key_file.exists() and key_example.exists():
        print("   📋 复制配置模板...")
        shutil.copy(key_example, key_file)
        print("   ⚠️  请编辑 config/key.json 并填入您的API密钥")
    elif key_file.exists():
        print("   ✅ 配置文件已存在")
    else:
        print("   ❌ 配置文件和模板都不存在")
        return False
    
    return True

def check_dependencies():
    """检查依赖"""
    print("\n📦 检查依赖...")
    
    required_packages = [
        'flask', 'requests', 'pillow', 'alibabacloud-imageseg20191230',
        'openai', 'websockets'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"   ✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"   ❌ {package}")
    
    if missing_packages:
        print(f"\n⚠️  缺少依赖: {', '.join(missing_packages)}")
        print("   请运行: pip install -r requirements.txt")
        return False
    
    print("✨ 所有依赖已安装")
    return True

def test_import():
    """测试核心模块导入"""
    print("\n🧪 测试模块导入...")
    
    modules = [
        ('app', 'Flask应用'),
        ('services.image_service', '图像处理服务'),
        ('services.voice_service', '语音服务'),
        ('services.chat_service', '聊天服务'),
        ('config.config_loader', '配置加载器')
    ]
    
    for module_name, description in modules:
        try:
            __import__(module_name)
            print(f"   ✅ {description}")
        except ImportError as e:
            print(f"   ❌ {description}: {e}")
            return False
    
    print("✨ 所有模块导入成功")
    return True

def generate_sample_data():
    """生成示例数据"""
    print("\n🎨 生成示例数据...")
    
    # 创建示例配置
    sample_config = {
        "test_mode": True,
        "api_timeout": 30,
        "max_file_size": 10485760,
        "supported_formats": ["jpg", "jpeg", "png", "gif"]
    }
    
    with open('config/app_config.json', 'w', encoding='utf-8') as f:
        json.dump(sample_config, f, indent=2, ensure_ascii=False)
    
    print("   ✅ 创建示例应用配置")
    
    # 创建.gitignore补充
    gitignore_content = """
# AI Avatar Chat 特定忽略文件
uploads/*
!uploads/.gitkeep
generated/*
!generated/.gitkeep
temp/*
!temp/.gitkeep
logs/*.log
config/key.json
.DS_Store
*.pyc
__pycache__/
"""
    
    with open('.gitignore.example', 'w') as f:
        f.write(gitignore_content.strip())
    
    print("   ✅ 创建Git忽略文件示例")

def main():
    """主函数"""
    print("🚀 AI Avatar Chat 项目初始化")
    print("=" * 50)
    
    # 检查是否在项目根目录
    if not Path('app.py').exists():
        print("❌ 请在项目根目录运行此脚本")
        sys.exit(1)
    
    try:
        # 创建目录
        create_directories()
        
        # 设置配置
        if not setup_config():
            print("⚠️  配置设置有问题，请手动检查")
        
        # 检查依赖
        deps_ok = check_dependencies()
        
        # 测试导入
        import_ok = test_import() if deps_ok else False
        
        # 生成示例数据
        generate_sample_data()
        
        print("\n" + "=" * 50)
        if deps_ok and import_ok:
            print("✅ 项目初始化完成!")
            print("\n📝 下一步:")
            print("1. 编辑 config/key.json 填入API密钥")
            print("2. 运行: python run.py --mode dev")
            print("3. 访问: http://localhost:5000")
        else:
            print("⚠️  初始化完成，但存在问题")
            print("请解决上述依赖和导入问题后重试")
    
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 
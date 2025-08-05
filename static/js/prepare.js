// 准备阶段页面类
class PreparePage {
    constructor() {
        this.sessionId = null;
        this.selectedAvatarIndex = null;
        this.initElements();
        this.bindEvents();
    }

    initElements() {
        // 主要元素
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadError = document.getElementById('uploadError');
        this.uploadLoading = document.getElementById('uploadLoading');
        
        // 步骤元素
        this.step1 = document.getElementById('step1');
        this.step2 = document.getElementById('step2');
        
        // 头像相关元素
        this.avatarGrid = document.getElementById('avatarGrid');
        this.avatarError = document.getElementById('avatarError');
        this.avatarLoading = document.getElementById('avatarLoading');
        this.selectAvatarBtn = document.getElementById('selectAvatarBtn');
        
        // 进度指示器
        this.progressSteps = document.querySelectorAll('.progress-step');
    }

    bindEvents() {
        // 文件上传事件
        this.uploadArea.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        
        // 拖拽上传事件
        this.uploadArea.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.uploadArea.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        this.uploadArea.addEventListener('drop', (e) => this.handleDrop(e));
        
        // 头像选择事件
        this.selectAvatarBtn.addEventListener('click', () => this.selectAvatar());
        
        // 键盘事件
        document.addEventListener('keydown', (e) => this.handleKeydown(e));
    }

    // 处理文件选择
    handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.processFile(file);
        }
    }

    // 处理拖拽悬停
    handleDragOver(event) {
        event.preventDefault();
        this.uploadArea.classList.add('dragover');
    }

    // 处理拖拽离开
    handleDragLeave(event) {
        event.preventDefault();
        this.uploadArea.classList.remove('dragover');
    }

    // 处理文件拖拽放置
    handleDrop(event) {
        event.preventDefault();
        this.uploadArea.classList.remove('dragover');
        
        const files = event.dataTransfer.files;
        if (files.length > 0) {
            this.processFile(files[0]);
        }
    }

    // 处理键盘事件
    handleKeydown(event) {
        // ESC键取消操作
        if (event.key === 'Escape') {
            this.resetToStep1();
        }
        
        // 在头像选择阶段，数字键快速选择
        if (this.step2 && !this.step2.classList.contains('hidden')) {
            const num = parseInt(event.key);
            if (num >= 1 && num <= 4) {
                this.selectAvatarByIndex(num - 1);
            }
        }
    }

    // 处理文件
    async processFile(file) {
        try {
            // 验证文件
            Utils.validateImageFile(file);
            
            // 显示加载状态
            this.showUploadLoading('正在上传和处理图片...');
            Utils.hideMessage(this.uploadError);
            
            // 创建FormData
            const formData = new FormData();
            formData.append('image', file);
            
            // 上传图片
            const uploadResult = await api.postFile('/api/upload-image', formData);
            this.sessionId = uploadResult.session_id;
            
            // 检查是否需要直接跳转到聊天页面
            if (uploadResult.data && uploadResult.data.redirect_to_chat) {
                if (uploadResult.data.preparation_complete) {
                    this.updateLoadingText('检测到相同图像，准备工作已完整，即将进入聊天...');
                    Utils.showSuccess(this.uploadError, '检测到相同图像，准备工作已完整');
                } else if (uploadResult.data.auto_completed) {
                    this.updateLoadingText('检测到相同图像，已自动补齐准备工作，即将进入聊天...');
                    Utils.showSuccess(this.uploadError, '检测到相同图像，已自动补齐准备工作');
                }
                
                // 延迟跳转给用户看到提示信息
                setTimeout(() => {
                    window.location.href = '/chat';
                }, 2000);
                return;
            }
            
            // 新图像处理流程
            if (uploadResult.data && uploadResult.data.is_new_image) {
                // 更新加载文本
                this.updateLoadingText('正在生成头像变体...');
                
                // 生成头像变体
                const variationsResult = await api.post('/api/avatar-variations', {
                    session_id: this.sessionId
                });
                
                // 显示头像选项
                if (variationsResult.data && variationsResult.data.variations) {
                    this.displayAvatarVariations(variationsResult.data.variations);
                    this.showStep2();
                    this.updateProgress(2);
                } else {
                    throw new Error('服务器返回的数据格式不正确');
                }
            } else {
                throw new Error('服务器响应格式错误');
            }
            
        } catch (error) {
            console.error('File processing error:', error);
            Utils.showError(this.uploadError, error.message);
        } finally {
            this.hideUploadLoading();
        }
    }

    // 显示头像变体
    displayAvatarVariations(variations) {
        this.avatarGrid.innerHTML = '';
        
        // 安全检查
        if (!variations || !Array.isArray(variations)) {
            console.error('variations参数无效:', variations);
            Utils.showError(this.uploadError, '头像变体数据格式错误');
            return;
        }
        
        variations.forEach((variation, index) => {
            const avatarOption = this.createAvatarOption(variation.url, index);
            this.avatarGrid.appendChild(avatarOption);
        });
        
        // 添加网格动画
        this.animateAvatarGrid();
    }

    // 创建头像选项元素
    createAvatarOption(imagePath, index) {
        const avatarOption = document.createElement('div');
        avatarOption.className = 'avatar-option';
        avatarOption.dataset.index = index;
        avatarOption.setAttribute('tabindex', '0');
        avatarOption.setAttribute('role', 'button');
        avatarOption.setAttribute('aria-label', `头像选项 ${index + 1}`);
        
        const img = document.createElement('img');
        img.src = imagePath;
        img.alt = `头像选项 ${index + 1}`;
        img.loading = 'lazy';
        
        // 添加图片加载错误处理
        img.onerror = () => {
            img.src = '/static/images/placeholder-avatar.png';
        };
        
        avatarOption.appendChild(img);
        
        // 添加点击事件
        avatarOption.addEventListener('click', () => this.selectAvatarByIndex(index));
        
        // 添加键盘事件
        avatarOption.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.selectAvatarByIndex(index);
            }
        });
        
        return avatarOption;
    }

    // 选择头像（通过索引）
    selectAvatarByIndex(index) {
        // 移除所有选中状态
        document.querySelectorAll('.avatar-option').forEach(option => {
            option.classList.remove('selected');
        });
        
        // 添加选中状态
        const selectedOption = document.querySelector(`[data-index="${index}"]`);
        if (selectedOption) {
            selectedOption.classList.add('selected');
            selectedOption.focus();
            
            // 启用继续按钮
            this.selectAvatarBtn.disabled = false;
            this.selectedAvatarIndex = index;
            
            // 播放选择音效（如果需要）
            this.playSelectionSound();
        }
    }

    // 最终选择头像
    async selectAvatar() {
        if (this.selectedAvatarIndex === null) {
            Utils.showError(this.avatarError, '请先选择一个头像选项');
            return;
        }
        
        try {
            // 显示加载状态
            this.showAvatarLoading('正在生成表情和个性...');
            Utils.hideMessage(this.avatarError);
            this.selectAvatarBtn.disabled = true;
            
            // 发送选择到服务器
            const result = await api.post('/api/select-avatar', {
                session_id: this.sessionId,
                selected_index: this.selectedAvatarIndex
            });
            
            // 更新进度
            this.updateProgress(3);
            
            // 短暂延迟后跳转到聊天页面
            setTimeout(() => {
                window.location.href = '/chat';
            }, 1000);
            
        } catch (error) {
            console.error('Avatar selection error:', error);
            Utils.showError(this.avatarError, error.message);
            this.selectAvatarBtn.disabled = false;
        } finally {
            this.hideAvatarLoading();
        }
    }

    // 显示步骤2
    showStep2() {
        this.step1.classList.add('hidden');
        this.step2.classList.remove('hidden');
        
        // 滚动到步骤2
        this.step2.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // 重置到步骤1
    resetToStep1() {
        this.step2.classList.add('hidden');
        this.step1.classList.remove('hidden');
        this.selectedAvatarIndex = null;
        this.sessionId = null;
        this.fileInput.value = '';
        this.updateProgress(1);
        
        // 重置按钮状态
        this.selectAvatarBtn.disabled = true;
    }

    // 更新进度指示器
    updateProgress(currentStep) {
        this.progressSteps.forEach((step, index) => {
            const stepNumber = index + 1;
            step.classList.remove('completed', 'current', 'pending');
            
            if (stepNumber < currentStep) {
                step.classList.add('completed');
            } else if (stepNumber === currentStep) {
                step.classList.add('current');
            } else {
                step.classList.add('pending');
            }
        });
    }

    // 显示上传加载状态
    showUploadLoading(text = '处理中...') {
        Utils.showLoading(this.uploadLoading, text);
    }

    // 隐藏上传加载状态
    hideUploadLoading() {
        Utils.hideLoading(this.uploadLoading);
    }

    // 更新加载文本
    updateLoadingText(text) {
        const loadingText = this.uploadLoading.querySelector('.loading-text');
        if (loadingText) {
            loadingText.textContent = text;
        }
    }

    // 显示头像加载状态
    showAvatarLoading(text = '处理中...') {
        Utils.showLoading(this.avatarLoading, text);
    }

    // 隐藏头像加载状态
    hideAvatarLoading() {
        Utils.hideLoading(this.avatarLoading);
    }

    // 动画显示头像网格
    animateAvatarGrid() {
        const avatarOptions = this.avatarGrid.querySelectorAll('.avatar-option');
        avatarOptions.forEach((option, index) => {
            option.style.opacity = '0';
            option.style.transform = 'translateY(20px)';
            
            setTimeout(() => {
                option.style.transition = 'all 0.5s ease-out';
                option.style.opacity = '1';
                option.style.transform = 'translateY(0)';
            }, index * 100);
        });
    }

    // 播放选择音效
    playSelectionSound() {
        // 可以添加音效播放逻辑
        try {
            const audio = new Audio('/static/audio/select.mp3');
            audio.volume = 0.3;
            audio.play().catch(() => {
                // 忽略音效播放失败
            });
        } catch (error) {
            // 忽略音效相关错误
        }
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 检查是否在准备页面
    if (document.getElementById('uploadArea')) {
        window.preparePage = new PreparePage();
    }
}); 
// 聊天页面类
class ChatPage {
    constructor() {
        this.isRecording = false;
        this.recordingSessionId = null;
        this.currentAudio = null;
        this.messageHistory = [];
        this.typingIndicatorId = null;
        
        this.initElements();
        this.bindEvents();
        this.initializePage();
    }

    initElements() {
        // 主要元素
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.recordBtn = document.getElementById('recordBtn');
        this.avatarVideo = document.getElementById('avatarVideo');
        
        // 容器元素
        this.chatContainer = document.querySelector('.chat-layout');
        this.videoContainer = document.querySelector('.video-container');
        this.audioIndicator = document.querySelector('.audio-indicator');
    }

    bindEvents() {
        // 消息输入事件
        this.messageInput.addEventListener('input', () => this.handleInputChange());
        this.messageInput.addEventListener('keypress', (e) => this.handleKeyPress(e));
        
        // 按钮点击事件
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.recordBtn.addEventListener('click', () => this.toggleRecording());
        
        // 视频事件
        this.avatarVideo.addEventListener('loadstart', () => this.showVideoStatus('加载中...'));
        this.avatarVideo.addEventListener('canplay', () => this.hideVideoStatus());
        this.avatarVideo.addEventListener('error', () => this.showVideoStatus('视频加载失败'));
        
        // 全局键盘事件
        document.addEventListener('keydown', (e) => this.handleGlobalKeydown(e));
        
        // 窗口大小改变事件
        window.addEventListener('resize', Utils.debounce(() => this.handleResize(), 300));
    }

    // 初始化页面
    initializePage() {
        // 设置初始状态
        this.sendBtn.disabled = true;
        this.scrollToBottom();
        
        // 添加欢迎消息
        this.addWelcomeMessage();
        
        // 检查会话状态
        this.checkSessionStatus();
    }

    // 处理输入变化
    handleInputChange() {
        const message = this.messageInput.value.trim();
        this.sendBtn.disabled = message === '';
        
        // 自动调整输入框高度
        this.adjustInputHeight();
    }

    // 处理键盘按键
    handleKeyPress(event) {
        if (event.key === 'Enter') {
            if (event.shiftKey) {
                // Shift+Enter换行
                return;
            } else {
                // Enter发送消息
                event.preventDefault();
                if (!this.sendBtn.disabled) {
                    this.sendMessage();
                }
            }
        }
    }

    // 处理全局键盘事件
    handleGlobalKeydown(event) {
        // 空格键录音（当输入框未聚焦时）
        if (event.code === 'Space' && document.activeElement !== this.messageInput) {
            event.preventDefault();
            if (!this.isRecording) {
                this.startRecording();
            }
        }
        
        // ESC键停止录音
        if (event.key === 'Escape' && this.isRecording) {
            this.stopRecording();
        }
    }

    // 发送消息
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (message === '') return;
        
        // 添加用户消息到界面
        this.addMessage(message, 'user');
        
        // 清空输入框
        this.messageInput.value = '';
        this.sendBtn.disabled = true;
        this.adjustInputHeight();
        
        // 显示输入指示器
        this.showTypingIndicator();
        
        try {
            // 发送消息到服务器
            const response = await api.post('/api/send-message', { message });
            
            // 隐藏输入指示器
            this.hideTypingIndicator();
            
            // 添加AI回复到界面
            this.addMessage(response.response, 'ai');
            
            // 播放表情视频
            if (response.expression_video) {
                this.playExpressionVideo(response.expression_video);
            }
            
            // 播放音频回复
            if (response.audio_url) {
                this.playAudio(response.audio_url);
            }
            
            // 保存消息历史
            this.messageHistory.push(
                { type: 'user', content: message, timestamp: new Date() },
                { type: 'ai', content: response.response, timestamp: new Date() }
            );
            
        } catch (error) {
            console.error('Send message error:', error);
            this.hideTypingIndicator();
            this.addMessage('抱歉，发送消息时出现错误。请稍后重试。', 'ai', true);
        }
    }

    // 切换录音状态
    toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            this.startRecording();
        }
    }

    // 开始录音
    async startRecording() {
        try {
            // 更新UI状态
            this.isRecording = true;
            this.recordBtn.classList.add('recording');
            this.recordBtn.innerHTML = '<span class="btn-icon">⏹️</span>';
            this.recordBtn.setAttribute('aria-label', '停止录音');
            
            // 禁用发送按钮
            this.sendBtn.disabled = true;
            
            // 开始录音
            const response = await api.post('/api/start-recording');
            this.recordingSessionId = response.recording_session_id;
            
            // 添加录音提示
            this.showRecordingIndicator();
            
        } catch (error) {
            console.error('Start recording error:', error);
            this.resetRecordingState();
            this.addMessage('抱歉，启动录音失败。请检查麦克风权限。', 'ai', true);
        }
    }

    // 停止录音
    async stopRecording() {
        if (!this.recordingSessionId) {
            this.resetRecordingState();
            return;
        }
        
        // 更新UI状态
        this.resetRecordingState();
        this.showTypingIndicator();
        
        try {
            // 停止录音并获取转录文本
            const response = await api.post('/api/stop-recording', {
                recording_session_id: this.recordingSessionId
            });
            
            const transcribedText = response.transcribed_text;
            
            if (transcribedText && transcribedText.trim()) {
                // 添加转录的用户消息
                this.addMessage(transcribedText, 'user');
                
                // 发送转录文本到AI
                const aiResponse = await api.post('/api/send-message', {
                    message: transcribedText
                });
                
                // 隐藏输入指示器
                this.hideTypingIndicator();
                
                // 添加AI回复
                this.addMessage(aiResponse.response, 'ai');
                
                // 播放表情和音频
                if (aiResponse.expression_video) {
                    this.playExpressionVideo(aiResponse.expression_video);
                }
                
                if (aiResponse.audio_url) {
                    this.playAudio(aiResponse.audio_url);
                }
                
                // 保存消息历史
                this.messageHistory.push(
                    { type: 'user', content: transcribedText, timestamp: new Date() },
                    { type: 'ai', content: aiResponse.response, timestamp: new Date() }
                );
                
            } else {
                this.hideTypingIndicator();
                this.addMessage('抱歉，没有检测到语音内容。请重试。', 'ai', true);
            }
            
        } catch (error) {
            console.error('Stop recording error:', error);
            this.hideTypingIndicator();
            this.addMessage('抱歉，处理语音时出现错误。请重试。', 'ai', true);
        } finally {
            this.recordingSessionId = null;
            this.hideRecordingIndicator();
        }
    }

    // 重置录音状态
    resetRecordingState() {
        this.isRecording = false;
        this.recordBtn.classList.remove('recording');
        this.recordBtn.innerHTML = '<span class="btn-icon">🎤</span>';
        this.recordBtn.setAttribute('aria-label', '开始录音');
        
        // 恢复发送按钮状态
        this.handleInputChange();
    }

    // 添加消息到聊天界面
    addMessage(content, sender, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        if (isError) {
            messageDiv.classList.add('error-message');
        }
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = content;
        
        const messageTime = document.createElement('div');
        messageTime.className = 'message-time';
        messageTime.textContent = Utils.formatTime();
        
        messageDiv.appendChild(messageContent);
        messageDiv.appendChild(messageTime);
        
        // 添加动画效果
        messageDiv.style.opacity = '0';
        messageDiv.style.transform = 'translateY(20px)';
        
        this.chatMessages.appendChild(messageDiv);
        
        // 触发动画
        requestAnimationFrame(() => {
            messageDiv.style.transition = 'all 0.3s ease-out';
            messageDiv.style.opacity = '1';
            messageDiv.style.transform = 'translateY(0)';
        });
        
        // 滚动到底部
        this.scrollToBottom();
    }

    // 显示输入指示器
    showTypingIndicator() {
        this.hideTypingIndicator(); // 确保没有重复的指示器
        
        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-indicator';
        typingDiv.id = 'typingIndicator';
        
        // 创建打字点动画
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('div');
            dot.className = 'typing-dot';
            typingDiv.appendChild(dot);
        }
        
        this.chatMessages.appendChild(typingDiv);
        this.scrollToBottom();
    }

    // 隐藏输入指示器
    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    // 显示录音指示器
    showRecordingIndicator() {
        const recordingDiv = document.createElement('div');
        recordingDiv.className = 'recording-indicator';
        recordingDiv.id = 'recordingIndicator';
        recordingDiv.innerHTML = '🎤 正在录音...';
        
        this.chatMessages.appendChild(recordingDiv);
        this.scrollToBottom();
    }

    // 隐藏录音指示器
    hideRecordingIndicator() {
        const recordingIndicator = document.getElementById('recordingIndicator');
        if (recordingIndicator) {
            recordingIndicator.remove();
        }
    }

    // 播放表情视频
    playExpressionVideo(videoUrl) {
        this.avatarVideo.src = videoUrl;
        this.avatarVideo.play().catch(error => {
            console.error('Video play error:', error);
            this.showVideoStatus('视频播放失败');
        });
    }

    // 播放音频 - 修复播放中断问题
    playAudio(audioUrl) {
        console.log(`开始播放音频: ${audioUrl}`);
        
        // 验证URL
        if (!audioUrl || audioUrl.trim() === '') {
            console.error('音频URL为空');
            return;
        }
        
        // 停止当前音频 - 优化时序
        if (this.currentAudio) {
            try {
                this.currentAudio.pause();
                this.currentAudio.currentTime = 0;
                this.currentAudio.src = '';  // 清空src避免冲突
            } catch (e) {
                console.warn('停止当前音频失败:', e);
            }
            this.currentAudio = null;
        }
        
        // 稍微延迟创建新音频，确保旧音频完全停止
        setTimeout(() => {
            // 创建新音频
            this.currentAudio = new Audio();
            
            // 添加详细的事件监听器
            this.currentAudio.addEventListener('loadstart', () => {
                console.log('音频开始加载');
                this.showAudioIndicator();
            });
            
            this.currentAudio.addEventListener('loadedmetadata', () => {
                console.log(`音频元数据加载完成 - 时长: ${this.currentAudio.duration}秒`);
            });
            
            this.currentAudio.addEventListener('canplay', () => {
                console.log('音频可以播放');
            });
            
            this.currentAudio.addEventListener('ended', () => {
                console.log('音频播放结束');
                this.hideAudioIndicator();
                this.currentAudio = null;
            });
            
            this.currentAudio.addEventListener('error', (e) => {
                console.error('音频加载错误:', e);
                
                if (this.currentAudio && this.currentAudio.error) {
                    const errorCode = this.currentAudio.error.code;
                    const errorMessages = {
                        1: 'MEDIA_ERR_ABORTED - 音频加载被中止',
                        2: 'MEDIA_ERR_NETWORK - 网络错误',
                        3: 'MEDIA_ERR_DECODE - 音频解码错误',
                        4: 'MEDIA_ERR_SRC_NOT_SUPPORTED - 音频格式不支持'
                    };
                    
                    const errorMsg = errorMessages[errorCode] || `未知错误 (代码: ${errorCode})`;
                    console.error(`音频错误详情: ${errorMsg}`);
                    
                    // 显示用户友好的错误消息
                    this.showAudioError(errorMsg);
                }
                
                this.hideAudioIndicator();
                this.currentAudio = null;
            });
            
            // 设置音频源
            this.currentAudio.src = audioUrl;
            
            // 预加载音频
            this.currentAudio.load();
            
            // 尝试播放
            const playPromise = this.currentAudio.play();
            
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    console.log('音频播放成功');
                }).catch(error => {
                    console.error('音频播放失败:', error);
                    
                    // 尝试用户交互后播放
                    if (error.name === 'NotAllowedError') {
                        console.log('需要用户交互才能播放音频');
                        this.showAudioInteractionPrompt();
                    } else {
                        this.showAudioError(error.message);
                    }
                    
                    this.hideAudioIndicator();
                });
            }
        }, 50); // 50ms延迟确保旧音频完全停止
    }
    
    // 显示音频错误信息
    showAudioError(errorMessage) {
        // 创建错误提示
        const errorDiv = document.createElement('div');
        errorDiv.className = 'audio-error-message';
        errorDiv.innerHTML = `
            <div style="background: #ffe6e6; border: 1px solid #ff9999; border-radius: 4px; padding: 8px; margin: 5px 0; font-size: 12px; color: #cc0000;">
                🔊 音频播放失败: ${errorMessage}
                <button onclick="this.parentElement.remove()" style="float: right; background: none; border: none; color: #cc0000; cursor: pointer;">×</button>
            </div>
        `;
        
        this.chatMessages.appendChild(errorDiv);
        this.scrollToBottom();
        
        // 5秒后自动移除
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    }
    
    // 显示需要用户交互的提示
    showAudioInteractionPrompt() {
        const promptDiv = document.createElement('div');
        promptDiv.className = 'audio-interaction-prompt';
        promptDiv.innerHTML = `
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; padding: 8px; margin: 5px 0; font-size: 12px; color: #856404;">
                🔊 需要点击以启用音频播放
                <button onclick="this.enableAudioPlayback()" style="margin-left: 10px; padding: 2px 8px; background: #ffc107; border: none; border-radius: 3px; cursor: pointer;">启用音频</button>
            </div>
        `;
        
        // 添加启用音频的方法
        promptDiv.querySelector('button').onclick = () => {
            // 播放一个静音音频以解除浏览器限制
            const silentAudio = new Audio();
            silentAudio.src = 'data:audio/wav;base64,UklGRnoAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoAAAAAAAAAAAAAAAA=';
            silentAudio.play().then(() => {
                console.log('音频播放权限已启用');
                promptDiv.remove();
                
                // 重新尝试播放原音频
                if (this.currentAudio && this.currentAudio.src) {
                    this.currentAudio.play().catch(e => {
                        console.error('重新播放音频失败:', e);
                    });
                }
            }).catch(e => {
                console.error('启用音频失败:', e);
            });
        };
        
        this.chatMessages.appendChild(promptDiv);
        this.scrollToBottom();
    }

    // 显示视频状态
    showVideoStatus(message) {
        let statusDiv = this.videoContainer.querySelector('.video-status');
        if (!statusDiv) {
            statusDiv = document.createElement('div');
            statusDiv.className = 'video-status';
            this.videoContainer.appendChild(statusDiv);
        }
        statusDiv.textContent = message;
    }

    // 隐藏视频状态
    hideVideoStatus() {
        const statusDiv = this.videoContainer.querySelector('.video-status');
        if (statusDiv) {
            statusDiv.remove();
        }
    }

    // 显示音频指示器
    showAudioIndicator() {
        if (!this.audioIndicator) {
            this.audioIndicator = document.createElement('div');
            this.audioIndicator.className = 'audio-indicator';
            this.audioIndicator.innerHTML = `
                播放中
                <div class="audio-wave"></div>
                <div class="audio-wave"></div>
                <div class="audio-wave"></div>
            `;
            this.videoContainer.appendChild(this.audioIndicator);
        }
    }

    // 隐藏音频指示器
    hideAudioIndicator() {
        if (this.audioIndicator) {
            this.audioIndicator.remove();
            this.audioIndicator = null;
        }
    }

    // 滚动到底部
    scrollToBottom() {
        requestAnimationFrame(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        });
    }

    // 自动调整输入框高度
    adjustInputHeight() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
    }

    // 处理窗口大小改变
    handleResize() {
        this.scrollToBottom();
    }

    // 添加欢迎消息
    addWelcomeMessage() {
        const welcomeMessages = [
            '你好！我是你的AI头像助手。',
            '你可以通过文字或语音与我交流。',
            '试着问我一些问题吧！'
        ];
        
        welcomeMessages.forEach((message, index) => {
            setTimeout(() => {
                this.addMessage(message, 'ai');
            }, index * 1000);
        });
    }

    // 检查会话状态
    async checkSessionStatus() {
        try {
            const response = await api.get('/api/preparation-status');
            if (!response.is_ready) {
                // 如果会话未准备好，重定向到准备页面
                const redirectTo = response.redirect_to || '/';
                window.location.href = redirectTo;
            }
        } catch (error) {
            console.error('Session status check error:', error);
            // 出错时也重定向到准备页面
            window.location.href = '/';
        }
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 检查是否在聊天页面
    if (document.getElementById('chatMessages')) {
        window.chatPage = new ChatPage();
    }
}); 
// 公共工具类
class Utils {
    // 显示错误消息
    static showError(element, message) {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (element) {
            element.textContent = message;
            element.className = 'alert alert-error';
            element.classList.remove('hidden');
            
            // 自动隐藏错误消息
            setTimeout(() => {
                element.classList.add('hidden');
            }, 5000);
        }
    }

    // 显示成功消息
    static showSuccess(element, message) {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (element) {
            element.textContent = message;
            element.className = 'alert alert-success';
            element.classList.remove('hidden');
            
            // 自动隐藏成功消息
            setTimeout(() => {
                element.classList.add('hidden');
            }, 3000);
        }
    }

    // 显示信息消息
    static showInfo(element, message) {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (element) {
            element.textContent = message;
            element.className = 'alert alert-info';
            element.classList.remove('hidden');
        }
    }

    // 隐藏消息
    static hideMessage(element) {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (element) {
            element.classList.add('hidden');
        }
    }

    // 显示加载状态
    static showLoading(element, text = '处理中...') {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (element) {
            element.innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    <div class="loading-text">${text}</div>
                </div>
            `;
            element.classList.remove('hidden');
        }
    }

    // 隐藏加载状态
    static hideLoading(element) {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (element) {
            element.classList.add('hidden');
        }
    }

    // 格式化时间
    static formatTime(date = new Date()) {
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60000) { // 小于1分钟
            return '刚刚';
        } else if (diff < 3600000) { // 小于1小时
            return `${Math.floor(diff / 60000)}分钟前`;
        } else if (diff < 86400000) { // 小于1天
            return `${Math.floor(diff / 3600000)}小时前`;
        } else {
            return date.toLocaleDateString('zh-CN');
        }
    }

    // 验证文件类型
    static validateImageFile(file) {
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp'];
        const maxSize = 10 * 1024 * 1024; // 10MB
        
        if (!allowedTypes.includes(file.type)) {
            throw new Error('请上传有效的图片文件 (JPEG, PNG, GIF, BMP)');
        }
        
        if (file.size > maxSize) {
            throw new Error('图片文件大小不能超过 10MB');
        }
        
        return true;
    }

    // 生成唯一ID
    static generateId() {
        return 'id_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
    }

    // 防抖函数
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // 节流函数
    static throttle(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
}

// API调用封装类
class ApiClient {
    constructor() {
        this.baseUrl = '';
        this.defaultHeaders = {
            'Content-Type': 'application/json'
        };
    }

    // 通用请求方法
    async request(url, options = {}) {
        const config = {
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };

        try {
            const response = await fetch(url, config);
            
            // 检查响应状态
            if (!response.ok) {
                throw new Error(`HTTP Error: ${response.status} ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const data = await response.json();
                if (data.error) {
                    throw new Error(data.message || '服务器错误');
                }
                return data;
            } else {
                return response;
            }
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    }

    // GET请求
    async get(url, params = {}) {
        const urlParams = new URLSearchParams(params);
        const fullUrl = urlParams.toString() ? `${url}?${urlParams}` : url;
        return this.request(fullUrl, { method: 'GET' });
    }

    // POST请求
    async post(url, data = {}) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // POST文件上传
    async postFile(url, formData) {
        return this.request(url, {
            method: 'POST',
            headers: {}, // 不设置Content-Type，让浏览器自动设置
            body: formData
        });
    }

    // PUT请求
    async put(url, data = {}) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    // DELETE请求
    async delete(url) {
        return this.request(url, { method: 'DELETE' });
    }
}

// 全局API客户端实例
const api = new ApiClient();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 添加全局错误处理
    window.addEventListener('error', function(event) {
        console.error('Global Error:', event.error);
    });

    // 添加未处理的Promise拒绝处理
    window.addEventListener('unhandledrejection', function(event) {
        console.error('Unhandled Promise Rejection:', event.reason);
    });

    // 初始化全局UI增强
    initGlobalEnhancements();
});

// 全局UI增强功能
function initGlobalEnhancements() {
    // 为所有按钮添加点击效果
    document.querySelectorAll('.btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            // 创建波纹效果
            const ripple = document.createElement('span');
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.cssText = `
                position: absolute;
                width: ${size}px;
                height: ${size}px;
                left: ${x}px;
                top: ${y}px;
                background: rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                transform: scale(0);
                animation: ripple 0.6s linear;
                pointer-events: none;
            `;
            
            // 添加波纹动画样式
            if (!document.getElementById('ripple-style')) {
                const style = document.createElement('style');
                style.id = 'ripple-style';
                style.textContent = `
                    @keyframes ripple {
                        to {
                            transform: scale(4);
                            opacity: 0;
                        }
                    }
                `;
                document.head.appendChild(style);
            }
            
            // 确保按钮有相对定位
            this.style.position = 'relative';
            this.style.overflow = 'hidden';
            
            this.appendChild(ripple);
            
            // 动画结束后移除元素
            setTimeout(() => {
                ripple.remove();
            }, 600);
        });
    });

    // 为输入框添加浮动标签效果
    document.querySelectorAll('.form-control').forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.classList.add('focused');
        });
        
        input.addEventListener('blur', function() {
            if (!this.value) {
                this.parentElement.classList.remove('focused');
            }
        });
        
        // 检查初始值
        if (input.value) {
            input.parentElement.classList.add('focused');
        }
    });
}

// 导出工具类和API客户端
window.Utils = Utils;
window.api = api; 
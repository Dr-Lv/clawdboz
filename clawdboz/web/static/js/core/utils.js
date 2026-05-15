// Utility functions

        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');
        
        if (!token) {
            window.location.href = '/static/login.html';
        }
        
        let ws = null, bots = [], selectedBots = new Set();
        let isConnected = false;
        let thinkingMode = true; // 思考模式开关，默认开启
        const streamingMessages = new Map();
        const receivedChunks = new Set(); // 跟踪已接收的 chunk，防止重复
        const messageTools = new Map();
        let lastMsgTime = null;
        
        // 会话管理
        let sessions = [];
        let currentSessionId = null;
        let currentBotId = null;
        const sessionUnreadCounts = new Map();
        
        // 聊天记录数据库
        const DB_NAME = 'ClawdbozChatDB';
        const DB_VERSION = 4; // 升级版本
        let db = null;
        
        // 搜索相关
        let searchResults = [];
        let currentSearchIndex = -1;
        let isSearchOpen = false;
        
        // ========== 群聊头像生成函数 ==========
        function generateGroupAvatarHtml(botIds) {
            // 第一个格子显示用户，后面显示 Bot
            const memberIds = ['user', ...(botIds || [])];
            const count = memberIds.length;
            
            if (count === 0) {
                return `<div class="group-avatar-grid grid-2x2"><div class="grid-cell bg-gradient-to-br from-gray-400 to-gray-600"><i class="fas fa-users"></i></div></div>`;
            }
            
            let gridClass = 'grid-2x2';
            let displayCount = count;
            let showMore = false;
            
            if (count > 4) {
                gridClass = 'grid-3x3';
                if (count > 9) {
                    displayCount = 9; // 用户 + 最多8个bot
                    showMore = true;
                } else {
                    displayCount = count;
                }
            }
            
            let cellsHtml = '';
            for (let i = 0; i < displayCount; i++) {
                const memberId = memberIds[i];
                
                if (memberId === 'user') {
                    // 用户头像 - 使用用户自定义的配置
                    const userColor = userProfile.avatar_color || 'from-indigo-500 to-purple-600';
                    const userIcon = userProfile.avatar_icon || 'fa-user';
                    cellsHtml += `<div class="grid-cell bg-gradient-to-br ${userColor}"><i class="fas ${userIcon}"></i></div>`;
                } else {
                    // Bot 头像 - 使用 Bot 自定义的配置
                    const bot = bots.find(b => b.id === memberId);
                    if (bot && bot.avatar_color) {
                        // 使用自定义头像
                        const colorClass = bot.avatar_color.startsWith('from-') ? bot.avatar_color : 'from-blue-500 to-blue-600';
                        const iconClass = bot.avatar_icon || 'fa-robot';
                        cellsHtml += `<div class="grid-cell bg-gradient-to-br ${colorClass}"><i class="fas ${iconClass}"></i></div>`;
                    } else {
                        // 使用默认配置 - 使用 getBotAvatarConfig 确保一致性
                        const cfg = getBotAvatarConfig(memberId);
                        cellsHtml += `<div class="grid-cell ${cfg.color}"><i class="fas ${cfg.icon}"></i></div>`;
                    }
                }
            }
            
            // 如果有更多成员，最后一格显示 +N
            if (showMore) {
                const moreCount = memberIds.length - 9;
                cellsHtml = cellsHtml.slice(0, cellsHtml.lastIndexOf('<div class="grid-cell'));
                cellsHtml += `<div class="grid-cell more">+${moreCount}</div>`;
            }
            
            // 填充空格使之完整
            const totalCells = gridClass === 'grid-3x3' ? 9 : 4;
            const actualCells = showMore ? 9 : displayCount;
            for (let i = actualCells; i < totalCells; i++) {
                cellsHtml += `<div class="grid-cell" style="background: transparent;"></div>`;
            }
            
            return `<div class="group-avatar-grid ${gridClass}">${cellsHtml}</div>`;
        }
        
        // ========== Toast 提示函数 ==========
        function showToast(message, type = 'info', duration = 3000) {
            const container = document.getElementById('toastContainer');
            if (!container) return;
            
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            
            const iconMap = {
                'success': 'fa-check-circle',
                'error': 'fa-times-circle',
                'warning': 'fa-exclamation-triangle',
                'info': 'fa-info-circle'
            };
            
            toast.innerHTML = `<i class="fas ${iconMap[type] || iconMap.info}"></i><span>${message}</span>`;
            container.appendChild(toast);
            
            setTimeout(() => {
                toast.classList.add('hiding');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }
        
        // 更多菜单和添加 Bot
        let isMoreMenuOpen = false;
        let tempSelectedBots = new Set();
        let isCreatingNewSession = false;
        
        // 停止生成功能
        let activeStreams = new Set();
        
        // 当前选中的标签页
        let currentTab = 'messages';
        
        // 折叠状态
        let collapsedGroups = new Set();
        let allGroupsCollapsed = false;
        
        // 选中的联系人
        let selectedContactId = null;
        
        const botConfigs = [
            { color: 'bg-gradient-to-br from-blue-500 to-blue-600', icon: 'fa-code' },
            { color: 'bg-gradient-to-br from-green-500 to-green-600', icon: 'fa-pen-nib' },
            { color: 'bg-gradient-to-br from-purple-500 to-purple-600', icon: 'fa-server' },
        ];
        
        // 头像预设选项
        const avatarPresets = [
            { color: 'from-blue-500 to-blue-600', icon: 'fa-user', name: '蓝色' },
            { color: 'from-indigo-500 to-purple-600', icon: 'fa-user', name: '紫色' },
            { color: 'from-purple-500 to-pink-500', icon: 'fa-user', name: '粉紫' },
            { color: 'from-pink-500 to-rose-500', icon: 'fa-user', name: '粉色' },
            { color: 'from-red-500 to-orange-500', icon: 'fa-user', name: '红色' },
            { color: 'from-orange-500 to-amber-500', icon: 'fa-user', name: '橙色' },
            { color: 'from-green-500 to-emerald-500', icon: 'fa-user', name: '绿色' },
            { color: 'from-teal-500 to-cyan-500', icon: 'fa-user', name: '青色' },
            { color: 'from-cyan-500 to-sky-500', icon: 'fa-user', name: '天蓝' },
            { color: 'from-slate-500 to-gray-500', icon: 'fa-user', name: '灰色' },
        ];
        
        // Bot 头像预设
        const botAvatarPresets = [
            { color: 'from-blue-500 to-blue-600', icon: 'fa-robot', name: '机器人' },
            { color: 'from-green-500 to-green-600', icon: 'fa-code', name: '代码' },
            { color: 'from-purple-500 to-purple-600', icon: 'fa-server', name: '服务器' },
            { color: 'from-pink-500 to-rose-500', icon: 'fa-brain', name: '智能' },
            { color: 'from-orange-500 to-amber-500', icon: 'fa-bolt', name: '闪电' },
            { color: 'from-red-500 to-orange-500', icon: 'fa-fire', name: '热情' },
            { color: 'from-teal-500 to-cyan-500', icon: 'fa-atom', name: '科学' },
            { color: 'from-indigo-500 to-purple-600', icon: 'fa-magic', name: '魔法' },
            { color: 'from-cyan-500 to-sky-500', icon: 'fa-cloud', name: '云朵' },
            { color: 'from-emerald-500 to-green-600', icon: 'fa-leaf', name: '自然' },
        ];
        
        // 当前选中的头像
        let currentAvatarSelection = { color: '', icon: '' };
        
        // ========== 头像选择器 ==========
        
        function showAvatarSelector(target, botId = '') {
            document.getElementById('avatarSelectorTarget').value = target;
            document.getElementById('avatarSelectorTargetId').value = botId;
            
            const presets = target === 'user' ? avatarPresets : botAvatarPresets;
            const grid = document.getElementById('avatarSelectorGrid');
            
            // 获取当前头像设置
            let currentColor = '';
            let currentIcon = '';
            if (target === 'user') {
                currentColor = document.getElementById('userAvatarColor').value;
                currentIcon = document.getElementById('userAvatarIcon').value;
            } else {
                currentColor = document.getElementById('editBotAvatarColor').value;
                currentIcon = document.getElementById('editBotAvatarIcon').value;
            }
            currentAvatarSelection = { color: currentColor, icon: currentIcon };
            
            // 生成头像选项
            grid.innerHTML = presets.map((preset, index) => {
                const isSelected = preset.color === currentColor && preset.icon === currentIcon;

// Export utilities

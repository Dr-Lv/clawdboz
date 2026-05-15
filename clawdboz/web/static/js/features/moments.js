// Moments feature

                    `;
                }
            }
            
            container.innerHTML = html;
            bindSwipeEvents();
        }
        
        // ========== 滑动删除 ==========
        
        let swipeItem = null;
        let swipeStartX = 0;
        let swipeStartY = 0;
        let swipeOffset = 0;
        let swipeStartTime = 0;
        const SWIPE_THRESHOLD = -80;
        const MAX_SWIPE = -100;
        const CLICK_TIME_THRESHOLD = 300;
        const CLICK_DISTANCE_THRESHOLD = 10;
        
        function bindSwipeEvents() {
            const items = document.querySelectorAll('.sidebar-item');
            
            items.forEach(item => {
                item.addEventListener('touchstart', handleSwipeStart, { passive: true });
                item.addEventListener('touchmove', handleSwipeMove, { passive: true });
                item.addEventListener('touchend', handleSwipeEnd, { passive: true });
                item.addEventListener('touchcancel', handleSwipeEnd, { passive: true });
                item.addEventListener('mousedown', handleSwipeStart);
                item.addEventListener('mousemove', handleSwipeMove);
                item.addEventListener('mouseup', handleSwipeEnd);
                item.addEventListener('mouseleave', handleSwipeEnd);
            });
        }
        
        function handleSwipeStart(e) {
            if (e.target.closest('.sidebar-delete-btn')) return;
            
            const item = e.currentTarget;
            
            document.querySelectorAll('.sidebar-item.swiped').forEach(el => {
                if (el !== item) {
                    resetSwipe(el);
                }
            });
            
            swipeItem = item;
            swipeStartTime = Date.now();
            
            if (e.type.includes('touch')) {
                swipeStartX = e.touches[0].clientX;
                swipeStartY = e.touches[0].clientY;
            } else {
                swipeStartX = e.clientX;
                swipeStartY = e.clientY;
            }
            
            swipeOffset = 0;
            swipeItem.classList.add('swiping');
        }
        
        function handleSwipeMove(e) {
            if (!swipeItem) return;
            
            let currentX, currentY;
            if (e.type.includes('touch')) {
                currentX = e.touches[0].clientX;
                currentY = e.touches[0].clientY;
            } else {
                currentX = e.clientX;
                currentY = e.clientY;
            }
            
            const diffX = currentX - swipeStartX;
            const diffY = currentY - swipeStartY;
            
            if (Math.abs(diffY) > Math.abs(diffX)) return;
            
            const content = swipeItem.querySelector('.sidebar-item-content');
            if (!content) return;
            
            const isSwiped = swipeItem.classList.contains('swiped');
            
            if (isSwiped) {
                if (diffX > 0) {
                    swipeOffset = Math.min(diffX - 80, 0);
                    content.style.transform = `translateX(${swipeOffset}px)`;
                }
            } else {
                if (diffX < 0) {
                    swipeOffset = Math.max(diffX, MAX_SWIPE);
                    content.style.transform = `translateX(${swipeOffset}px)`;
                }
            }
        }
        
        function handleSwipeEnd(e) {
            if (!swipeItem) return;
            
            swipeItem.classList.remove('swiping');
            
            const touchDuration = Date.now() - swipeStartTime;
            const content = swipeItem.querySelector('.sidebar-item-content');
            
            const isClick = touchDuration < CLICK_TIME_THRESHOLD && Math.abs(swipeOffset) < CLICK_DISTANCE_THRESHOLD;
            
            if (isClick) {
                if (content) {
                    content.style.transform = '';
                }
                swipeItem = null;
                swipeStartX = 0;
                swipeStartY = 0;
                swipeOffset = 0;
                return;
            }
            
            if (swipeOffset <= SWIPE_THRESHOLD) {
                if (content) {
                    content.style.transform = `translateX(-80px)`;
                }
                swipeItem.classList.add('swiped');
            } else {
                resetSwipe(swipeItem);
            }
            
            swipeItem = null;
            swipeStartX = 0;
            swipeStartY = 0;
            swipeOffset = 0;
        }
        
        function resetSwipe(item) {
            const content = item.querySelector('.sidebar-item-content');
            content.style.transform = '';
            item.classList.remove('swiped');
        }
        
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.sidebar-item')) {
                document.querySelectorAll('.sidebar-item.swiped').forEach(resetSwipe);
            }
        });
        
        async function confirmDeleteSession(sessionId, event) {
            event.stopPropagation();
            
            try {
                const session = sessions.find(s => s.id === sessionId);
                const sessionName = session ? session.name : '这个会话';
                
                let confirmed = false;
                try {
                    confirmed = confirm(`确定要删除"${sessionName}"吗？\n\n聊天记录将无法恢复。`);
                } catch (e) {
                    console.error('[confirmDeleteSession] confirm() 调用失败:', e);
                }
                
                if (!confirmed) return;
                
                await deleteSessionById(sessionId);
            } catch (e) {
                console.error('[confirmDeleteSession] 删除失败:', e);
                alert('删除失败: ' + e.message);
            }
        }
        
        async function deleteSessionById(sessionId) {
            const success = await deleteSessionFromDB(sessionId);
            if (!success) {
                alert('删除失败，请重试');
                return;
            }
            
            sessions = sessions.filter(s => s.id !== sessionId);
            
            if (currentSessionId === sessionId) {
                currentSessionId = null;
                if (sessions.length > 0) {
                    await selectSession(sessions[0].id);
                    return;
                } else {
                    document.getElementById('messages').innerHTML = `
                        <div class="empty-state">
                            <div class="empty-icon">🤖</div>
                            <div>点击右上角"+"创建新会话</div>
                        </div>
                    `;
                    document.getElementById('headerTitle').textContent = '选择一个会话';
                    selectedBots.clear();
                    updatePlaceholder();
                }
            }
            
            renderSessionList();
        }
        
        // ========== 头像组 ==========
        
        function generateAvatarGroup(botIds) {
            if (!botIds || botIds.length === 0 || bots.length === 0) {
                return `
                    <div class="group-avatar" style="display:flex;align-items:center;margin-right:12px;flex-shrink:0;">
                        <div class="sidebar-avatar bg-gradient-to-br from-gray-400 to-gray-600 text-white" style="width:40px;height:40px;">
                            <i class="fas fa-robot"></i>
                        </div>
                    </div>
                `;
            }
            
            if (botIds.length === 1) {
                const bot = bots.find(b => b.id === botIds[0]);
                if (!bot) {
                    return `
                        <div class="group-avatar" style="display:flex;align-items:center;margin-right:12px;flex-shrink:0;">
                            <div class="sidebar-avatar bg-gradient-to-br from-blue-400 to-blue-600 text-white" style="width:40px;height:40px;">
                                <i class="fas fa-robot"></i>
                            </div>
                        </div>
                    `;
                }
                const cfg = getBotAvatarConfig(botIds[0]);
                
                return `
                    <div class="group-avatar" style="display:flex;align-items:center;margin-right:12px;flex-shrink:0;">
                        <div class="sidebar-avatar ${cfg.color} text-white" style="width:40px;height:40px;">
                            <i class="fas ${cfg.icon}"></i>
                        </div>
                    </div>
                `;
            }
            
            const maxDisplay = 2;
            const displayBots = botIds.slice(0, maxDisplay);
            const remainingCount = botIds.length - maxDisplay;
            
            const userAvatar = `
                <div class="group-avatar-item" style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);display:flex;align-items:center;justify-content:center;color:white;font-size:12px;border:2px solid #1e222d;z-index:10;flex-shrink:0;">
                    <i class="fas fa-user"></i>
                </div>
            `;
            
            const botAvatars = displayBots.map((botId, idx) => {
                const bot = bots.find(b => b.id === botId);
                if (!bot) return '';
                const cfg = getBotAvatarConfig(botId);
                const zIndex = 9 - idx;
                const marginLeft = '-10px';
                
                let bgStyle = '';
                if (cfg.color.includes('from-blue')) {
                    bgStyle = 'background:linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)';
                } else if (cfg.color.includes('from-green')) {
                    bgStyle = 'background:linear-gradient(135deg, #22c55e 0%, #16a34a 100%)';
                } else if (cfg.color.includes('from-purple')) {
                    bgStyle = 'background:linear-gradient(135deg, #a855f7 0%, #9333ea 100%)';
                } else {
                    bgStyle = 'background:linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)';
                }
                
                return `
                    <div class="group-avatar-item" style="width:28px;height:28px;border-radius:50%;${bgStyle};display:flex;align-items:center;justify-content:center;color:white;font-size:12px;border:2px solid #1e222d;z-index:${zIndex};margin-left:${marginLeft};flex-shrink:0;">
                        <i class="fas ${cfg.icon}"></i>
                    </div>
                `;
            }).join('');
            
            const moreBadge = remainingCount > 0 ? `
                <div style="width:28px;height:28px;border-radius:50%;background:#3370ff;display:flex;align-items:center;justify-content:center;color:white;font-size:11px;border:2px solid #1e222d;z-index:1;margin-left:-10px;flex-shrink:0;">
                    +${remainingCount}
                </div>
            ` : '';
            
            return `
                <div class="group-avatar" style="display:flex;align-items:center;margin-right:12px;flex-shrink:0;min-width:28px;">
                    ${userAvatar}
                    ${botAvatars}
                    ${moreBadge}
                </div>
            `;
        }
        
        function formatTime(timestamp) {
            const now = Date.now();
            const diff = now - timestamp;
            
            if (diff < 60000) return '刚刚';
            if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
            if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
            const date = new Date(timestamp);
            return `${date.getMonth() + 1}月${date.getDate()}日`;
        }
        
        // ========== 选择会话 ==========
        
        const pendingMessages = new Map();
        
        async function selectSession(sessionId) {
            if (currentSessionId && streamingMessages.size > 0) {
                for (const [msgId, stream] of streamingMessages) {
                    if (stream.isStreaming) {
                        const contentEl = document.getElementById(`content-${msgId}`);
                        const currentContent = contentEl ? contentEl.innerHTML : '';
                        
                        pendingMessages.set(msgId, {
                            sessionId: stream.sessionId,
                            botId: stream.botId,
                            content: currentContent,
                            timestamp: stream.timestamp || Date.now(),
                            botName: stream.botName || stream.botId
                        });
                    }
                }
            }
            
            currentSessionId = sessionId;
            const session = sessions.find(s => s.id === sessionId);
            
            if (session) {
                selectedBots = new Set(session.botIds);
                updateHeader(session);
                isLoadingChatHistory = false;
                
                // 从服务器加载思考模式设置（如果失败则使用 localStorage 的默认值）
                const loadedFromServer = await loadThinkingModeFromServer(sessionId);
                if (!loadedFromServer) {
                    // 如果服务器没有设置，使用 localStorage 的值并保存到服务器
                    const saved = localStorage.getItem('thinkingMode');
                    if (saved === 'off') {
                        thinkingMode = false;
                    } else {
                        thinkingMode = true;
                    }
                    const checkbox = document.getElementById('thinkingModeCheckbox');
                    if (checkbox) checkbox.checked = thinkingMode;
                    // 保存到服务器作为默认值
                    saveThinkingModeToServer(sessionId, thinkingMode);
                }
                
                await loadChatHistory(sessionId, true);
                
                const loadedBotMessages = document.querySelectorAll('#messages .message-item:not(.message-self)');
                const lastBotMessage = loadedBotMessages.length > 0 ? loadedBotMessages[loadedBotMessages.length - 1] : null;
                
                let hasPendingMessage = false;
                for (const [msgId, pending] of pendingMessages) {
                    if (pending.sessionId === sessionId) {
                        let isMessageCompleted = false;
                        
                        if (lastBotMessage) {
                            const senderEl = lastBotMessage.querySelector('.message-sender');
                            const contentEl = lastBotMessage.querySelector('.message-content');
                            
                            if (senderEl && senderEl.textContent === (pending.botName || pending.botId)) {
                                if (contentEl && pending.content) {
                                    const pendingText = pending.content.substring(0, 100);
                                    const existingText = contentEl.textContent.substring(0, 100);
                                    if (existingText.includes(pendingText) || pendingText.includes(existingText)) {
                                        isMessageCompleted = true;
                                        pendingMessages.delete(msgId);
                                    }
                                }
                            }
                        }
                        
                        if (!isMessageCompleted) {
                            hasPendingMessage = true;
                            restorePendingMessage(msgId, pending);
                        }
                    }
                }
                
                if (hasPendingMessage) {
                    showStopBtn();
                }
                
                setTimeout(() => {
                    const allLoading = document.querySelectorAll('.message-loading');
                    allLoading.forEach(el => {
                        const msgId = el.id.replace('loading-', '');
                        if (!streamingMessages.has(msgId)) {
                            el.remove();
                        }
                    });
                }, 100);
            }
            
            if (sessionUnreadCounts.has(sessionId)) {
                sessionUnreadCounts.delete(sessionId);
            }
            renderSessionList();
            updatePlaceholder();
        }
        
        function updateHeader(session = null) {
            if (!session) {
                session = sessions.find(s => s.id === currentSessionId);
            }
            
            if (!session || session.botIds.length === 0) {


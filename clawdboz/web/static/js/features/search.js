// Search feature

                document.getElementById('headerTitle').textContent = '选择一个会话';
                document.getElementById('headerAvatars').innerHTML = `
                    <div class="header-avatar bg-gradient-to-br from-blue-500 to-blue-600 text-white">
                        <i class="fas fa-robot"></i>
                    </div>
                `;
                return;
            }
            
            // 群聊显示多个头像叠加
            if (session.botIds.length > 1) {
                let avatarsHtml = '';
                const maxDisplay = 3; // 最多显示3个头像
                const displayBots = session.botIds.slice(0, maxDisplay);
                const remainingCount = session.botIds.length - maxDisplay;
                
                displayBots.forEach((botId, index) => {
                    const cfg = getBotAvatarConfig(botId);
                    const zIndex = maxDisplay - index;
                    avatarsHtml += `<div class="header-avatar ${cfg.color} text-white" style="z-index: ${zIndex};"><i class="fas ${cfg.icon}"></i></div>`;
                });
                
                if (remainingCount > 0) {
                    avatarsHtml += `<div class="header-avatar bg-gradient-to-br from-gray-500 to-gray-600 text-white" style="z-index: 0; font-size: 11px;">+${remainingCount}</div>`;
                }
                
                document.getElementById('headerAvatars').innerHTML = avatarsHtml;
            } else {
                // 单聊显示单个头像
                const firstBotId = session.botIds[0];
                const cfg = getBotAvatarConfig(firstBotId);
                
                document.getElementById('headerAvatars').innerHTML = `
                    <div class="header-avatar ${cfg.color} text-white"><i class="fas ${cfg.icon}"></i></div>
                `;
            }
            
            document.getElementById('headerTitle').textContent = session.name;
            
            // 根据单聊/群聊显示或隐藏@按钮（群聊显示，单聊隐藏）
            const mentionBtn = document.getElementById('mentionBtn');
            if (mentionBtn) {
                mentionBtn.style.display = session.botIds.length > 1 ? 'flex' : 'none';
            }
        }
        
        function updatePlaceholder() {
            const input = document.getElementById('messageInput');
            if (!currentSessionId || selectedBots.size === 0) {
                input.placeholder = '请先选择一个会话';
            } else {
                input.placeholder = `发送给 ${selectedBots.size} 个 Bot`;
            }
        }
        
        // ========== WebSocket ==========
        
        function connectWebSocket() {
            if (!token) return;
            
            // 如果已有连接，先关闭
            if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
                console.log('[WebSocket] 关闭现有连接');
                ws.close();
            }
            
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            console.log('[WebSocket] 创建新连接...');
            ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/chat?token=${token}`);
            
            ws.onopen = () => { 
                isConnected = true; 
            };
            
            ws.onmessage = (e) => handleMsg(JSON.parse(e.data));
            
            ws.onclose = () => { 
                isConnected = false;
                setTimeout(connectWebSocket, 5000); 
            };
        }
        
        function handleMsg(data) {
            // 如果消息有 chat_id 且与当前会话不匹配，记录未读数，不自动切换
            // 但飞书消息需要特殊处理（创建会话、显示消息）
            if (data.chat_id && data.chat_id !== currentSessionId && data.type !== 'feishu_message') {
                console.log(`[handleMsg] 消息 chat_id ${data.chat_id} 与当前会话 ${currentSessionId} 不匹配，记录未读`);
                const targetSession = sessions.find(s => s.id === data.chat_id);
                if (targetSession) {
                    const count = sessionUnreadCounts.get(data.chat_id) || 0;
                    sessionUnreadCounts.set(data.chat_id, count + 1);
                    renderSessionList();
                } else {
                    console.log(`[handleMsg] 未找到目标会话，丢弃消息`);
                }
                return;
            }
            
            // Debug logging for streaming messages
            if (data.type === 'start' || data.type === 'chunk' || data.type === 'done') {
                const contentPreview = data.content ? data.content.substring(0, 30).replace(/\n/g, '\\n') : '';
                const isThinking = data.is_thinking ? ' [THINKING]' : '';
                console.log(`[handleMsg] ${data.type}${isThinking}: seq=${data.seq}, content='${contentPreview}'`);
            }
            
            switch(data.type) {
                case 'start': createBotMsg(data); break;
                case 'chunk': appendChunk(data); break;
                case 'done': finishMsg(data); break;
                case 'error': showError(data); break;
                case 'mcp_message': createMCPMessage(data); break;
                case 'mcp_file': createMCPFile(data); break;
                case 'mcp_notify': createMCPNotify(data); break;
                case 'feishu_message': handleFeishuMessage(data); break;
            }
        }
        
        // ========== 消息处理 ==========
        
        const loadingSymbols = ['○', '◐', '●', '◑'];
        
        function createBotMsg(data) {
            const { msg_id, bot_id, bot_name } = data;
            
            // 检查消息是否已存在，防止重复创建
            const existingWrapper = document.getElementById(`msg-${msg_id}`);
            if (existingWrapper) {
                console.log(`[createBotMsg] 消息 ${msg_id} 已存在，跳过创建`);
                return;
            }
            
            const cfg = getBotAvatarConfig(bot_id);
            
            addTimeDivider();
            
            const wrapper = document.createElement('div');
            wrapper.className = 'message-item-wrapper';
            wrapper.id = `msg-${msg_id}`;
            const botAvatarHtml = cfg.image
                ? `<img src="${cfg.image}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">`
                : `<i class="fas ${cfg.icon}" style="color: white;"></i>`;
            const botAvatarClass = cfg.image
                ? 'message-avatar text-white'
                : `message-avatar ${cfg.color} text-white`;
            wrapper.innerHTML = `
                <div class="message-container">
                    <div class="message-item">
                        <div class="message-left">
                            <div class="${botAvatarClass}">
                                ${botAvatarHtml}
                            </div>
                        </div>
                        <div class="message-right">
                            <div class="message-info">
                                <span class="message-sender">${bot_name || bot_id}</span>
                                <span class="message-timestamp">${getTimeStr()}</span>
                            </div>
                            <div class="message-section streaming-empty" id="section-${msg_id}">
                                <div id="thinking-${msg_id}" class="thinking-section" style="display: none;">
                                    <div class="thinking-header" onclick="toggleThinking('${msg_id}')">
                                        <div class="thinking-header-left">
                                            <span class="thinking-toggle-btn">
                                                <i class="fas fa-chevron-right"></i>
                                            </span>
                                            <span class="thinking-label">
                                                <i class="fas fa-brain"></i>
                                                思考
                                            </span>
                                            <div class="thinking-preview">
                                                <span id="thinking-preview-${msg_id}" class="thinking-preview-text"></span>
                                            </div>
                                        </div>
                                    </div>
                                    <div id="thinking-content-${msg_id}" class="thinking-content"></div>
                                </div>
                                <div id="content-${msg_id}" class="message-content markdown-body"></div>
                                <div id="loading-${msg_id}" class="message-loading" style="margin-top: 0;">
                                    <span class="loading-indicator" style="color: #3370ff; font-size: 16px; display: inline-block; width: 20px; text-align: center;">${loadingSymbols[0]}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.getElementById('messages').appendChild(wrapper);
            smartScrollToBottom();
            
            const sessionId = currentSessionId;
            const contentEl = document.getElementById(`content-${msg_id}`);
            streamingMessages.set(msg_id, {
                element: contentEl,
                isStreaming: true,
                sessionId: sessionId,
                botId: bot_id,
                thinkingContent: '',
                mainContent: '',
                hasThinking: false
            });
            
            let symbolIndex = 0;
            const loadingInterval = setInterval(() => {
                const stream = streamingMessages.get(msg_id);
                if (!stream || !stream.isStreaming) {
                    clearInterval(loadingInterval);
                    return;
                }
                
                const loadingContainer = document.getElementById(`loading-${msg_id}`);
                if (loadingContainer) {
                    const loadingEl = loadingContainer.querySelector('.loading-indicator');
                    if (loadingEl) {
                        symbolIndex = (symbolIndex + 1) % loadingSymbols.length;
                        loadingEl.textContent = loadingSymbols[symbolIndex];
                    }
                }
            }, 300);
            
            streamingMessages.get(msg_id).loadingInterval = loadingInterval;
            activeStreams.add(msg_id);
            showStopBtn();
        }
        
        function appendChunk(data) {
            const stream = streamingMessages.get(data.msg_id);
            
            // 检查是否已接收过此 chunk（通过 msg_id + seq 唯一标识）
            const chunkId = `${data.msg_id}-${data.seq}`;
            if (receivedChunks.has(chunkId)) {
                console.log(`[appendChunk] 跳过重复 chunk: ${chunkId}`);
                return;
            }
            receivedChunks.add(chunkId);
            
            // 清理旧的 chunk 记录（保留最近1000个）
            if (receivedChunks.size > 1000) {
                const iterator = receivedChunks.values();
                for (let i = 0; i < 100; i++) {
                    const oldChunk = iterator.next().value;
                    if (oldChunk) receivedChunks.delete(oldChunk);
                }
            }
            
            if (data.tool_call) {
                handleToolCall(data.msg_id, data.tool_call);
            }
            
            if (stream && stream.isStreaming) {
                const isThinking = data.is_thinking;
                const content = data.content;
                
                if (isThinking) {
                    // 注意：后端发送的是完整思考内容，不是增量！
                    stream.thinkingContent = content;
                    stream.hasThinking = true;
                    
                    // 如果有思考内容，移除紧凑样式
                    if (content && content.trim()) {
                        const section = document.getElementById(`section-${data.msg_id}`);


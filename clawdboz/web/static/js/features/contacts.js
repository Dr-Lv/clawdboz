// Contacts feature

            if (!content) return;
            
            try {
                const res = await fetch(`/api/moments/${momentId}/comment`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token,
                        content,
                        sender_id: 'user',
                        sender_type: 'user'
                    })
                });
                const data = await res.json();
                if (data.success) {
                    input.value = '';
                    loadMoments();
                }
            } catch (e) {
                console.error('评论失败:', e);
            }
        }
        
        // 查看大图
        function viewImage(url) {
            window.open(url, '_blank');
        }
        
        // ========== 初始化 ==========
        
        async function init() {
            await initDB();
            await loadBots();
            await loadSessions();
            await loadUserProfile();
            restoreSidebarState();
            setupMessagesScroll();
            setupMobileViewport();
            initThinkingMode(); // 初始化思考模式
            connectWebSocket();
            setupEventListeners();
            setupSearchListeners();
        }
        
        async function loadBots() {
            try {
                const res = await fetch(`/api/bots?token=${token}`);
                bots = (await res.json()).bots || [];
                console.log('[loadBots] 加载完成:', bots.length, '个bots');
            } catch (e) { console.error('加载 Bot 失败:', e); }
        }
        
        async function loadSessions() {
            try {
                console.log('[Init] 从服务器加载会话...');
                const serverSessions = await loadSessionsFromServer();
                
                if (serverSessions.length > 0) {
                    sessions = serverSessions;
                    console.log(`[Init] 从服务器加载了 ${sessions.length} 个会话`);
                    
                    for (const session of sessions) {
                        await saveSessionToDB(session);
                    }
                } else {
                    console.log('[Init] 服务器没有会话，创建默认会话');
                    if (bots.length > 0) {
                        const defaultSession = createSession([bots[0].id], bots[0].name || bots[0].id);
                        sessions = [defaultSession];
                        await saveSessionToDB(defaultSession);
                        await saveSessionToServer(defaultSession);
                        // 发送成员介绍信息
                        await sendSessionIntro(defaultSession.id, defaultSession.botIds);
                    } else {
                        sessions = [];
                    }
                }
                
                renderSessionList();
                
                if (sessions.length > 0) {
                    await selectSession(sessions[0].id);
                }
            } catch (e) { 
                console.error('从服务器加载会话失败:', e);
                try {
                    sessions = await loadSessionsFromDB();
                    sessions.forEach(s => {
                        if (!s.mode) {
                            s.mode = s.botIds && s.botIds.length > 1 ? 'group' : 'single';
                        }
                    });
                    if (sessions.length > 0) {
                        renderSessionList();
                        await selectSession(sessions[0].id);
                    }
                } catch (e2) {
                    console.error('本地缓存也失败:', e2);
                }
            }
        }
        
        async function loadSessionsFromServer() {
            try {
                console.log('[Session] 从服务器加载会话...');
                const res = await fetch(`/api/sessions?token=${token}`);
                if (!res.ok) throw new Error('服务器返回错误');
                const data = await res.json();
                
                if (!data.sessions || data.sessions.length === 0) {
                    return [];
                }
                
                const serverSessions = [];
                
                for (const s of data.sessions) {
                    let botIds = s.bot_ids || [];
                    
                    if (botIds.length === 0 && bots.length > 0) {
                        botIds.push(bots[0].id);
                    }
                    
                    const sessionName = s.name || (s.updated_at ? `会话 ${new Date(s.updated_at * 1000).toLocaleDateString()}` : `会话 ${s.id.slice(-8)}`);
                    serverSessions.push({
                        id: s.id,
                        name: sessionName,
                        botIds: botIds,
                        mode: botIds.length > 1 ? 'group' : 'single',
                        firstBotId: botIds[0],
                        createdAt: s.updated_at * 1000,
                        timestamp: s.updated_at * 1000
                    });
                }
                
                return serverSessions;
            } catch (e) {
                console.error('从服务器加载会话失败:', e);
                return [];
            }
        }
        
        async function saveSessionToServer(session) {
            try {
                const body = {
                    id: session.id,
                    bot_ids: session.botIds
                };
                if (session.name) {
                    body.name = session.name;
                }
                const res = await fetch(`/api/sessions?token=${token}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body)
                });
                if (!res.ok) {
                    console.error('[Session] 保存会话失败:', await res.text());
                    return false;
                }
                return true;
            } catch (e) {
                console.error('[Session] 保存会话出错:', e);
                return false;
            }
        }
        
        async function loadMessagesFromServer(sessionId) {
            try {
                const session = sessions.find(s => s.id === sessionId);
                const botIds = session && session.botIds ? session.botIds : [];
                const botIdsParam = botIds.length > 0 ? 
                    `&bot_ids=${encodeURIComponent(botIds.join(','))}` : '';
                const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}?token=${token}${botIdsParam}`);
                if (!res.ok) throw new Error('服务器返回错误');
                
                const data = await res.json();
                if (!data.messages || data.messages.length === 0) {
                    return [];
                }
                
                return data.messages.map(m => ({
                    type: m.sender === 'user' ? 'user' : (m.sender === 'system' ? 'system' : 'bot'),
                    content: m.content,
                    timestamp: m.time * 1000,
                    botId: m.sender === 'user' || m.sender === 'system' ? null : m.sender
                })).filter(m => m.type !== 'system');  // 过滤掉系统消息，不显示在UI上
            } catch (e) {
                console.error('从服务器加载聊天记录失败:', e);
                return [];
            }
        }
        
        // ========== 会话列表渲染（折叠分组） ==========
        
        function renderSessionList() {
            const container = document.getElementById('botList');
            if (sessions.length === 0) {
                container.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.4);padding:20px;">点击右上角"+"创建会话</div>';
                return;
            }
            
            // 分离群聊和单聊
            const groupSessions = sessions.filter(s => s.botIds.length > 1);
            const singleSessions = sessions.filter(s => s.botIds.length === 1);
            
            // 单聊按 firstBotId 分组
            const groups = {};
            singleSessions.forEach(session => {
                const firstBotId = session.firstBotId || session.botIds[0];
                if (!groups[firstBotId]) {
                    groups[firstBotId] = [];
                }
                groups[firstBotId].push(session);
            });
            
            let html = '';
            
            // 1. 先显示群聊（不折叠，不归到任何bot下）
            if (groupSessions.length > 0) {
                html += `
                    <div class="sidebar-section-title" style="margin-top: 0;">
                        <span>群聊</span>
                        <span class="session-count" style="margin-left: auto; font-size: 11px; color: rgba(255,255,255,0.3); background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 10px;">${groupSessions.length}</span>
                    </div>
                `;
                
                html += groupSessions.map(session => {
                    const isActive = session.id === currentSessionId;
                    const avatarHtml = generateGroupAvatarHtml(session.botIds);
                    const unreadCount = sessionUnreadCounts.get(session.id) || 0;
                    const unreadBadge = unreadCount > 0 ? `<div class="session-unread-badge">${unreadCount}</div>` : '';
                    return `
                        <div class="sidebar-item ${isActive ? 'active' : ''}" data-session-id="${session.id}" oncontextmenu="showSessionContextMenu(event, '${session.id}')">
                            <div class="sidebar-delete-btn" onclick="event.stopPropagation(); confirmDeleteSession('${session.id}', event);">
                                <i class="fas fa-trash-alt"></i> 删除
                            </div>
                            <div class="sidebar-item-content" onclick="selectSessionWithMobileClose('${session.id}')">
                                ${avatarHtml}
                                <div class="sidebar-info" style="overflow:hidden;">
                                    <div class="sidebar-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${session.name}">${session.name}</div>
                                    <div class="sidebar-subtitle">${session.botIds.length} 个 Bot · ${formatTime(session.createdAt)}</div>
                                </div>
                                ${unreadBadge}
                            </div>
                        </div>
                    `;
                }).join('');
            }
            
            // 2. 再显示单聊（按Bot分组折叠）
            if (Object.keys(groups).length > 0) {
                html += `
                    <div class="sidebar-section-title">
                        <span>单聊</span>
                        <span class="collapse-btn" onclick="toggleAllGroups()" title="全部展开/折叠">
                            <i class="fas fa-expand-alt" id="collapseAllIcon"></i>
                        </span>
                    </div>
                `;
                
                for (const [botId, botSessions] of Object.entries(groups)) {
                    const bot = bots.find(b => b.id === botId);
                    const botName = bot?.name || botId;
                    // 使用自定义头像或默认配置
                    const cfg = getBotAvatarConfig(botId);
                    
                    const isCollapsed = collapsedGroups.has(botId);
                    
                    html += `
                        <div class="bot-group">
                            <div class="bot-group-header ${isCollapsed ? 'collapsed' : ''}" id="bot-group-${botId}" onclick="toggleBotGroup('${botId}')">
                                <i class="fas fa-chevron-down" id="bot-group-icon-${botId}" style="transform: ${isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)'};"></i>
                                <div class="bot-avatar-small ${cfg.color} text-white">
                                    <i class="fas ${cfg.icon}"></i>
                                </div>
                                <span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${botName}</span>
                                <span class="session-count">${botSessions.length}</span>
                            </div>
                            <div class="bot-group-sessions ${isCollapsed ? 'collapsed' : ''}" id="bot-group-sessions-${botId}">
                                ${botSessions.map(session => {
                                    const isActive = session.id === currentSessionId;
                                    const unreadCount = sessionUnreadCounts.get(session.id) || 0;
                                    const unreadBadge = unreadCount > 0 ? `<div class="session-unread-badge">${unreadCount}</div>` : '';
                                    return `
                                        <div class="sidebar-item ${isActive ? 'active' : ''}" data-session-id="${session.id}" oncontextmenu="showSessionContextMenu(event, '${session.id}')">
                                            <div class="sidebar-delete-btn" onclick="event.stopPropagation(); confirmDeleteSession('${session.id}', event);">
                                                <i class="fas fa-trash-alt"></i> 删除
                                            </div>
                                            <div class="sidebar-item-content" onclick="selectSessionWithMobileClose('${session.id}')" style="padding-left: 36px;">
                                                <div class="sidebar-info" style="overflow:hidden;">
                                                    <div class="sidebar-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${session.name}">${session.name}</div>
                                                    <div class="sidebar-subtitle">${formatTime(session.createdAt)}</div>
                                                </div>
                                                ${unreadBadge}
                                            </div>
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                        </div>


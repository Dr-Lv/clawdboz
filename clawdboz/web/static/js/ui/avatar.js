// Avatar management

        
        async function confirmEditBot() {
            const botId = document.getElementById('editBotId').value;
            const name = document.getElementById('editBotName').value.trim();
            const bio = document.getElementById('editBotBio').value.trim();
            const avatarColor = document.getElementById('editBotAvatarColor').value;
            const avatarIcon = document.getElementById('editBotAvatarIcon').value;
            
            if (!botId) {
                showToast('Bot ID 不能为空', 'error');
                return;
            }
            
            if (!token) {
                showToast('未登录或 Token 无效', 'error');
                return;
            }
            
            try {
                console.log('[Edit Bot] 发送请求:', { bot_id: botId, name, bio, avatar_color: avatarColor, avatar_icon: avatarIcon });
                const response = await fetch(`/api/bots/${botId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token, name, bio, avatar_color: avatarColor, avatar_icon: avatarIcon })
                });
                
                let result;
                try {
                    result = await response.json();
                } catch (jsonErr) {
                    const text = await response.text();
                    console.error('[Edit Bot] 解析响应失败:', jsonErr, '响应内容:', text);
                    showToast('服务器返回格式错误: ' + text.substring(0, 100), 'error');
                    return;
                }
                
                console.log('[Edit Bot] 响应:', result);
                
                if (response.ok && result.success) {
                    console.log('[Edit Bot] 修改成功，刷新列表');
                    // 更新本地 bots 数据
                    const botIndex = bots.findIndex(b => b.id === botId);
                    if (botIndex >= 0) {
                        bots[botIndex].name = name || botId;
                        bots[botIndex].bio = bio;
                        bots[botIndex].avatar_color = avatarColor;
                        bots[botIndex].avatar_icon = avatarIcon;
                    }
                    // 刷新通讯录列表和详情
                    renderContactsList();
                    selectContact(botId);
                    // 刷新会话列表（可能显示了 bot 名称）
                    renderSessionList();
                    closeEditBotModal();
                    showToast('Bot 修改成功', 'success');
                } else {
                    console.log('[Edit Bot] 修改失败:', result.error);
                    showToast(result.error || '修改失败', 'error');
                }
            } catch (e) {
                console.error('修改 Bot 失败:', e);
                showToast('修改失败: ' + (e.message || '未知错误'), 'error');
            }
        }
        
        // ========== 通讯录功能 ==========
        
        async function loadSidebarContacts() {
            console.log('[loadSidebarContacts] 开始加载侧边栏通讯录...');
            try {
                // 如果 bots 已经加载，直接渲染
                if (bots.length === 0) {
                    // 从 API 重新加载
                    const response = await fetch(`/api/bots?token=${token}`);
                    if (response.ok) {
                        const data = await response.json();
                        bots = data.bots || [];
                        console.log('[loadSidebarContacts] 加载到', bots.length, '个 Bot');
                    }
                }
                renderSidebarContactsList();
            } catch (e) {
                console.error('[loadSidebarContacts] 加载失败:', e);
                showToast('加载通讯录失败', 'error');
            }
        }
        
        function renderSidebarContactsList() {
            const container = document.getElementById('sidebarContactsList');
            
            if (bots.length === 0) {
                container.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.4);padding:20px;">暂无可用 Bot</div>';
                return;
            }
            
            const searchTerm = document.getElementById('sidebarContactsSearch')?.value?.toLowerCase() || '';
            
            const filteredBots = bots.filter(bot => {
                const name = (bot.name || bot.id).toLowerCase();
                return name.includes(searchTerm);
            });
            
            // 更新数量显示
            const countEl = document.getElementById('sidebarContactsCount');
            if (countEl) {
                countEl.textContent = filteredBots.length;
            }
            
            container.innerHTML = filteredBots.map((bot, i) => {
                const cfg = getBotAvatarConfig(bot.id);
                const isActive = bot.id === selectedContactId;
                
                return `
                    <div class="sidebar-item ${isActive ? 'active' : ''}" onclick="selectSidebarContact('${bot.id}')" style="border-left: 3px solid transparent;">
                        <div class="sidebar-item-content">
                            <div class="sidebar-avatar ${cfg.color} text-white" style="width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0;">
                                <i class="fas ${cfg.icon}"></i>
                            </div>
                            <div class="sidebar-info" style="overflow: hidden;">
                                <div class="sidebar-title" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${bot.name || bot.id}">${bot.name || bot.id}</div>
                                <div class="sidebar-subtitle">@${bot.id}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        function filterSidebarContacts() {
            renderSidebarContactsList();
        }
        
        async function selectSidebarContact(botId) {
            selectedContactId = botId;
            renderSidebarContactsList();
            
            // 在右侧主区域显示 Bot 详情（替换聊天内容）
            const bot = bots.find(b => b.id === botId);
            if (!bot) return;
            
            // 使用自定义头像或默认配置
            const cfg = getBotAvatarConfig(botId);
            
            // 隐藏消息列表，显示 Bot 详情
            document.getElementById('messages').style.display = 'none';
            document.querySelector('.input-area').style.display = 'none';
            
            // 创建或显示 Bot 详情面板
            let botDetailPanel = document.getElementById('botDetailPanel');
            if (!botDetailPanel) {
                botDetailPanel = document.createElement('div');
                botDetailPanel.id = 'botDetailPanel';
                botDetailPanel.className = 'messages-container';
                botDetailPanel.style.display = 'flex';
                botDetailPanel.style.alignItems = 'center';
                botDetailPanel.style.justifyContent = 'center';
                botDetailPanel.style.background = 'var(--bg)';
                document.querySelector('.messages-wrapper').appendChild(botDetailPanel);
            }
            
            // 加载 Skills 和 Memory
            let skills = [];
            let memory = '';
            try {
                const res = await fetch(`/api/bots/${botId}?token=${token}`);
                if (res.ok) {
                    const data = await res.json();
                    skills = data.skills || [];
                    memory = data.memory || '';
                }
            } catch (e) {
                console.error('加载 Bot 详情失败:', e);
            }
            
            // 渲染 Bot 详情
            botDetailPanel.innerHTML = `
                <div class="contacts-detail-card" style="max-width: 400px; width: 100%;">
                    <div class="contacts-detail-avatar ${cfg.color} text-white" style="width: 80px; height: 80px; font-size: 36px;">
                        <i class="fas ${cfg.icon}"></i>
                    </div>
                    <div class="contacts-detail-name">${bot.name || bot.id}</div>
                    <div class="contacts-detail-id">ID: ${bot.id}</div>
                    ${bot.bio ? `<div style="text-align: center; color: var(--text-secondary); font-size: 14px; margin: 12px 20px; line-height: 1.5;">${bot.bio}</div>` : ''}
                    
                    ${skills.length > 0 ? `
                    <div class="contacts-detail-section" style="margin-top: 20px;">
                        <div class="contacts-detail-section-title">
                            <i class="fas fa-puzzle-piece"></i> Skills
                        </div>
                        <div class="contacts-detail-skills-list">
                            ${skills.map(skill => `
                                <span class="contacts-detail-skill-tag">
                                    <i class="fas fa-puzzle-piece"></i>${skill}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                    ` : ''}
                    
                    ${memory ? `


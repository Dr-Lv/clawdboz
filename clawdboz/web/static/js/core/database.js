// Database operations

                
                await new Promise((resolve, reject) => {
                    const request = sessionStore.delete(sessionId);
                    request.onsuccess = () => resolve();
                    request.onerror = () => reject(request.error);
                });
                
                const index = messageStore.index('sessionId');
                const cursorRequest = index.openCursor(IDBKeyRange.only(sessionId));
                
                await new Promise((resolve, reject) => {
                    cursorRequest.onsuccess = (event) => {
                        const cursor = event.target.result;
                        if (cursor) {
                            cursor.delete();
                            cursor.continue();
                        } else {
                            resolve();
                        }
                    };
                    cursorRequest.onerror = () => reject(cursorRequest.error);
                });
            } catch (e) {
                console.error('[删除会话] 本地删除失败:', e);
            }
            
            return true;
        }
        
        function createSession(botIds, name = null) {
            const id = generateSessionId();
            const botList = bots.filter(b => botIds.includes(b.id));
            const sessionName = name || botList.map(b => b.name || b.id).join(', ');
            
            return {
                id: id,
                name: sessionName,
                botIds: Array.from(botIds),
                mode: botIds.length > 1 ? 'group' : 'single',
                createdAt: Date.now(),
                firstBotId: botIds[0]
            };
        }
        
        // 发送会话成员介绍信息给所有 bots
        async function sendSessionIntro(sessionId, botIds) {
            try {
                // 构建成员列表（包含用户和所有 bots）
                const members = [];
                
                // 添加用户信息
                members.push({
                    type: 'user',
                    id: 'user',
                    name: userProfile.name || '用户',
                    bio: userProfile.bio || ''
                });
                
                // 添加每个 bot 的信息
                for (const botId of botIds) {
                    const bot = bots.find(b => b.id === botId);
                    if (bot) {
                        members.push({
                            type: 'bot',
                            id: bot.id,
                            name: bot.name || bot.id,
                            bio: bot.bio || ''
                        });
                    }
                }
                
                // 发送给服务器
                const response = await fetch(`/api/sessions/${sessionId}/intro?token=${token}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ members })
                });
                
                if (response.ok) {
                    console.log(`[Session Intro] 已发送会话 ${sessionId} 的成员介绍`);
                } else {
                    console.error('[Session Intro] 发送失败:', await response.text());
                }
            } catch (e) {
                console.error('[Session Intro] 错误:', e);
            }
        }
        
        function saveMessageToDB(messageData) {
            if (!db || !currentSessionId) return;
            
            const transaction = db.transaction(['messages'], 'readwrite');
            const store = transaction.objectStore('messages');
            
            const record = {
                ...messageData,
                timestamp: Date.now(),
                sessionId: currentSessionId
            };
            
            store.add(record);
        }
        
        async function loadMessagesFromDB(sessionId) {
            if (!db || !sessionId) return [];
            
            return new Promise((resolve, reject) => {
                const transaction = db.transaction(['messages'], 'readonly');
                const store = transaction.objectStore('messages');
                const index = store.index('sessionId');
                
                const request = index.getAll(sessionId);
                request.onsuccess = () => {
                    const messages = request.result.sort((a, b) => a.timestamp - b.timestamp);
                    resolve(messages);
                };
                request.onerror = () => reject(request.error);
            });
        }
        
        // ========== 自动命名功能 ==========
        
        async function getSessionMessageCount(sessionId) {
            if (!db || !sessionId) return 0;
            
            const messages = await loadMessagesFromDB(sessionId);
            return messages.length;
        }
        
        async function autoRenameSession(sessionId) {
            const session = sessions.find(s => s.id === sessionId);
            if (!session) return;
            
            const messageCount = await getSessionMessageCount(sessionId);
            
            // 如果消息数超过4条且没有自定义名称（使用默认名称），则自动命名
            if (messageCount > 4) {
                const messages = await loadMessagesFromDB(sessionId);
                const userMessages = messages.filter(m => m.type === 'user');
                
                if (userMessages.length > 0) {
                    // 获取最后一条用户消息作为命名依据
                    const lastUserMsg = userMessages[userMessages.length - 1];
                    const content = lastUserMsg.content || '';
                    
                    // 提取前15个字符作为名称
                    let newName = content.trim().substring(0, 15);
                    if (content.length > 15) newName += '...';
                    
                    // 如果名称有效且与当前名称不同，则更新
                    if (newName && newName !== session.name) {
                        // 检查是否是默认名称模式（Bot名称或日期格式）
                        const isDefaultName = bots.some(b => session.name === b.name) ||
                                             session.name.includes('会话') ||
                                             session.name.includes(',');
                        
                        if (isDefaultName) {
                            session.name = newName;
                            await saveSessionToDB(session);
                            await saveSessionToServer(session);
                            renderSessionList();
                            if (currentSessionId === sessionId) {
                                updateHeader(session);
                            }
                        }
                    }
                }
            }
        }
        
        // ========== 标签切换 ==========

        function switchTab(tab) {
            console.log('[Tab] 切换到:', tab);

            // 更新标签样式
            document.querySelectorAll('.tab-item').forEach(item => {
                item.classList.remove('active');
            });
            document.querySelector(`.tab-item[data-tab="${tab}"]`).classList.add('active');

            // 隐藏通讯录覆盖层
            document.getElementById('contactsOverlay').classList.remove('active');
            
            // 隐藏所有主视图
            document.getElementById('messagesView').style.display = 'none';
            document.getElementById('contactsView').style.display = 'none';
            document.getElementById('momentsView').style.display = 'none';

            // 隐藏所有覆盖层
            document.getElementById('contactsOverlay').classList.remove('active');
            document.getElementById('momentsOverlay').classList.remove('active');
            
            // 隐藏 Bot 详情面板和朋友圈面板
            const botDetailPanel = document.getElementById('botDetailPanel');
            if (botDetailPanel) botDetailPanel.style.display = 'none';
            const momentsPanel = document.getElementById('momentsPanel');
            if (momentsPanel) momentsPanel.style.display = 'none';
            
            // 显示/隐藏聊天标题栏


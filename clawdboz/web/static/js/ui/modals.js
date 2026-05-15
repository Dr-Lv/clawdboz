// Modal dialogs

                sessionsEl.classList.add('collapsed');
                groupEl.classList.add('collapsed');
                iconEl.style.transform = 'rotate(-90deg)';
                collapsedGroups.add(botId);
            }
        }
        
        function toggleAllGroups() {
            allGroupsCollapsed = !allGroupsCollapsed;
            const icon = document.getElementById('collapseAllIcon');
            
            if (allGroupsCollapsed) {
                icon.className = 'fas fa-compress-alt';
                // 折叠所有分组
                const groups = document.querySelectorAll('.bot-group-sessions');
                groups.forEach(el => el.classList.add('collapsed'));
                const headers = document.querySelectorAll('.bot-group-header');
                headers.forEach(el => el.classList.add('collapsed'));
                const icons = document.querySelectorAll('.bot-group-header i');
                icons.forEach(el => el.style.transform = 'rotate(-90deg)');
            } else {
                icon.className = 'fas fa-expand-alt';
                // 展开所有分组
                const groups = document.querySelectorAll('.bot-group-sessions');
                groups.forEach(el => el.classList.remove('collapsed'));
                const headers = document.querySelectorAll('.bot-group-header');
                headers.forEach(el => el.classList.remove('collapsed'));
                const icons = document.querySelectorAll('.bot-group-header i');
                icons.forEach(el => el.style.transform = 'rotate(0deg)');
            }
        }
        
        // ========== 加载聊天记录 ==========
        
        let isLoadingChatHistory = false;
        
        async function loadChatHistory(sessionId = null, force = false) {
            const sid = sessionId || currentSessionId;
            if (!sid) {
                isLoadingChatHistory = false;
                return;
            }
            
            if (isLoadingChatHistory && !force) {
                console.log(`[loadChatHistory] 正在加载中，跳过重复调用: ${sid}`);
                return;
            }
            isLoadingChatHistory = true;
            
            let messages = await loadMessagesFromServer(sid);
            
            if (messages.length === 0) {
                messages = await loadMessagesFromDB(sid);
            } else {
                for (const msg of messages) {
                    await saveMessageToDB({...msg, sessionId: sid});
                }
            }
            
            document.getElementById('messages').innerHTML = '';
            lastMsgTime = null;
            
            if (messages.length === 0) {
                document.getElementById('messages').innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">🤖</div>
                        <div>开始新的对话</div>
                    </div>
                `;
                isLoadingChatHistory = false;
                return;
            }
            
            messages.forEach(msg => {
                if (msg.type === 'user') {
                    restoreUserMessage(msg.content, msg.timestamp);
                } else if (msg.type === 'bot') {
                    restoreBotMessage(msg);
                }
            });
            
            smartScrollToBottom();
            
            const loadingElements = document.querySelectorAll('.message-loading');
            loadingElements.forEach(el => {
                console.log(`[loadChatHistory] 移除残留的 loading 元素: ${el.id}`);
                el.remove();
            });
            
            isLoadingChatHistory = false;
            
            // 检查是否需要自动命名
            await autoRenameSession(sid);
        }
        
        function restoreUserMessage(content, timestamp) {
            const time = new Date(timestamp);
            const timeStr = `${time.getMonth()+1}月${time.getDate()}日 ${String(time.getHours()).padStart(2,'0')}:${String(time.getMinutes()).padStart(2,'0')}`;
            
            if (!lastMsgTime || timestamp - lastMsgTime > 5 * 60 * 1000) {
                const div = document.createElement('div');
                div.className = 'message-time-divider';
                div.textContent = timeStr;
                document.getElementById('messages').appendChild(div);
            }
            lastMsgTime = timestamp;
            
            const wrapper = document.createElement('div');
            wrapper.className = 'message-item-wrapper';
            wrapper.innerHTML = `
                <div class="message-container">
                    <div class="message-item message-self">
                        <div class="message-left">
                            <div class="message-avatar bg-gradient-to-br from-blue-500 to-blue-600 text-white">
                                <i class="fas fa-user" style="color: white;"></i>
                            </div>
                        </div>
                        <div class="message-right">
                            <div class="message-section">
                                <div class="message-content markdown-body">${marked.parse(content)}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.getElementById('messages').appendChild(wrapper);
        }
        
        function restoreBotMessage(msg) {
            const bot = bots.find(b => b.id === msg.botId);
            const cfg = getBotAvatarConfig(msg.botId);
            
            const time = new Date(msg.timestamp);
            const timeStr = `${time.getMonth()+1}月${time.getDate()}日 ${String(time.getHours()).padStart(2,'0')}:${String(time.getMinutes()).padStart(2,'0')}`;
            
            if (!lastMsgTime || msg.timestamp - lastMsgTime > 5 * 60 * 1000) {
                const div = document.createElement('div');
                div.className = 'message-time-divider';
                div.textContent = timeStr;
                document.getElementById('messages').appendChild(div);
            }
            lastMsgTime = msg.timestamp;
            
            let thinkingHtml = '';
            let mainContent = msg.content || '';
            const thinkingMatch = mainContent.match(/💭 \*\*思考过程\*\*\n```\n([\s\S]*?)\n```\n\n/);
            
            if (thinkingMatch) {
                const thinkingText = thinkingMatch[1];
                const thinkingId = `hist-think-${msg.msgId || Date.now()}`;
                mainContent = mainContent.replace(thinkingMatch[0], '');
                
                thinkingHtml = `
                    <div id="thinking-${thinkingId}" class="thinking-section finished" style="display: block; margin-bottom: 8px;">
                        <div class="thinking-header" onclick="toggleThinking('${thinkingId}')">
                            <div class="thinking-header-left">
                                <span class="thinking-toggle-btn">
                                    <i class="fas fa-chevron-right"></i>
                                </span>
                                <span class="thinking-label">
                                    <i class="fas fa-brain"></i>
                                    思考
                                </span>
                            </div>
                        </div>
                        <div id="thinking-content-${thinkingId}" class="thinking-content" style="display: none;">
                            ${marked.parse('```\n' + thinkingText + '\n```')}
                        </div>
                    </div>
                `;
            }
            
            const wrapper = document.createElement('div');
            wrapper.className = 'message-item-wrapper';
            if (msg.msgId) {
                wrapper.id = `msg-${msg.msgId}`;
            }
            wrapper.innerHTML = `
                <div class="message-container">
                    <div class="message-item">
                        <div class="message-left">
                            <div class="message-avatar ${cfg.color} text-white">
                                <i class="fas ${cfg.icon}" style="color: white;"></i>
                            </div>
                        </div>
                        <div class="message-right">
                            <div class="message-info">
                                <span class="message-sender">${bot?.name || msg.botId}</span>
                                <span class="message-timestamp">${timeStr}</span>
                            </div>
                            <div class="message-section">
                                ${thinkingHtml}
                                <div class="message-content markdown-body">${marked.parse(mainContent)}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.getElementById('messages').appendChild(wrapper);
        }
        
        // ========== 搜索功能 ==========
        
        function toggleSearch() {
            isSearchOpen = !isSearchOpen;
            const overlay = document.getElementById('searchOverlay');
            if (isSearchOpen) {
                overlay.classList.add('show');
                document.getElementById('searchInput').focus();
            } else {
                overlay.classList.remove('show');
                clearSearch();
            }
        }

        // 调试功能：触发定时任务执行流程
        async function triggerDebugTask() {
            if (!currentSessionId || selectedBots.size === 0) {
                showToast('请先选择一个聊天和 Bot', 'error');
                return;
            }

            const botId = Array.from(selectedBots)[0];
            showToast(`正在触发 Bot ${botId} 的定时任务调试...`, 'info');

            try {
                const response = await fetch(`/api/debug/trigger-task?token=${encodeURIComponent(token)}&chat_id=${encodeURIComponent(currentSessionId)}&bot_id=${encodeURIComponent(botId)}`, {
                    method: 'POST'
                });

                const result = await response.json();
                if (result.success) {
                    showToast(`调试任务已执行: ${result.message}`, 'success');
                } else {
                    showToast(`调试失败: ${result.error || '未知错误'}`, 'error');
                }
            } catch (e) {
                showToast(`请求失败: ${e.message}`, 'error');
            }
        }
        
        function closeSearch() {
            isSearchOpen = false;
            document.getElementById('searchOverlay').classList.remove('show');
            clearSearch();
        }
        
        function clearSearch() {
            document.querySelectorAll('.search-highlight, .search-current').forEach(el => {
                const parent = el.parentNode;
                parent.replaceChild(document.createTextNode(el.textContent), el);
                parent.normalize();
            });
            searchResults = [];
            currentSearchIndex = -1;
            updateSearchCount();
        }
        
        function performSearch() {
            clearSearch();
            
            const query = document.getElementById('searchInput').value.trim().toLowerCase();
            if (!query) {
                updateSearchCount();
                return;
            }
            
            const messageContents = document.querySelectorAll('.message-content');
            messageContents.forEach((contentEl, messageIndex) => {
                const text = contentEl.textContent.toLowerCase();
                if (text.includes(query)) {
                    highlightText(contentEl, query, messageIndex);
                }
            });
            
            updateSearchCount();
            
            if (searchResults.length > 0) {
                currentSearchIndex = 0;
                highlightCurrentResult();
            }
        }
        
        function highlightText(element, query, messageIndex) {
            const walker = document.createTreeWalker(
                element,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            
            const textNodes = [];
            let node;
            while (node = walker.nextNode()) {
                if (node.textContent.toLowerCase().includes(query)) {
                    textNodes.push(node);
                }
            }
            
            textNodes.forEach(node => {
                const text = node.textContent;
                const lowerText = text.toLowerCase();
                const parts = [];
                let lastIndex = 0;
                let index;
                
                while ((index = lowerText.indexOf(query, lastIndex)) !== -1) {
                    if (index > lastIndex) {
                        parts.push(document.createTextNode(text.substring(lastIndex, index)));
                    }
                    
                    const highlight = document.createElement('span');
                    highlight.className = 'search-highlight';
                    highlight.textContent = text.substring(index, index + query.length);
                    highlight.dataset.resultIndex = searchResults.length;
                    parts.push(highlight);
                    
                    searchResults.push({
                        element: highlight,
                        messageIndex: messageIndex
                    });
                    
                    lastIndex = index + query.length;
                }
                
                if (lastIndex < text.length) {
                    parts.push(document.createTextNode(text.substring(lastIndex)));
                }
                
                const parent = node.parentNode;
                parts.forEach(part => parent.insertBefore(part, node));
                parent.removeChild(node);
            });
        }
        
        function updateSearchCount() {
            const countEl = document.getElementById('searchCount');
            if (searchResults.length === 0) {
                countEl.textContent = '';
            } else {
                countEl.textContent = `${currentSearchIndex + 1}/${searchResults.length}`;
            }
            
            const navBtns = document.querySelectorAll('.search-nav-btn');
            navBtns.forEach(btn => btn.disabled = searchResults.length === 0);
        }
        
        function highlightCurrentResult() {
            document.querySelectorAll('.search-current').forEach(el => {
                el.classList.remove('search-current');
            });
            
            if (currentSearchIndex >= 0 && currentSearchIndex < searchResults.length) {
                const result = searchResults[currentSearchIndex];
                result.element.classList.add('search-current');
                result.element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            
            updateSearchCount();
        }
        
        function nextSearchResult() {
            if (searchResults.length === 0) return;
            currentSearchIndex = (currentSearchIndex + 1) % searchResults.length;
            highlightCurrentResult();
        }
        
        function prevSearchResult() {
            if (searchResults.length === 0) return;
            currentSearchIndex = (currentSearchIndex - 1 + searchResults.length) % searchResults.length;
            highlightCurrentResult();
        }
        
        // ========== 侧边栏控制 ==========
        
        let sidebarCollapsed = false;
        
        function toggleSidebar() {
            sidebarCollapsed = !sidebarCollapsed;
            const sidebar = document.getElementById('sidebar');
            const icon = document.getElementById('sidebarToggleIcon');
            
            if (sidebarCollapsed) {
                sidebar.classList.add('collapsed');
                icon.classList.remove('fa-chevron-left');
                icon.classList.add('fa-chevron-right');
                localStorage.setItem('sidebarCollapsed', 'true');
            } else {
                sidebar.classList.remove('collapsed');
                icon.classList.remove('fa-chevron-right');
                icon.classList.add('fa-chevron-left');
                localStorage.setItem('sidebarCollapsed', 'false');
            }
        }
        
        function restoreSidebarState() {
            const collapsed = localStorage.getItem('sidebarCollapsed') === 'true';
            if (collapsed) {
                sidebarCollapsed = true;
                const sidebar = document.getElementById('sidebar');


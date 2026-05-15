// Main application entry point


                        if (section) {
                            section.classList.remove('streaming-empty');
                        }
                    }
                    
                    const thinkingSection = document.getElementById(`thinking-${data.msg_id}`);
                    if (thinkingSection) {
                        thinkingSection.style.display = 'block';
                    }
                    
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = marked.parse(stream.thinkingContent);
                    const plainText = (tempDiv.textContent || tempDiv.innerText || '').trim();
                    
                    const previewText = document.getElementById(`thinking-preview-${data.msg_id}`);
                    if (previewText) {
                        const displayText = plainText + '    ' + plainText;
                        previewText.textContent = displayText;
                        
                        const charCount = plainText.length;
                        const duration = Math.max(3, charCount / 3);
                        previewText.style.animationDuration = `${duration}s`;
                    }
                    
                    const thinkingContent = document.getElementById(`thinking-content-${data.msg_id}`);
                    if (thinkingContent) {
                        let html = marked.parse(stream.thinkingContent);
                        html = processCode(html);
                        thinkingContent.innerHTML = html;
                        thinkingContent.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
                    }
                } else {
                    // 注意：后端发送的是完整内容（从开头到当前），不是增量！
                    // 因此这里应该用赋值 = 而不是追加 +=
                    stream.mainContent = content;
                    
                    // 如果有内容，移除紧凑样式
                    if (content && content.trim()) {
                        const section = document.getElementById(`section-${data.msg_id}`);
                        if (section) {
                            section.classList.remove('streaming-empty');
                        }
                    }
                    
                    // 完整重新渲染内容
                    let html = marked.parse(stream.mainContent);
                    html = processCode(html);
                    html = processImages(html);
                    stream.element.innerHTML = html;
                    stream.element.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
                }
                
                smartScrollToBottom();
                
                if (pendingMessages.has(data.msg_id)) {
                    const pending = pendingMessages.get(data.msg_id);
                    let fullContent = '';
                    if (stream.thinkingContent) {
                        fullContent += `💭 **思考过程**\n\`\`\`\n${stream.thinkingContent}\n\`\`\`\n\n`;
                    }
                    fullContent += stream.mainContent;
                    pending.content = marked.parse(fullContent);
                    pendingMessages.set(data.msg_id, pending);
                }
            }
        }
        
        function finishMsg(data) {
            let stream = streamingMessages.get(data.msg_id);
            let content = null;
            let messageSessionId = currentSessionId;
            
            if (stream) {
                const loadingContainer = document.getElementById(`loading-${data.msg_id}`);
                if (loadingContainer) {
                    loadingContainer.remove();
                }
                
                if (stream.element) {
                    stream.element.style.display = 'none';
                    stream.element.offsetHeight;
                    stream.element.style.display = '';
                }
                
                stream.isStreaming = false;
                streamingMessages.delete(data.msg_id);
                activeStreams.delete(data.msg_id);
                messageTools.delete(data.msg_id);
                
                // 清理该消息的 chunk 记录
                for (const chunkId of receivedChunks) {
                    if (chunkId.startsWith(`${data.msg_id}-`)) {
                        receivedChunks.delete(chunkId);
                    }
                }
                
                if (stream.loadingInterval) {
                    clearInterval(stream.loadingInterval);
                    delete stream.loadingInterval;
                }
                
                messageSessionId = stream.sessionId || currentSessionId;
                
                let finalMainContent = stream.mainContent;
                
                if (stream.hasThinking && stream.thinkingContent) {
                    const thinkingSection = document.getElementById(`thinking-${data.msg_id}`);
                    if (thinkingSection) {
                        thinkingSection.style.display = 'block';
                        if (!thinkingSection.classList.contains('finished')) {
                            thinkingSection.classList.add('finished');
                        }
                    }
                    
                    const previewText = document.getElementById(`thinking-preview-${data.msg_id}`);
                    if (previewText) {
                        previewText.classList.add('stopped');
                        previewText.style.animation = 'none';
                        previewText.style.animationDuration = '';
                        previewText.style.transform = 'none';
                        void previewText.offsetWidth;
                    }
                    
                    content = `💭 **思考过程**\n\`\`\`\n${stream.thinkingContent}\n\`\`\`\n\n${finalMainContent}`;
                } else {
                    content = stream.mainContent || stream.element.innerHTML;
                }
                
                smartScrollToBottom();
            } else {
                const pending = pendingMessages.get(data.msg_id);
                if (pending) {
                    messageSessionId = pending.sessionId;
                    content = data.final || '';
                    pendingMessages.delete(data.msg_id);
                    
                    const loadingContainer = document.getElementById(`loading-${data.msg_id}`);
                    if (loadingContainer) {
                        loadingContainer.remove();
                    }
                    
                    if (messageSessionId === currentSessionId && content) {
                        restoreBotMessageFromPending(data.msg_id, data.bot_id, data.bot_name || data.bot_id, content);
                    }
                }
            }
            
            if (content) {
                const botId = data.bot_id || (stream ? stream.botId : null);
                
                if (botId && messageSessionId && db) {
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = content;
                    const textContent = tempDiv.textContent || tempDiv.innerText || content;
                    
                    const transaction = db.transaction(['messages'], 'readwrite');
                    const store = transaction.objectStore('messages');
                    const index = store.index('sessionId');
                    const request = index.getAll(messageSessionId);
                    
                    request.onsuccess = (event) => {
                        const records = event.target.result;
                        const existingRecord = records.find(r => r.msgId === data.msg_id);
                        
                        if (existingRecord) {
                            existingRecord.content = textContent;
                            existingRecord.timestamp = Date.now();
                            store.put(existingRecord);
                        } else {
                            store.add({
                                type: 'bot',
                                botId: botId,
                                content: textContent,
                                timestamp: Date.now(),
                                sessionId: messageSessionId,
                                msgId: data.msg_id
                            });
                        }
                    };
                }
            }
            
            const thinkingSection = document.getElementById(`thinking-${data.msg_id}`);
            if (thinkingSection) {
                if (!thinkingSection.classList.contains('finished')) {
                    thinkingSection.classList.add('finished');
                }
                
                const previewText = document.getElementById(`thinking-preview-${data.msg_id}`);
                if (previewText) {
                    previewText.classList.add('stopped');
                    previewText.style.animation = 'none';
                    previewText.style.animationDuration = '';
                    previewText.style.transform = 'none';
                    void previewText.offsetWidth;
                }
            }
            
            if (streamingMessages.size === 0 && pendingMessages.size === 0) {
                hideStopBtn();
            }
            
            // 消息完成后检查是否需要自动重命名
            if (messageSessionId) {
                autoRenameSession(messageSessionId);
            }
        }
        
        function showError(data) {
            const wrapper = document.createElement('div');
            wrapper.className = 'message-item-wrapper';
            wrapper.innerHTML = `
                <div class="message-container">
                    <div style="padding: 12px 20px; color: #cf1322; background: #fff2f0; margin: 0 20px; border-radius: 6px;">
                        [${data.bot_id}] 错误: ${data.error}
                    </div>
                </div>
            `;
            document.getElementById('messages').appendChild(wrapper);
            smartScrollToBottom();
            
            activeStreams.delete(data.msg_id);
            streamingMessages.delete(data.msg_id);
            if (activeStreams.size === 0) {
                hideStopBtn();
            }
        }
        
        function createUserMsg(text) {
            document.querySelector('.empty-state')?.remove();
            addTimeDivider();
            
            let processedText = text;
            processedText = processedText.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '[IMG:$2|$1]');
            
            let html = marked.parse(processedText);
            
            html = html.replace(/\[IMG:([^|]+)\|([^\]]*)\]/g, (match, url, alt) => {
                const fullUrl = url + (url.includes('?') ? '&' : '?') + 'token=' + token;
                return `<img src="${fullUrl}" alt="${alt}" style="max-width: 300px; max-height: 300px; border-radius: 8px; cursor: pointer;" onclick="previewImage('${fullUrl}')">`;
            });
            
            html = html.replace(/<a[^>]*href="(\/uploads\/[^"]+)"[^>]*>(.*?)<\/a>/gi, (match, href, fileName) => {
                const fullUrl = href + (href.includes('?') ? '&' : '?') + 'token=' + token;
                return `<div class="file-bubble" style="display: flex; align-items: center; gap: 12px; padding: 12px; background: #f5f5f5; border-radius: 8px; cursor: pointer; min-width: 200px; max-width: 400px; margin: 4px 0;" onclick="event.preventDefault(); const a=document.createElement('a'); a.href='${fullUrl}'; a.download='${fileName}'; a.target='_blank'; document.body.appendChild(a); a.click(); document.body.removeChild(a);">
                    <div style="width: 40px; height: 40px; background: #3370ff; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                        <i class="fas fa-file" style="color: white; font-size: 18px;"></i>
                    </div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${fileName}</div>
                        <div style="font-size: 12px; color: #8f959e; margin-top: 2px;">点击下载</div>
                    </div>
                    <i class="fas fa-download" style="color: #8f959e; flex-shrink: 0;"></i>
                </div>`;
            });
            
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
                                <div class="message-content markdown-body">${html}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.getElementById('messages').appendChild(wrapper);
            smartScrollToBottom();
            
            const botId = currentBotId || Array.from(selectedBots)[0];
            if (botId) {
                saveMessageToDB({
                    type: 'user',
                    botId: botId,
                    content: text
                });
            }
        }
        
        function getTimeStr() {
            const now = new Date();
            return `${now.getMonth()+1}月${now.getDate()}日 ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
        }
        
        function shouldShowTime() {
            const now = Date.now();
            if (!lastMsgTime || now - lastMsgTime > 5 * 60 * 1000) {
                lastMsgTime = now;
                return true;
            }
            return false;
        }
        
        function addTimeDivider() {
            if (!shouldShowTime()) return;
            const div = document.createElement('div');
            div.className = 'message-time-divider';
            div.textContent = getTimeStr();
            document.getElementById('messages').appendChild(div);
        }
        
        // ========== 工具函数 ==========
        
        function processCode(html) {
            const temp = document.createElement('div');
            temp.innerHTML = html;
            temp.querySelectorAll('pre').forEach(pre => {
                const code = pre.querySelector('code');
                if (!code) return;
                const codeText = code.textContent;
                const wrapper = document.createElement('div');
                wrapper.className = 'code-block-wrapper';
                wrapper.innerHTML = `<button class="code-copy-btn" onclick="copyCode(this,'${btoa(encodeURIComponent(codeText))}')">复制</button>`;
                pre.parentNode.insertBefore(wrapper, pre);
                wrapper.appendChild(pre);
            });
            return temp.innerHTML;
        }
        
        window.copyCode = async function(btn, encoded) {
            try {
                await navigator.clipboard.writeText(decodeURIComponent(atob(encoded)));
                btn.textContent = '已复制';
                setTimeout(() => btn.textContent = '复制', 2000);
            } catch(e) {}
        };
        
        window.toggleThinking = function(msgId) {
            const thinkingSection = document.getElementById(`thinking-${msgId}`);
            const thinkingContent = document.getElementById(`thinking-content-${msgId}`);
            const thinkingPreview = thinkingSection?.querySelector('.thinking-preview');
            
            if (!thinkingSection || !thinkingContent) return;
            
            const isExpanded = thinkingSection.classList.contains('expanded') || 
                               thinkingContent.style.display === 'block';
            
            if (isExpanded) {
                thinkingSection.classList.remove('expanded');
                thinkingContent.style.display = 'none';
                if (thinkingPreview) thinkingPreview.style.display = '';
            } else {
                thinkingSection.classList.add('expanded');
                thinkingContent.style.display = 'block';
                if (thinkingPreview) thinkingPreview.style.display = 'none';
            }
        };
        
        function processImages(html) {
            const temp = document.createElement('div');
            temp.innerHTML = html;
            
            temp.querySelectorAll('img').forEach(img => {
                const src = img.getAttribute('src');
                if (src && !src.startsWith('http') && !src.startsWith('data:')) {
                    img.src = src + (src.includes('?') ? '&' : '?') + 'token=' + token;
                }
                img.style.maxWidth = '300px';
                img.style.maxHeight = '300px';
                img.style.borderRadius = '8px';
                img.style.cursor = 'pointer';
                img.onclick = () => previewImage(img.src);
            });
            
            temp.querySelectorAll('a').forEach(link => {
                const href = link.getAttribute('href') || '';
                const text = link.textContent || '';
                
                if ((href.includes('/uploads/') || href.includes('/api/file/')) && !link.classList.contains('processed')) {
                    link.classList.add('processed');
                    
                    const fileBubble = document.createElement('div');
                    fileBubble.className = 'file-bubble';
                    fileBubble.style.cssText = 'display: flex; align-items: center; gap: 12px; padding: 12px; background: #f5f5f5; border-radius: 8px; cursor: pointer; min-width: 200px; max-width: 400px; margin: 4px 0;';
                    fileBubble.innerHTML = `
                        <div style="width: 40px; height: 40px; background: #3370ff; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                            <i class="fas fa-file" style="color: white; font-size: 18px;"></i>
                        </div>
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${text}</div>
                            <div style="font-size: 12px; color: #8f959e; margin-top: 2px;">点击下载</div>
                        </div>
                        <i class="fas fa-download" style="color: #8f959e; flex-shrink: 0;"></i>
                    `;
                    fileBubble.onclick = (e) => {
                        e.preventDefault();
                        downloadFile(href, text);
                    };
                    

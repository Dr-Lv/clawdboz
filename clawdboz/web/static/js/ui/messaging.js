// Messaging UI

                const icon = document.getElementById('sidebarToggleIcon');
                sidebar.classList.add('collapsed');
                icon.classList.remove('fa-chevron-left');
                icon.classList.add('fa-chevron-right');
            }
        }
        
        // ========== 移动端侧边栏控制 ==========
        
        let mobileSidebarOpen = false;
        
        function toggleMobileSidebar() {
            if (mobileSidebarOpen) {
                closeMobileSidebar();
            } else {
                openMobileSidebar();
            }
        }
        
        function openMobileSidebar() {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('mobileOverlay');
            if (sidebar && overlay) {
                sidebar.classList.add('mobile-open');
                overlay.classList.add('show');
                mobileSidebarOpen = true;
                document.body.style.overflow = 'hidden';
                document.body.style.touchAction = 'none';
            }
        }
        
        function closeMobileSidebar() {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('mobileOverlay');
            if (sidebar && overlay) {
                sidebar.classList.remove('mobile-open');
                overlay.classList.remove('show');
                mobileSidebarOpen = false;
                document.body.style.overflow = '';
                document.body.style.touchAction = '';
            }
        }
        
        function selectSessionWithMobileClose(sessionId) {
            selectSession(sessionId);
            if (window.innerWidth <= 768) {
                closeMobileSidebar();
            }
        }
        
        function setupMobileViewport() {
            const setVH = () => {
                const vh = window.innerHeight * 0.01;
                document.documentElement.style.setProperty('--vh', `${vh}px`);
            };
            setVH();
            window.addEventListener('resize', setVH);
            
            window.addEventListener('resize', () => {
                if (window.innerWidth > 768 && mobileSidebarOpen) {
                    closeMobileSidebar();
                }
            });
            
            if ('visualViewport' in window) {
                window.visualViewport.addEventListener('resize', () => {
                    const vvHeight = window.visualViewport.height;
                    const windowHeight = window.innerHeight;
                    
                    if (vvHeight < windowHeight) {
                        const input = document.getElementById('messageInput');
                        if (input && document.activeElement === input) {
                            document.querySelector('.main').style.height = `${vvHeight}px`;
                            setTimeout(() => {
                                input.scrollIntoView({ behavior: 'smooth', block: 'end' });
                            }, 100);
                        }
                    } else {
                        document.querySelector('.main').style.height = '';
                    }
                });
            }
        }
        
        // ========== 消息区域滚动控制 ==========
        
        let isUserScrollingUp = false;
        let lastScrollTop = 0;
        
        function setupMessagesScroll() {
            const messagesContainer = document.getElementById('messages');
            const scrollBtn = document.getElementById('scrollToBottom');
            
            if (!messagesContainer) return;
            
            messagesContainer.addEventListener('scroll', () => {
                const currentScrollTop = messagesContainer.scrollTop;
                const scrollDiff = currentScrollTop - lastScrollTop;
                const isNearBottomNow = messagesContainer.scrollHeight - currentScrollTop - messagesContainer.clientHeight < 100;
                
                if (scrollDiff < -5 && !isNearBottomNow) {
                    isUserScrollingUp = true;
                } else if (isNearBottomNow) {
                    isUserScrollingUp = false;
                }
                
                lastScrollTop = currentScrollTop;
                
                if (scrollBtn) {
                    if (isNearBottomNow) {
                        scrollBtn.classList.remove('visible');
                    } else {
                        scrollBtn.classList.add('visible');
                    }
                }
            }, { passive: true });
        }
        
        function scrollToBottom() {
            const messagesContainer = document.getElementById('messages');
            if (messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            isUserScrollingUp = false;
            lastScrollTop = messagesContainer ? messagesContainer.scrollTop : 0;
        }
        
        function isNearBottom() {
            const messagesContainer = document.getElementById('messages');
            if (!messagesContainer) return true;
            return messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < 100;
        }
        
        function smartScrollToBottom() {
            if (!isUserScrollingUp || isNearBottom()) {
                scrollToBottom();
                isUserScrollingUp = false;
            }
        }
        
        // ========== 朋友圈功能 ==========
        
        let momentImages = [];
        
        // 加载朋友圈
        async function loadMoments() {
            try {
                console.log('[Moments] 开始加载...');
                const res = await fetch(`/api/moments?token=${token}&limit=20`);
                const data = await res.json();
                console.log('[Moments] API 返回:', data);
                if (data.success) {
                    console.log('[Moments] 渲染', data.moments?.length || 0, '条动态');
                    renderMoments(data.moments);
                } else {
                    console.error('[Moments] API 返回失败:', data.error);
                }
            } catch (e) {
                console.error('[Moments] 加载失败:', e);
            }
        }
        
        // 渲染朋友圈列表
        function renderMoments(moments) {
            console.log('[Moments] renderMoments 被调用, 数据:', moments);
            
            // 在消息区域显示朋友圈内容
            document.getElementById('messages').style.display = 'none';
            document.querySelector('.input-area').style.display = 'none';
            
            // 创建或获取朋友圈面板
            let momentsPanel = document.getElementById('momentsPanel');
            if (!momentsPanel) {
                momentsPanel = document.createElement('div');
                momentsPanel.id = 'momentsPanel';
                momentsPanel.className = 'messages-container';
                momentsPanel.style.display = 'block';
                momentsPanel.style.padding = '20px';
                momentsPanel.style.overflowY = 'auto';
                document.querySelector('.messages-wrapper').appendChild(momentsPanel);
            }
            
            // 发布框 HTML
            const publishHtml = `
                <div class="moments-publish">
                    <textarea id="momentTextarea" class="moments-publish-textarea" placeholder="分享你的心情..."></textarea>
                    <div class="moments-publish-actions">
                        <div class="moments-publish-tools">
                            <div class="moments-publish-tool" onclick="selectMomentImage()" title="添加图片">
                                <i class="fas fa-image"></i>
                            </div>
                            <div class="moments-publish-tool" onclick="selectMomentFile()" title="添加文件">
                                <i class="fas fa-paperclip"></i>
                            </div>
                        </div>
                        <button class="moments-publish-btn" onclick="publishMoment()">
                            <i class="fas fa-paper-plane"></i> 发布
                        </button>
                    </div>
                </div>
            `;
            
            if (!moments || moments.length === 0) {
                console.log('[Moments] 无数据, 显示空状态');
                momentsPanel.innerHTML = `
                    <div style="max-width: 600px; margin: 0 auto;">
                        ${publishHtml}
                        <div style="text-align:center;color:var(--text-tertiary);padding:60px 40px;">
                            <i class="fas fa-camera" style="font-size: 64px; margin-bottom: 20px; opacity: 0.3;"></i>
                            <div style="font-size: 18px; margin-bottom: 10px;">暂无动态</div>
                            <div style="font-size: 14px; opacity: 0.7;">发布你的第一条动态</div>
                        </div>
                    </div>
                `;
            } else {
                console.log('[Moments] 渲染', moments.length, '条动态');
                momentsPanel.innerHTML = `
                    <div style="max-width: 600px; margin: 0 auto;">
                        ${publishHtml}
                        ${moments.map(moment => renderMomentItem(moment)).join('')}
                    </div>
                `;
            }
            momentsPanel.style.display = 'block';
            console.log('[Moments] 渲染完成');
        }
        
        // 渲染单条朋友圈
        function renderMomentItem(moment) {
            const sender = moment.sender || {};
            const avatarColor = sender.avatar_color || 'from-blue-500 to-blue-600';
            const avatarIcon = sender.avatar_icon || 'fa-user';
            const name = sender.name || '未知';
            const time = formatTime(moment.created_at);
            const content = moment.content || '';
            const images = moment.images || [];
            const likes = moment.likes || [];
            const comments = moment.comments || [];
            
            // 判断当前用户是否点赞
            const hasLiked = likes.some(like => {
                if (typeof like === 'string') return like === 'user';
                return like.sender_id === 'user';
            });
            
            // 图片布局
            let imagesHtml = '';
            if (images.length > 0) {
                const gridClass = images.length === 1 ? 'single' : images.length === 2 ? 'double' : '';
                imagesHtml = `
                    <div class="moment-images ${gridClass}">
                        ${images.filter(img => img).map(img => `
                            <div class="moment-image" onclick="viewImage('${img}')">
                                <img src="${img}" alt="" loading="lazy" onerror="this.style.display='none'; this.parentElement.innerHTML='<div style=\\'padding:20px;text-align:center;color:#999\\'><i class=\\'fas fa-image\\'></i> 图片加载失败</div>';">
                            </div>
                        `).join('')}
                    </div>
                `;
            }
            
            // 点赞
            let likesHtml = '';
            if (likes.length > 0) {
                const likeNames = likes.map(l => {
                    if (typeof l === 'string') return l;
                    return l.sender_name || l.sender_id || '未知用户';
                }).join('、');
                likesHtml = `
                    <div class="moment-likes">
                        <i class="fas fa-heart moment-likes-icon"></i>
                        ${likeNames}
                    </div>
                `;
            }
            
            // 评论
            let commentsHtml = '';
            if (comments.length > 0) {
                const commentsList = comments.map(c => {
                    const author = c.sender?.name || '未知';
                    return `
                        <div class="moment-comment">
                            <span class="moment-comment-author">${author}</span>:
                            <span class="moment-comment-content">${c.content}</span>
                        </div>
                    `;
                }).join('');
                commentsHtml = `<div class="moment-comments">${commentsList}</div>`;
            }
            
            return `
                <div class="moment-item" data-moment-id="${moment.id}">
                    <div class="moment-header">
                        <div class="moment-avatar bg-gradient-to-br ${avatarColor}">
                            <i class="fas ${avatarIcon}"></i>
                        </div>
                        <div class="moment-info">
                            <div class="moment-name">${name}</div>
                            <div class="moment-time">${time}</div>
                        </div>
                    </div>
                    <div class="moment-content">${content}</div>
                    ${imagesHtml}
                    <div class="moment-actions">
                        <div class="moment-action ${hasLiked ? 'liked' : ''}" onclick="toggleLike('${moment.id}')">
                            <i class="${hasLiked ? 'fas' : 'far'} fa-heart"></i>
                            <span>${likes.length || '点赞'}</span>
                        </div>
                        <div class="moment-action" onclick="showCommentInput('${moment.id}')">
                            <i class="far fa-comment"></i>
                            <span>${comments.length || '评论'}</span>
                        </div>
                    </div>
                    ${likesHtml}
                    ${commentsHtml}
                    <div class="moment-comment-input-container" id="comment-input-${moment.id}" style="display:none;">
                        <input type="text" class="moment-comment-input" id="comment-text-${moment.id}" placeholder="写评论..." onkeypress="if(event.key==='Enter')submitComment('${moment.id}')">
                        <button class="moment-comment-submit" onclick="submitComment('${moment.id}')">发送</button>
                    </div>
                </div>
            `;
        }
        
        // 选择图片
        function selectMomentImage() {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = 'image/*';
            input.multiple = true;
            input.onchange = async (e) => {
                const files = Array.from(e.target.files);
                for (const file of files) {
                    if (momentImages.length >= 9) {
                        showToast('最多只能上传9张图片', 'warning');
                        break;
                    }
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('token', token);
                    try {
                        const res = await fetch('/api/upload', {
                            method: 'POST',
                            body: formData
                        });
                        const data = await res.json();
                        if (data.success) {
                            momentImages.push(data.file_url);
                            updateMomentImagePreview();
                        }
                    } catch (err) {
                        console.error('上传图片失败:', err);
                    }
                }
            };
            input.click();
        }
        
        // 选择文件
        function selectMomentFile() {
            selectMomentImage();
        }
        
        // 更新图片预览
        function updateMomentImagePreview() {
            const container = document.getElementById('momentImagePreview');
            container.innerHTML = momentImages.map((url, idx) => `
                <div class="moments-image-preview-item">
                    <img src="${url}" alt="">
                    <div class="moments-image-preview-remove" onclick="removeMomentImage(${idx})">×</div>
                </div>
            `).join('');
        }
        
        // 移除图片
        function removeMomentImage(index) {
            momentImages.splice(index, 1);
            updateMomentImagePreview();
        }
        
        // 发布朋友圈
        async function publishMoment() {
            const content = document.getElementById('momentTextarea').value.trim();
            if (!content && momentImages.length === 0) {
                showToast('请输入内容或添加图片', 'warning');
                return;
            }
            
            try {
                const res = await fetch('/api/moments', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token,
                        content,
                        images: momentImages,
                        sender_id: 'user',
                        sender_type: 'user'
                    })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('发布成功', 'success');
                    console.log('[Moments] 发布成功:', data.moment);
                    document.getElementById('momentTextarea').value = '';
                    momentImages = [];
                    updateMomentImagePreview();
                    setTimeout(() => loadMoments(), 100); // 稍微延迟确保数据已写入
                } else {
                    showToast(data.error || '发布失败', 'error');
                }
            } catch (e) {
                console.error('发布失败:', e);
                showToast('发布失败', 'error');
            }
        }
        
        // 点赞/取消点赞
        async function toggleLike(momentId) {
            try {
                const res = await fetch(`/api/moments/${momentId}/like`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token,
                        sender_id: 'user',
                        sender_type: 'user'
                    })
                });
                const data = await res.json();
                if (data.success) {
                    loadMoments();
                }
            } catch (e) {
                console.error('点赞失败:', e);
            }
        }
        
        // 显示评论输入框
        function showCommentInput(momentId) {
            const inputContainer = document.getElementById(`comment-input-${momentId}`);
            inputContainer.style.display = inputContainer.style.display === 'none' ? 'flex' : 'none';
            if (inputContainer.style.display === 'flex') {
                document.getElementById(`comment-text-${momentId}`).focus();
            }
        }
        
        // 提交评论
        async function submitComment(momentId) {
            const input = document.getElementById(`comment-text-${momentId}`);
            const content = input.value.trim();


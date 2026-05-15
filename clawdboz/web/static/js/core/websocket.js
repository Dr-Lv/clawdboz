// WebSocket connection

            const chatHeader = document.querySelector('.chat-header');
            if (chatHeader) {
                chatHeader.style.display = (tab === 'messages') ? 'flex' : 'none';
            }
            
            // 恢复侧边栏显示（用于从朋友圈切回）
            document.getElementById('sidebar').style.display = 'flex';
            
            // 显示目标视图
            if (tab === 'messages') {
                document.getElementById('messagesView').style.display = 'flex';
                // 确保消息区域显示正常
                document.getElementById('messages').style.display = 'block';
                document.querySelector('.input-area').style.display = 'block';
            } else if (tab === 'contacts') {
                // 显示消息视图，但在侧边栏显示通讯录覆盖层，隐藏标题栏
                document.getElementById('messagesView').style.display = 'flex';
                document.getElementById('messages').style.display = 'none';
                document.querySelector('.input-area').style.display = 'none';
                document.getElementById('contactsOverlay').classList.add('active');
                loadSidebarContacts().then(() => {
                    // 如果已有选中的 Bot，自动刷新详情卡片
                    if (selectedContactId) {
                        selectSidebarContact(selectedContactId);
                    }
                });
            } else if (tab === 'moments') {
                // 显示消息视图，隐藏标题栏和侧边栏，全宽显示朋友圈
                document.getElementById('messagesView').style.display = 'flex';
                document.getElementById('messages').style.display = 'none';
                document.querySelector('.input-area').style.display = 'none';
                // 隐藏侧边栏
                document.getElementById('sidebar').style.display = 'none';
                loadMoments();
            }

            currentTab = tab;
        }

        // ========== 用户资料功能 ==========
        
        let userProfile = {
            name: '',
            bio: ''
        };
        
        async function loadUserProfile() {
            try {
                const response = await fetch(`/api/user/profile?token=${token}`);
                if (response.ok) {
                    const data = await response.json();
                    userProfile.name = data.name || '';
                    userProfile.bio = data.bio || '';
                    userProfile.avatar_color = data.avatar_color || 'from-indigo-500 to-purple-600';
                    userProfile.avatar_icon = data.avatar_icon || 'fa-user';
                    // 更新左上角用户头像
                    updateUserTabAvatar();
                }
            } catch (e) {
                console.error('加载用户资料失败:', e);
            }
        }
        
        // 更新左上角用户标签头像
        function updateUserTabAvatar() {
            const avatarEl = document.getElementById('userTabAvatar');
            if (avatarEl && userProfile.avatar_color && userProfile.avatar_icon) {
                avatarEl.className = `user-tab-avatar bg-gradient-to-br ${userProfile.avatar_color}`;
                avatarEl.innerHTML = `<i class="fas ${userProfile.avatar_icon}"></i>`;
            }
        }
        
        function showUserProfileModal() {
            loadUserProfile().then(() => {
                document.getElementById('userProfileName').value = userProfile.name;
                document.getElementById('userProfileBio').value = userProfile.bio;
                // 加载头像
                const avatarColor = userProfile.avatar_color || 'from-indigo-500 to-purple-600';
                const avatarIcon = userProfile.avatar_icon || 'fa-user';
                document.getElementById('userAvatarColor').value = avatarColor;
                document.getElementById('userAvatarIcon').value = avatarIcon;
                const preview = document.getElementById('userAvatarPreview');
                preview.className = `avatar-preview-large bg-gradient-to-br ${avatarColor}`;
                preview.innerHTML = `<i class="fas ${avatarIcon}"></i>`;
                document.getElementById('userProfileModal').classList.add('show');
            });
        }
        
        function closeUserProfileModal() {
            document.getElementById('userProfileModal').classList.remove('show');
        }
        
        function closeUserProfileModalOnOverlay(event) {
            if (event.target.id === 'userProfileModal') {
                closeUserProfileModal();
            }
        }
        
        async function saveUserProfile() {
            const name = document.getElementById('userProfileName').value.trim();
            const bio = document.getElementById('userProfileBio').value.trim();
            const avatarColor = document.getElementById('userAvatarColor').value;
            const avatarIcon = document.getElementById('userAvatarIcon').value;
            
            try {
                const response = await fetch('/api/user/profile/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token, name, bio, avatar_color: avatarColor, avatar_icon: avatarIcon })
                });
                
                if (response.ok) {
                    userProfile.name = name;
                    userProfile.bio = bio;
                    userProfile.avatar_color = avatarColor;
                    userProfile.avatar_icon = avatarIcon;
                    // 更新左上角头像
                    updateUserTabAvatar();
                    closeUserProfileModal();
                    showToast('保存成功', 'success');
                } else {
                    showToast('保存失败', 'error');
                }
            } catch (e) {
                console.error('保存用户资料失败:', e);
                showToast('保存失败', 'error');
            }
        }
        
        // ========== 新建 Bot 功能 ==========
        
        function showCreateBotModal() {
            console.log('[Create Bot] 打开创建 Bot 弹窗');
            document.getElementById('newBotId').value = '';
            document.getElementById('newBotName').value = '';
            document.getElementById('newBotBio').value = '';
            document.getElementById('createBotModal').classList.add('show');
        }
        
        function closeCreateBotModal() {
            document.getElementById('createBotModal').classList.remove('show');
        }
        
        function closeCreateBotModalOnOverlay(event) {
            if (event.target.id === 'createBotModal') {
                closeCreateBotModal();
            }
        }
        
        async function confirmCreateBot() {
            const botId = document.getElementById('newBotId').value.trim();
            const name = document.getElementById('newBotName').value.trim();
            const bio = document.getElementById('newBotBio').value.trim();
            
            if (!botId) {
                showToast('请输入 Bot ID', 'warning');
                return;
            }
            
            // 验证 botId 格式（只允许字母、数字、下划线、连字符）
            if (!/^[a-zA-Z0-9_-]+$/.test(botId)) {
                showToast('Bot ID 只能包含字母、数字、下划线和连字符', 'warning');
                return;
            }
            
            if (!token) {
                showToast('未登录或 Token 无效', 'error');
                return;
            }
            
            try {
                console.log('[Create Bot] 发送请求:', { bot_id: botId, name, bio, token: token ? '已设置' : '未设置' });
                const response = await fetch('/api/bots', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token, bot_id: botId, name, bio })
                });
                
                let result;
                try {
                    result = await response.json();
                } catch (jsonErr) {
                    const text = await response.text();
                    console.error('[Create Bot] 解析响应失败:', jsonErr, '响应内容:', text);
                    showToast('服务器返回格式错误: ' + text.substring(0, 100), 'error');
                    return;
                }
                
                console.log('[Create Bot] 响应:', result);
                
                if (response.ok && result.success) {
                    console.log('[Create Bot] 创建成功，刷新列表');
                    // 重新加载 bot 列表
                    await loadBots();
                    // 刷新通讯录列表（包括侧边栏和完整页面）
                    renderSidebarContactsList();
                    if (currentTab === 'contacts') {
                        renderContactsList();
                    }
                    closeCreateBotModal();
                    showToast('Bot 创建成功', 'success');
                } else {
                    console.log('[Create Bot] 创建失败:', result.error);
                    showToast(result.error || '创建失败', 'error');
                }
            } catch (e) {
                console.error('创建 Bot 失败:', e);
                showToast('创建失败: ' + (e.message || '未知错误'), 'error');
            }
        }
        
        // ========== 编辑 Bot 功能 ==========
        
        function showEditBotModal() {
            if (!selectedContactId) {
                showToast('请先选择一个 Bot', 'warning');
                return;
            }
            
            const bot = bots.find(b => b.id === selectedContactId);
            if (!bot) {
                showToast('Bot 不存在', 'error');
                return;
            }
            
            document.getElementById('editBotId').value = bot.id;
            document.getElementById('editBotIdDisplay').value = bot.id;
            document.getElementById('editBotName').value = bot.name || bot.id;
            document.getElementById('editBotBio').value = bot.bio || '';
            // 加载头像
            const avatarColor = bot.avatar_color || 'from-blue-500 to-blue-600';
            const avatarIcon = bot.avatar_icon || 'fa-robot';
            document.getElementById('editBotAvatarColor').value = avatarColor;
            document.getElementById('editBotAvatarIcon').value = avatarIcon;
            const preview = document.getElementById('editBotAvatarPreview');
            preview.className = `avatar-preview-medium bg-gradient-to-br ${avatarColor}`;
            preview.style.cssText = 'margin: 0 auto; cursor: pointer; width: 64px; height: 64px; font-size: 28px;';
            preview.innerHTML = `<i class="fas ${avatarIcon}"></i>`;
            document.getElementById('editBotModal').classList.add('show');
        }
        
        function closeEditBotModal() {
            document.getElementById('editBotModal').classList.remove('show');
        }
        
        function closeEditBotModalOnOverlay(event) {
            if (event.target.id === 'editBotModal') {
                closeEditBotModal();
            }
        }


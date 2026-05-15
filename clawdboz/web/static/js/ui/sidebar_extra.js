        if (content) content.style.transform = '';
        swipeItem = null;
        return;
    }
    if (swipeOffset <= SWIPE_THRESHOLD) {
        if (content) content.style.transform = `translateX(-80px)`;
        swipeItem.classList.add('swiped');
    } else {
        resetSwipe(swipeItem);
    }
    swipeItem = null;
}

function resetSwipe(item) {
    const content = item.querySelector('.sidebar-item-content');
    if (content) content.style.transform = '';
    item.classList.remove('swiped');
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.sidebar-item')) {
        document.querySelectorAll('.sidebar-item.swiped').forEach(resetSwipe);
    }
});

export async function confirmDeleteSession(sessionId, event) {
    event.stopPropagation();
    try {
        const session = getSessionById(sessionId);
        const sessionName = session ? session.name : 'this session';
        const confirmed = confirm(`Delete "${sessionName}"?\n\nChat history will be lost.`);
        if (!confirmed) return;
        await deleteSessionById(sessionId);
    } catch (e) {
        console.error('[confirmDeleteSession] Delete failed:', e);
        alert('Delete failed: ' + e.message);
    }
}

export async function deleteSessionById(sessionId) {
    const success = await deleteSessionFromDB(sessionId, token);
    if (!success) {
        alert('Delete failed, please try again');
        return;
    }
    removeSession(sessionId);
    if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        if (sessions.length > 0) {
            await selectSession(sessions[0].id);
            return;
        } else {
            const messagesEl = document.getElementById('messages');
            if (messagesEl) {
                messagesEl.innerHTML = '<div class="empty-state"><div class="empty-icon">🤖</div><div>Click "+" to create a new session</div></div>';
            }
            const headerTitle = document.getElementById('headerTitle');
            if (headerTitle) headerTitle.textContent = 'Select a session';
        }
    }
    renderSessionList();
}

export async function selectSession(sessionId) {
    setCurrentSessionId(sessionId);
    renderSessionList();
}

export function selectSessionWithMobileClose(sessionId) {
    selectSession(sessionId);
    if (window.innerWidth <= 768) {
        closeMobileSidebar();
    }
}

export function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    const sidebar = document.getElementById('sidebar');
    const icon = document.getElementById('sidebarToggleIcon');
    if (!sidebar || !icon) return;
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

export function restoreSidebarState() {
    const collapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (collapsed) {
        sidebarCollapsed = true;
        const sidebar = document.getElementById('sidebar');
        const icon = document.getElementById('sidebarToggleIcon');
        if (sidebar && icon) {
            sidebar.classList.add('collapsed');
            icon.classList.remove('fa-chevron-left');
            icon.classList.add('fa-chevron-right');
        }
    }
}

export function toggleMobileSidebar() {
    if (mobileSidebarOpen) {
        closeMobileSidebar();
    } else {
        openMobileSidebar();
    }
}

export function openMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (sidebar && overlay) {
        sidebar.classList.add('mobile-open');
        overlay.classList.add('show');
        mobileSidebarOpen = true;
        document.body.style.overflow = 'hidden';
    }
}

export function closeMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (sidebar && overlay) {
        sidebar.classList.remove('mobile-open');
        overlay.classList.remove('show');
        mobileSidebarOpen = false;
        document.body.style.overflow = '';
    }
}

export function toggleBotGroup(botId) {
    toggleGroupCollapsed(botId);
    const header = document.getElementById(`bot-group-${botId}`);
    const sessionsEl = document.getElementById(`bot-group-sessions-${botId}`);
    const icon = document.getElementById(`bot-group-icon-${botId}`);
    if (header && sessionsEl && icon) {
        const isCollapsed = collapsedGroups.has(botId);
        if (isCollapsed) {
            header.classList.add('collapsed');
            sessionsEl.classList.add('collapsed');
            icon.style.transform = 'rotate(-90deg)';
        } else {
            header.classList.remove('collapsed');
            sessionsEl.classList.remove('collapsed');
            icon.style.transform = 'rotate(0deg)';
        }
    }
}

export function toggleAllGroups() {
    const newState = !allGroupsCollapsed;
    setAllGroupsCollapsed(newState);
    const icon = document.getElementById('collapseAllIcon');
    if (icon) {
        icon.className = newState ? 'fas fa-compress-alt' : 'fas fa-expand-alt';
    }
    const botIds = new Set();
    sessions.forEach(s => {
        if (s.botIds && s.botIds.length === 1) {
            botIds.add(s.botIds[0]);
        }
    });
    botIds.forEach(botId => {
        if (newState) {
            collapsedGroups.add(botId);
        } else {
            collapsedGroups.delete(botId);
        }
        toggleBotGroup(botId);
    });
}

export function showSessionContextMenu(event, sessionId) {
    event.preventDefault();
    event.stopPropagation();
    contextMenuSessionId = sessionId;
    const menu = document.getElementById('sessionContextMenu');
    if (menu) {
        menu.style.left = event.clientX + 'px';
        menu.style.top = event.clientY + 'px';
        menu.classList.add('show');
        setTimeout(() => {
            document.addEventListener('click', closeContextMenu, { once: true });
        }, 0);
    }
}

export function closeContextMenu() {
    const menu = document.getElementById('sessionContextMenu');
    if (menu) menu.classList.remove('show');
    contextMenuSessionId = null;
}

export function renameSession() {
    if (!contextMenuSessionId) return;
    const session = getSessionById(contextMenuSessionId);
    if (!session) return;
    renameTargetSessionId = contextMenuSessionId;
    const input = document.getElementById('renameInput');
    if (input) {
        input.value = session.name;
        input.focus();
        input.select();
    }
    const modal = document.getElementById('renameModal');
    if (modal) modal.classList.add('show');
    closeContextMenu();
}

export function closeRenameModal() {
    const modal = document.getElementById('renameModal');
    if (modal) modal.classList.remove('show');
    contextMenuSessionId = null;
    renameTargetSessionId = null;
}

export function closeRenameModalOnOverlay(event) {
    if (event.target.id === 'renameModal') {
        closeRenameModal();
    }
}

export async function confirmRename() {
    if (!renameTargetSessionId) return;
    const input = document.getElementById('renameInput');
    const newName = input?.value.trim();
    if (!newName) return;
    const session = getSessionById(renameTargetSessionId);
    if (session) {
        session.name = newName;
        await saveSessionToDB(session);
        await saveSessionToServer(session, token);
        renderSessionList();
    }
    renameTargetSessionId = null;
    closeRenameModal();
}

export async function deleteSession() {
    const sessionIdToDelete = contextMenuSessionId;
    if (!sessionIdToDelete) return;
    if (!confirm('Delete this session? Chat history will be lost.')) {
        closeContextMenu();
        return;
    }
    await deleteSessionById(sessionIdToDelete);
    closeContextMenu();
}

function formatTime(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    const date = new Date(timestamp);
    return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function setupMobileViewport() {
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
}

export function initSidebar() {
    restoreSidebarState();
    setupMobileViewport();
}

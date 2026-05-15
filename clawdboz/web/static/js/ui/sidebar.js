/**
 * Sidebar Module
 * Manages session list rendering, sidebar interactions, and session management
 */

    bots,
    sessions,
    currentSessionId,
    sessionUnreadCounts,
    collapsedGroups,
    allGroupsCollapsed,
    setSessions,
    setCurrentSessionId,
    setCollapsedGroups,
    setAllGroupsCollapsed,
    toggleGroupCollapsed,
    getSessionById,
    removeSession,
    token
} from '../core/state.js';

    saveSessionToDB,
    deleteSessionFromDB,
    createSession,
    saveSessionToServer,
    loadSessionsFromServer,
    loadMessagesFromServer
} from '../core/database.js';


// Sidebar state
let sidebarCollapsed = false;
let mobileSidebarOpen = false;
let contextMenuSessionId = null;
let renameTargetSessionId = null;

// Swipe state
let swipeItem = null;
let swipeStartX = 0;
let swipeStartY = 0;
let swipeOffset = 0;
let swipeStartTime = 0;
const SWIPE_THRESHOLD = -80;
const MAX_SWIPE = -100;
const CLICK_TIME_THRESHOLD = 300;
const CLICK_DISTANCE_THRESHOLD = 10;

/**
 * Load sessions from server or local DB
 */
export async function loadSessions() {
    try {
        console.log('[Init] Loading sessions from server...');
        const serverSessions = await loadSessionsFromServer(token);

        if (serverSessions.length > 0) {
            setSessions(serverSessions);
            console.log(`[Init] Loaded ${sessions.length} sessions from server`);

            for (const session of sessions) {
                await saveSessionToDB(session);
            }
        } else {
            console.log('[Init] No sessions on server, creating default');
            if (bots.length > 0) {
                const defaultSession = createSession([bots[0].id], bots[0].name || bots[0].id, bots);
                setSessions([defaultSession]);
                await saveSessionToDB(defaultSession);
                await saveSessionToServer(defaultSession, token);
            } else {
                setSessions([]);
            }
        }

        renderSessionList();

        if (sessions.length > 0) {
            await selectSession(sessions[0].id);
        }
    } catch (e) {
        console.error('Failed to load sessions from server:', e);
        try {
            const localSessions = await loadSessionsFromDB();
            localSessions.forEach(s => {
                if (!s.mode) {
                    s.mode = s.botIds && s.botIds.length > 1 ? 'group' : 'single';
                }
            });
            setSessions(localSessions);
            if (sessions.length > 0) {
                renderSessionList();
                await selectSession(sessions[0].id);
            }
        } catch (e2) {
            console.error('Local cache also failed:', e2);
        }
    }
}

/**
 * Render the session list in the sidebar
 */
export function renderSessionList() {
    const container = document.getElementById('botList');
    if (!container) return;

    if (sessions.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.4);padding:20px;">Click "+" to create a session</div>';
        return;
    }

    const groupSessions = sessions.filter(s => s.botIds.length > 1);
    const singleSessions = sessions.filter(s => s.botIds.length === 1);

    const groups = {};
    singleSessions.forEach(session => {
        const firstBotId = session.firstBotId || session.botIds[0];
        if (!groups[firstBotId]) {
            groups[firstBotId] = [];
        }
        groups[firstBotId].push(session);
    });

    let html = '';

    if (groupSessions.length > 0) {
        html += `
            <div class="sidebar-section-title" style="margin-top: 0;">
                <span>Group Chats</span>
                <span class="session-count">${groupSessions.length}</span>
            </div>
        `;

        html += groupSessions.map(session => {
            const isActive = session.id === currentSessionId;
            const avatarHtml = generateGroupAvatarHtml(session.botIds, null, bots);
            const unreadCount = sessionUnreadCounts.get(session.id) || 0;
            const unreadBadge = unreadCount > 0 ? `<div class="session-unread-badge">${unreadCount}</div>` : '';
            return `
                <div class="sidebar-item ${isActive ? 'active' : ''}" data-session-id="${session.id}">
                    <div class="sidebar-delete-btn" onclick="event.stopPropagation(); window.confirmDeleteSession('${session.id}', event);">
                        <i class="fas fa-trash-alt"></i> Delete
                    </div>
                    <div class="sidebar-item-content" onclick="window.selectSessionWithMobileClose('${session.id}')">
                        ${avatarHtml}
                        <div class="sidebar-info">
                            <div class="sidebar-title" title="${session.name}">${session.name}</div>
                            <div class="sidebar-subtitle">${session.botIds.length} bots · ${formatTime(session.createdAt)}</div>
                        </div>
                        ${unreadBadge}
                    </div>
                </div>
            `;
        }).join('');
    }

    if (Object.keys(groups).length > 0) {
        html += `
            <div class="sidebar-section-title">
                <span>Single Chats</span>
                <span class="collapse-btn" onclick="window.toggleAllGroups()" title="Expand/Collapse All">
                    <i class="fas fa-expand-alt" id="collapseAllIcon"></i>
                </span>
            </div>
        `;

        for (const [botId, botSessions] of Object.entries(groups)) {
            const bot = bots.find(b => b.id === botId);
            const botName = bot?.name || botId;
            const cfg = getBotAvatarConfig(botId, bots);
            const isCollapsed = collapsedGroups.has(botId);

            html += `
                <div class="bot-group">
                    <div class="bot-group-header ${isCollapsed ? 'collapsed' : ''}" onclick="window.toggleBotGroup('${botId}')">
                        <i class="fas fa-chevron-down" id="bot-group-icon-${botId}" style="transform: ${isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)'};"></i>
                        <div class="bot-avatar-small ${cfg.color} text-white">
                            <i class="fas ${cfg.icon}"></i>
                        </div>
                        <span style="flex:1">${botName}</span>
                        <span class="session-count">${botSessions.length}</span>
                    </div>
                    <div class="bot-group-sessions ${isCollapsed ? 'collapsed' : ''}" id="bot-group-sessions-${botId}">
                        ${botSessions.map(session => {
                            const isActive = session.id === currentSessionId;
                            const unreadCount = sessionUnreadCounts.get(session.id) || 0;
                            const unreadBadge = unreadCount > 0 ? `<div class="session-unread-badge">${unreadCount}</div>` : '';
                            // 飞书会话标识（source === 'feishu'）
                            const isFeishu = session.source === 'feishu' || session.id.startsWith('f_');
                            const feishuIcon = isFeishu ? '<i class="fas fa-paper-plane" style="margin-right:4px;color:#2eb5f0;"></i>' : '';
                            const feishuClass = isFeishu ? 'feishu-session' : '';
                            return `
                                <div class="sidebar-item ${isActive ? 'active' : ''} ${feishuClass}" data-session-id="${session.id}">
                                    <div class="sidebar-delete-btn" onclick="event.stopPropagation(); window.confirmDeleteSession('${session.id}', event);">
                                        <i class="fas fa-trash-alt"></i> Delete
                                    </div>
                                    <div class="sidebar-item-content" onclick="window.selectSessionWithMobileClose('${session.id}')" style="padding-left: 36px;">
                                        <div class="sidebar-info">
                                            <div class="sidebar-title" title="${session.name}">${feishuIcon}${session.name}</div>
                                            <div class="sidebar-subtitle">${isFeishu ? '飞书 · ' : ''}${formatTime(session.createdAt)}</div>
                                        </div>
                                        ${unreadBadge}
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        }
    }

    container.innerHTML = html;
    bindSwipeEvents();
}

function bindSwipeEvents() {
    const items = document.querySelectorAll('.sidebar-item');
    items.forEach(item => {
        item.addEventListener('touchstart', handleSwipeStart, { passive: true });
        item.addEventListener('touchmove', handleSwipeMove, { passive: true });
        item.addEventListener('touchend', handleSwipeEnd, { passive: true });
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
        if (el !== item) resetSwipe(el);
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

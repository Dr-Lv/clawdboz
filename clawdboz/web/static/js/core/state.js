// Global state

            const options = document.querySelectorAll('.avatar-option');
                const presets = document.getElementById('avatarSelectorTarget').value === 'user' ? avatarPresets : botAvatarPresets;
                const preset = presets[index];
            const preview = document.getElementById('avatarPreview');
            const target = document.getElementById('avatarSelectorTarget').value;
                const preview = document.getElementById('userAvatarPreview');
                const preview = document.getElementById('editBotAvatarPreview');
            const color = document.getElementById('userAvatarColor').value || 'from-indigo-500 to-purple-600';
            const icon = document.getElementById('userAvatarIcon').value || 'fa-user';
            const bot = bots.find(b => b.id === botId);
            let hash = 0;
            for (let i = 0; i < botId.length; i++) {
            const idx = Math.abs(hash) % botConfigs.length;
                const request = indexedDB.open(DB_NAME, DB_VERSION);
                    const db = event.target.result;
                    const store = db.createObjectStore('messages', { keyPath: 'id', autoIncrement: true });
                    const sessionStore = db.createObjectStore('sessions', { keyPath: 'id' });
                const transaction = db.transaction(['sessions'], 'readonly');
                const store = transaction.objectStore('sessions');
                const request = store.getAll();
                    const sessions = request.result.sort((a, b) => b.timestamp - a.timestamp);
                const transaction = db.transaction(['sessions'], 'readwrite');
                const store = transaction.objectStore('sessions');
                const record = {
                const request = store.put(record);
                const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}?token=${token}`, {
                    const result = await res.json();
                const transaction = db.transaction(['sessions', 'messages'], 'readwrite');
                const sessionStore = transaction.objectStore('sessions');
                const messageStore = transaction.objectStore('messages');


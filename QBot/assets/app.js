let AUTH_KEY = "";
let currentTarget = null;
let pollTimer = null;

// 简易安全 Markdown 解析引擎
function parseMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);

    // 1. 标题
    html = html.replace(/^### (.*$)/gim, '### $1');
    html = html.replace(/^## (.*$)/gim, '## $1');
    html = html.replace(/^# (.*$)/gim, '# $1');

    // 2. 引用
    html = html.replace(/^&gt; (.*$)/gim, '<blockquote>$1</blockquote>');

    // 3. 粗体
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // 4. 行内代码
    html = html.replace(/`(.*?)`/g, '<code>$1</code>');

    // 5. 列表
    html = html.replace(/^\* (.*$)/gim, '<ul><li>$1</li></ul>');
    html = html.replace(/<\/ul>\n<ul>/g, '');

    // 6. 换行
    html = html.replace(/\n/g, '<br>');

    return html;
}

// 统一 API 请求封装
async function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    
    // GET 请求携带 key 参数；POST 请求在 Body 中提交 key
    let requestUrl = url;
    if (!options.method || options.method.toUpperCase() === "GET") {
        const separator = requestUrl.includes("?") ? "&" : "?";
        requestUrl += `${separator}key=${encodeURIComponent(AUTH_KEY)}`;
    } else if (options.method.toUpperCase() === "POST") {
        options.headers["Content-Type"] = "application/json";
        let bodyObj = {};
        if (options.body) {
            try { bodyObj = JSON.parse(options.body); } catch (e) {}
        }
        bodyObj.key = AUTH_KEY;
        options.body = JSON.stringify(bodyObj);
    }
    
    try {
        const res = await fetch(requestUrl, options);
        if (res.status === 401) {
            clearAndExit("身份校验失败：密码不正确或过期！");
            throw new Error("401 Unauthorized");
        }
        return await res.json();
    } catch (err) {
        console.error("API 异常:", err);
        throw err;
    }
}

async function login() {
    const keyInput = document.getElementById("authKeyInput").value.trim();
    if (!keyInput) return alert("请输入密码！");

    const btn = document.getElementById("loginBtn");
    btn.innerText = "正在登录...";
    btn.disabled = true;

    AUTH_KEY = keyInput;

    try {
        const res = await apiFetch("/bot/api/users");
        if (res.status === "success") {
            document.getElementById("authKeyInput").value = "";
            document.getElementById("loginCard").style.display = "none";
            document.getElementById("mainContainer").style.display = "flex";
            
            await fetchTargetLists();
            startPolling();
        } else {
            alert(res.message || "登录失败");
        }
    } catch (err) {
        // 401 统一在 apiFetch 拦截
    } finally {
        btn.innerText = "登录控制台";
        btn.disabled = false;
    }
}

async function fetchTargetLists() {
    try {
        const [uRes, gRes] = await Promise.all([
            apiFetch("/bot/api/users"),
            apiFetch("/bot/api/groups")
        ]);

        const chatListEl = document.getElementById("chatList");
        chatListEl.innerHTML = "";

        if (uRes.data && Array.isArray(uRes.data)) {
            uRes.data.forEach(user => {
                const uid = user.user_id || user.user_openid || user.id;
                const displayName = user.nickname || "用户 " + String(uid).slice(-6);
                createChatItem(uid, false, displayName, uid);
            });
        }

        if (gRes.data && Array.isArray(gRes.data)) {
            gRes.data.forEach(group => {
                const gid = group.group_id || group.group_openid || group.id;
                const tag = group.grouptag || group.tag || group.tag_num ? `[群${group.grouptag || group.tag || group.tag_num}] ` : "";
                const displayName = tag + (group.nickname || "群聊 " + String(gid).slice(-6));
                createChatItem(gid, true, displayName, gid);
            });
        }
    } catch (err) {
        console.error("加载列表失败:", err);
    }
}

function createChatItem(id, isGroup, name, subId) {
    const chatListEl = document.getElementById("chatList");
    const div = document.createElement("div");
    div.className = "chat-item";
    if (currentTarget && currentTarget.id === id) div.classList.add("active");
    
    const badgeText = isGroup ? "群聊" : "私聊";
    div.innerHTML = `
        <div class="info">
            <div class="title">${escapeHtml(name)}</div>
            <div class="sub">${escapeHtml(subId)}</div>
        </div>
        <span class="badge">${badgeText}</span>
    `;
    
    div.onclick = () => selectChat(id, isGroup, name, div);
    chatListEl.appendChild(div);
}

async function selectChat(id, isGroup, name, element) {
    document.querySelectorAll(".chat-item").forEach(el => el.classList.remove("active"));
    if (element) element.classList.add("active");

    currentTarget = { id, isGroup, nickname: name };
    
    updateHeaderDisplay();
    document.getElementById("mainContainer").classList.add("show-chat");
    await loadHistory();
}

function updateHeaderDisplay() {
    if (!currentTarget) return;
    const titleText = document.getElementById("chatTitle");
    titleText.innerHTML = `
        ${escapeHtml(currentTarget.nickname)}
        <button class="btn-edit-name" onclick="openRenameModal()">改名</button>
    `;
}

function backToList() {
    document.getElementById("mainContainer").classList.remove("show-chat");
}

async function refreshCurrentChat() {
    if (currentTarget) {
        await loadHistory();
    }
    await fetchTargetLists();
}

async function loadHistory() {
    if (!currentTarget) return;
    try {
        const res = await apiFetch(`/bot/api/history?target_id=${encodeURIComponent(currentTarget.id)}&is_group=${currentTarget.isGroup}`);
        if (res.status === "success") {
            renderMessages(res.data || []);
        }
    } catch (err) {
        console.error("加载历史消息失败:", err);
    }
}

function renderMessages(messages) {
    const box = document.getElementById("messagesList");
    box.innerHTML = "";
    
    messages.forEach(msg => appendSingleMessage(msg, false));
    box.scrollTop = box.scrollHeight;
}

function appendSingleMessage(msg, isPending = false) {
    const box = document.getElementById("messagesList");
    // 判断是否为机器人发出的消息 (兼容 bot/assistant/user_id=BOT)
    const isBot = msg.role === "bot" || msg.role === "assistant" || msg.user_id === "BOT" || msg.user_id === "bot";
    const msgEl = document.createElement("div");
    msgEl.className = `msg ${isBot ? "bot" : "user"} ${isPending ? "pending" : ""}`;
    
    // 机器人名字固定显示为 Perseus
    let sender = isBot ? "Perseus" : (msg.nickname || msg.user_id || "用户");
    
    const parsedContent = parseMarkdown(msg.content);
    
    msgEl.innerHTML = `
        <div class="sender-info">${escapeHtml(sender)}${isPending ? " (发送中...)" : ""}</div>
        <div>${parsedContent}</div>
    `;
    box.appendChild(msgEl);
    box.scrollTop = box.scrollHeight;
}

async function sendMsg() {
    if (!currentTarget) return alert("请先选择聊天目标！");
    const input = document.getElementById("msgInput");
    const content = input.value.trim();
    if (!content) return;

    input.value = "";

    const tempMsg = { role: "assistant", content: content, user_id: "BOT" };
    appendSingleMessage(tempMsg, true);

    const url = currentTarget.isGroup ? "/bot/api/send_group" : "/bot/api/send_c2c";
    const payload = currentTarget.isGroup 
        ? { group_openid: currentTarget.id, content } 
        : { user_openid: currentTarget.id, content };

    try {
        const res = await apiFetch(url, {
            method: "POST",
            body: JSON.stringify(payload)
        });

        if (res.status === "success") {
            setTimeout(async () => {
                await loadHistory();
                await fetchTargetLists();
            }, 200);
        } else {
            alert(res.message || "发送失败");
        }
    } catch (err) {
        console.error("发送失败:", err);
        await loadHistory();
    }
}

function openRenameModal() {
    if (!currentTarget) return;
    const modal = document.getElementById("renameModal");
    const input = document.getElementById("renameInput");
    input.value = currentTarget.nickname;
    modal.classList.add("active");
    input.focus();
}

function closeRenameModal() {
    document.getElementById("renameModal").classList.remove("active");
}

async function submitRename() {
    const newName = document.getElementById("renameInput").value.trim();
    if (!newName) return alert("昵称不能为空！");

    const url = currentTarget.isGroup ? "/bot/api/set_group_nickname" : "/bot/api/set_user_nickname";
    const payload = currentTarget.isGroup 
        ? { group_id: currentTarget.id, nickname: newName } 
        : { user_id: currentTarget.id, nickname: newName };

    try {
        const res = await apiFetch(url, {
            method: "POST",
            body: JSON.stringify(payload)
        });

        if (res.status === "success") {
            currentTarget.nickname = newName;
            updateHeaderDisplay();
            closeRenameModal();
            await fetchTargetLists();
        } else {
            alert(res.message || "修改昵称失败");
        }
    } catch (err) {
        console.error("修改昵称失败:", err);
    }
}

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const res = await apiFetch("/bot/api/check_new?reset=true");
            if (res.data && res.data.has_new) {
                if (currentTarget) await loadHistory();
                await fetchTargetLists();
            }
        } catch (err) {
            console.error("轮询错误:", err);
        }
    }, 1500);
}

function clearAndExit(msg) {
    if (pollTimer) clearInterval(pollTimer);
    AUTH_KEY = "";
    currentTarget = null;
    document.getElementById("messagesList").innerHTML = "";
    document.getElementById("chatList").innerHTML = "";
    document.getElementById("mainContainer").classList.remove("show-chat");
    document.getElementById("mainContainer").style.display = "none";
    document.getElementById("loginCard").style.display = "block";
    if (msg) alert(msg);
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

window.onunload = function() {
    AUTH_KEY = "";
};
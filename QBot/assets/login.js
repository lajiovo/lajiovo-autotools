async function login() {
    const keyInput = document.getElementById("authKeyInput").value.trim();
    const errEl = document.getElementById("loginError");
    errEl.textContent = "";
    if (!keyInput) {
        errEl.textContent = "请输入密码！";
        return;
    }

    const btn = document.getElementById("loginBtn");
    btn.innerText = "正在登录...";
    btn.disabled = true;

    try {
        const res = await fetch("/bot/api/login", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key: keyInput })
        });
        const data = await res.json();
        if (res.ok && data.status === "success") {
            window.location.href = "/bot/assets/chat.html";
            return;
        }
        errEl.textContent = data.message || "登录失败";
    } catch (err) {
        errEl.textContent = "登录请求失败，请稍后重试";
    } finally {
        btn.innerText = "登录控制台";
        btn.disabled = false;
    }
}

async function tryAutoEnter() {
    try {
        const res = await fetch("/bot/api/users", { credentials: "include" });
        if (res.ok) {
            const data = await res.json();
            if (data.status === "success") {
                window.location.href = "/bot/assets/chat.html";
            }
        }
    } catch (err) {
        // 保持登录页
    }
}

window.addEventListener("DOMContentLoaded", tryAutoEnter);

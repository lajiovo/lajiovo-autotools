// 初始化默认 Key-Value 字典配置
window.addEventListener('DOMContentLoaded', () => {
    addKvRow('pushKvContainer', 'title', '');
    addKvRow('pushKvContainer', 'body', '');
    addKvRow('runKvContainer', 'task', '');
  });
  
  // 动态增删 Key-Value 节点
  function addKvRow(containerId, defaultKey = '', defaultValue = '') {
    const container = document.getElementById(containerId);
    const row = document.createElement('div');
    row.className = 'kv-row';
    row.innerHTML = `
      <input type="text" class="kv-key" placeholder="键 (Key)" value="${defaultKey}">
      <input type="text" class="kv-value" placeholder="值 (Value)" value="${defaultValue}">
      <button class="btn-del" onclick="this.parentElement.remove()">✕</button>
    `;
    container.appendChild(row);
  }
  
  // 搜集并构建字典发送
  function sendKvDict(endpoint, containerId) {
    const container = document.getElementById(containerId);
    const keys = container.querySelectorAll('.kv-key');
    const values = container.querySelectorAll('.kv-value');
    
    const payload = {};
    let hasKeys = false;
  
    keys.forEach((keyEl, index) => {
      const k = keyEl.value.trim();
      const v = values[index].value.trim();
      if (k !== '') {
        payload[k] = v;
        hasKeys = true;
      }
    });
  
    if (!hasKeys) {
      const errMsg = '未配置有效的 Key-Value 条目！';
      log(errMsg, 'err');
      alert(errMsg);
      return;
    }
  
    sendReq(endpoint, 'POST', payload);
  }
  
  // 打印日志到前端界面
  function log(msg, type = 'info') {
    const consoleLog = document.getElementById('consoleLog');
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    
    let formattedMsg = typeof msg === 'object' ? JSON.stringify(msg, null, 2) : msg;
    entry.innerHTML = `<span class="log-time">[${time}]</span>${formattedMsg}`;
    
    consoleLog.appendChild(entry);
    consoleLog.scrollTop = consoleLog.scrollHeight;
  }
  
  function clearLog() {
    document.getElementById('consoleLog').innerHTML = '';
  }
  
  // 通用请求发送函数（带日志控制台输出与自动 Alert 弹窗提醒）
  async function sendReq(endpoint, method = 'POST', data = null) {
    log(`发送请求: [${method}] ${endpoint}...`, 'info');
    
    const options = { method: method };
    if (data) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(data);
    }
  
    try {
      const res = await fetch(endpoint, options);
      const rawText = await res.text(); 
      let resData;
  
      try {
        resData = JSON.parse(rawText);
      } catch (e) {
        resData = rawText;
      }
      
      // 转换供 Alert 弹窗显示的文本内容
      const alertMsg = typeof resData === 'object' ? JSON.stringify(resData, null, 2) : resData;
  
      if (res.ok) {
        log(`[${res.status}] 请求成功:`, 'info');
        log(resData);
        alert(`[${res.status}] 请求成功:\n${alertMsg}`);
      } else {
        log(`[${res.status}] 接口异常:`, 'err');
        log(resData, 'err');
        alert(`[${res.status}] 接口异常:\n${alertMsg}`);
      }
      return resData;
    } catch (err) {
      log(`网络错误或请求失败: ${err.message}`, 'err');
      alert(`网络错误或请求失败:\n${err.message}`);
      return null;
    }
  }
  
  // 处理带有参数的 LK 路由请求
  function sendBookId() {
    const bookId = document.getElementById('bookId').value.trim();
    if (!bookId || isNaN(bookId)) {
      const errMsg = '请输入有效的数字 Book ID';
      log(errMsg, 'err');
      alert(errMsg);
      return;
    }
    const onlyVal = document.getElementById('onlySwitch').checked;
    const cacheVal = document.getElementById('cacheSwitch').checked;
  
    sendReq(`/lk/${bookId}/${onlyVal}/${cacheVal}`, 'GET');
  }
  
  // 返回主菜单（直接跳转网页）
  function goToMainMenu() {
    window.location.href = '/main/';
  }

  // 加载系统状态与仪表盘数据
  async function loadSystemStatusAndDashboard() {
    try {
      // 1. 获取 /main/sv/get 状态
      const svRes = await fetch('/main/sv/get');
      if (svRes.ok) {
        const svData = await svRes.json();
        const data = svData.data || svData;
        
        const hpEl = document.getElementById('svHandlepush');
        const mumuEl = document.getElementById('svMumu');
        const alasEl = document.getElementById('svAlas');

        if (hpEl) {
          hpEl.textContent = data.handlepush ? '🟢 运行中' : '🔴 已暂停';
          hpEl.style.color = data.handlepush ? '#10b981' : '#ef4444';
        }
        if (mumuEl) {
          mumuEl.textContent = data.mumu_running ? '🟢 运行中' : '⚪ 未运行';
          mumuEl.style.color = data.mumu_running ? '#10b981' : '#94a3b8';
        }
        if (alasEl) {
          alasEl.textContent = data.alas_running ? '🟢 运行中' : '⚪ 未运行';
          alasEl.style.color = data.alas_running ? '#10b981' : '#94a3b8';
        }
      }

      // 2. 获取 /main/ap/get 仪表盘 HTML
      const apRes = await fetch('/main/ap/get');
      if (apRes.ok) {
        const apData = await apRes.json();
        const htmlContent = apData.html || (apData.data && apData.data.html);
        const container = document.getElementById('dashboardContainer');
        if (container) {
          if (htmlContent && htmlContent.trim() !== '') {
            container.innerHTML = htmlContent;
          } else {
            container.innerHTML = '<p style="color: #94a3b8; font-size: 0.85rem; text-align: center;">暂无仪表盘缓存数据，请先执行 Playwright 任务获取。</p>';
          }
        }
      }
    } catch (e) {
      console.error('加载系统状态或仪表盘失败:', e);
    }
  }

  // 页面加载完成后自动加载一次，并每 10 秒自动轮询更新
  window.addEventListener('DOMContentLoaded', () => {
    loadSystemStatusAndDashboard();
    setInterval(loadSystemStatusAndDashboard, 10000);
  });
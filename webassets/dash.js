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
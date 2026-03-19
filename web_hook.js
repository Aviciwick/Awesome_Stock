// ==UserScript==
// @name         JoinQuant Log -> Feishu (Line Mode)
// @namespace    http://tampermonkey.net/
// @version      1.2
// @description  日志逐行发送到飞书
// @match        https://www.joinquant.com/algorithm/live/index*
// @grant        GM_xmlhttpRequest
// @connect      www.feishu.cn
// ==/UserScript==

(function () {
    'use strict';

    const WEBHOOK_URL = "https://www.feishu.cn/flow/api/trigger-webhook/dc854f069fb1488312514f304003f1df";

    let logContainer = null;
    let logs = new Set();   // 去重
    let queue = [];
    let sending = false;

    function init() {
        logContainer = document.getElementById('log');
        if (!logContainer) {
            setTimeout(init, 2000);
            return;
        }

        console.log('日志监听启动');

        collectLogs();

        const observer = new MutationObserver(() => {
            collectLogs();
        });

        observer.observe(logContainer, {
            childList: true,
            subtree: true
        });

        // 启动发送循环
        setInterval(processQueue, 1000);
    }

    function collectLogs() {
        const ps = logContainer.querySelectorAll('p');

        ps.forEach(p => {
            const text = p.innerText.trim();
            if (text && !logs.has(text)) {
                logs.add(text);

                queue.push({
                    time: new Date().toISOString(),
                    content: text
                });

                console.log('捕获:', text);
            }
        });
    }

    function processQueue() {
        if (sending || queue.length === 0) return;

        sending = true;

        const item = queue.shift();

        const payload = {
            time: item.time,
            content: item.content
        };

        GM_xmlhttpRequest({
            method: "POST",
            url: WEBHOOK_URL,
            headers: {
                "Content-Type": "application/json"
            },
            data: JSON.stringify(payload),
            onload: function () {
                sending = false;
            },
            onerror: function () {
                console.error("发送失败:", item);
                sending = false;
            }
        });
    }

    function getBacktestId() {
        const url = new URL(window.location.href);
        return url.searchParams.get("backtestId") || "unknown";
    }

    window.addEventListener('load', init);

})();
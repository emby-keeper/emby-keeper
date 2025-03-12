window.addEventListener('DOMContentLoaded', function() {
    const term = new Terminal({
        cursorBlink: false,
        macOptionIsMeta: true,
        allowTransparency: true,
        altClickMovesCursor: false,
        fontFamily: 'Cascadia Code, Courier New, Courier, -apple-system, Noto Sans, Helvetica Neue, Helvetica, Nimbus Sans L, Arial, Liberation Sans, PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, Source Han Sans SC, Source Han Sans CN, Microsoft YaHei, Wenquanyi Micro Hei, WenQuanYi Zen Hei, ST Heiti, SimHei, WenQuanYi Zen Hei Sharp, sans-serif',
        cursorStyle: 'bar',
        minimumContrastRatio: 7,
        smoothScrollDuration: 150,
        scrollback: 100000,
        rightClickSelectsWord: false,
        theme: {
            background: '#ffffff00',
            foreground: '#303030',
            cursor: '#303030',
            cursorAccent: '#ffffff00',
            selectionBackground: '#b1e2facc',
            selectionForeground: '#303030',
            selectionInactiveBackground: '#d8d8d8cc',
        }
    });

    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new SearchAddon.SearchAddon());

    term.open(document.getElementById("terminal"));
    fit.fit();
    console.debug("Web console init: ", term.cols, term.rows);

    const socket = io.connect("/pty", {'reconnection': false, 'transports': ['websocket']});

    function resize() {
        fit.fit();
        console.debug("Web console resize: ", term.cols, term.rows);
        const dims = { cols: term.cols, rows: term.rows };
        socket.emit("resize", dims);
    }

    function debounce(func, wait_ms) {
        let timeout;
        return function (...args) {
            const context = this;
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(context, args), wait_ms);
        };
    }

    function customKeyEventHandler(e) {
        if (e.type !== "keydown") {
            return true;
        }
        if (e.ctrlKey) {
            const key = e.key.toLowerCase();
            if (key === "v") {
                navigator.clipboard.readText().then((toPaste) => {
                    term.writeText(toPaste);
                });
                return false;
            } else if (key === "c" || key === "x") {
                const toCopy = term.getSelection();
                navigator.clipboard.writeText(toCopy);
                term.focus();
                return false;
            }
        }
        return true;
    }

    window.onresize = debounce(resize, 50);
    term.attachCustomKeyEventHandler(customKeyEventHandler);
    term.onData((data) => {
        console.debug(data)
        socket.emit("pty-input", { input: data });
    });

    var restartBtn = document.getElementById("restart-btn");
    restartBtn.addEventListener('click', () => {
        var statusMsg = document.getElementById("status-msg");
        statusMsg.textContent = "程序正在重启";
        console.info("Web console restarting.");

        // 先发送终止信号
        socket.emit("embykeeper_kill");

        // 等待一段时间后再重连
        setTimeout(() => {
            socket.disconnect();
            setTimeout(() => {
                socket.connect();
            }, 1000);
        }, 1000);
    });

    socket.on("connect_error", (error) => {
        console.error("Connection error:", error);
    });

    socket.on("error", (error) => {
        console.error("Socket error:", error);
    });

    socket.on("disconnect", (reason) => {
        var statusIcon = document.getElementById("status-icon");
        statusIcon.style.backgroundColor = "red";
        var statusMsg = document.getElementById("status-msg");
        statusMsg.textContent = "已断开连接";
        var restartIcon = document.getElementById("restart-icon");
        restartIcon.style.animationPlayState = "running";
        console.info("Web console disconnected: ", reason);
    });

    socket.on("pty-output", (data) => {
        console.log("Received pty-output, length:", data.output.length);
        term.write(data.output);
    });

    socket.on("connect", () => {
        console.log("Socket connected");
        var statusIcon = document.getElementById("status-icon");
        statusIcon.style.backgroundColor = "green";
        var statusMsg = document.getElementById("status-msg");
        statusMsg.textContent = "程序已连接";
        var restartIcon = document.getElementById("restart-icon");
        restartIcon.style.animationPlayState = "paused";
        console.info("Web console connected: ", term.cols, term.rows);
        term.focus();
        term.clear();
        term.reset();

        const dims = { cols: term.cols, rows: term.rows, instant: true };
        console.log("Sending embykeeper_start with dims:", dims);
        socket.emit("embykeeper_start", dims, (error) => {
            if (error) {
                console.error("Failed to start embykeeper:", error);
            }
        });
    });

    window.addEventListener('beforeunload', () => {
        if (socket.connected) {
            socket.disconnect();
        }
    });
});

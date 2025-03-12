window.addEventListener('DOMContentLoaded', function() {
    var statusMsg = document.getElementById("status-msg");
    var statusMsgBadge = document.getElementById("status-msg-badge");
    var tomlBox = document.getElementById('toml-box');
    var editor = CodeMirror(tomlBox, {
        mode: "toml",
        theme: "default",
        lineNumbers: false,
        scrollbarStyle: "overlay",
    });
    editor.setOption('readOnly', true);
    editor.on('change',function(inst){
        statusMsgBadge.classList.add("d-none");
    });

    const basePrefix = document.documentElement.getAttribute('data-prefix') || '';

    document.getElementById('save-btn').addEventListener('click', function() {
        statusMsg.innerText = '正在保存中';
        statusMsgBadge.classList.remove("d-none");
        axios.post(basePrefix + '/config/save', {"config": editor.getDoc().getValue()})
            .then(function(response) {
                document.getElementById('modal-data').textContent = response.data;
                var saveModal = new bootstrap.Modal(document.getElementById('saveModal'));
                saveModal.show();
                statusMsgBadge.classList.add("d-none");
            })
            .catch(function(error) {
                console.error(error);
                statusMsg.innerText = '保存失败, 请检查您的网络并重试';
            });
    });
    document.getElementById('example-btn').addEventListener('click', function() {
        statusMsg.innerText = '正在加载示例配置';
        statusMsgBadge.classList.remove("d-none");
        axios.get(basePrefix + '/config/example')
            .then(function(response) {
                editor.getDoc().setValue(response.data);
            })
            .catch(function(error) {
                console.error(error);
                statusMsg.innerText = '加载示例配置失败, 请检查您的网络并重试';
            });
    });
    axios.get(basePrefix + '/config/current')
        .then(function (response) {
            var statusIcon = document.getElementById("status-icon");
            statusIcon.style.backgroundColor = "green";
            editor.getDoc().setValue(response.data);
        })
        .catch(function (error) {
            if (error.response && error.response.status === 404) {
                statusMsg.innerText = '当前无配置设置, 请点击"示例"按钮以加载示例配置';
                statusMsgBadge.classList.remove("d-none");
            } else if (error.response && error.response.status === 400) {
                statusMsg.innerText = '当前配置字符串无效, 请点击"示例"按钮以加载示例配置';
                statusMsgBadge.classList.remove("d-none");
            } else {
                console.error(error);
                statusMsg.innerText = '无法连接, 请刷新页面';
                statusMsgBadge.classList.remove("d-none");
            }
        })
        .finally(function () {
            editor.setOption('readOnly', false);
        });
    function showCopyTooltip(text, event) {
        const tooltip = document.createElement('div');
        tooltip.className = 'copy-tooltip';
        tooltip.textContent = text;
        tooltip.style.left = `${event.pageX + 10}px`;
        tooltip.style.top = `${event.pageY + 10}px`;
        document.body.appendChild(tooltip);
        setTimeout(() => tooltip.remove(), 1000);
    }

    function copyText(text, event) {
        navigator.clipboard.writeText(text).then(() => {
            showCopyTooltip('已复制', event);
        }).catch(() => {
            showCopyTooltip('复制失败', event);
        });
    }

    document.getElementById('env-name').addEventListener('click', function(e) {
        copyText('EK_CONFIG', e);
    });

    document.getElementById('modal-data-box').addEventListener('click', function(e) {
        const modalData = document.getElementById('modal-data').textContent;
        copyText(modalData, e);
    });
})

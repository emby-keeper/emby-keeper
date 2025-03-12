import eventlet

eventlet.monkey_patch()

import os
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
import threading
from appdirs import user_data_dir
import socketio
import eventlet
import requests

EK_VERSION = "7.1.6"
APP_DATA_DIR = Path(user_data_dir("embykeeper"))
VERSION_CACHE_DIR = APP_DATA_DIR / "hf" / "version"


def setup_embykeeper():
    try:
        # 确保缓存目录存在
        VERSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_version = VERSION_CACHE_DIR / f"emby-keeper-{EK_VERSION}"
        cached_tarball = VERSION_CACHE_DIR / f"emby-keeper-{EK_VERSION}.tar.gz"

        if cached_version.exists():
            print(f"Using cached version from {cached_version}", flush=True)
            return True

        # 创建临时目录
        temp_dir = tempfile.mkdtemp()

        # 下载并解压（使用系统代理）
        print("Downloading EK...", flush=True)
        tarball_path = os.path.join(temp_dir, "embykeeper.tar.gz")

        if cached_tarball.exists():
            print(f"Using cached tarball from {cached_tarball}", flush=True)
            shutil.copy2(cached_tarball, tarball_path)
        else:
            # 使用固定的GitHub release下载地址
            release_url = f"https://github.com/emby-keeper/emby-keeper/archive/refs/tags/v{EK_VERSION}.tar.gz"
            subprocess.run(["wget", "-q", release_url, "-O", tarball_path], check=True)
            # 缓存下载的文件
            shutil.copy2(tarball_path, cached_tarball)

        subprocess.run(["tar", "xf", tarball_path, "-C", temp_dir], check=True)
        os.remove(tarball_path)  # 删除临时的 tar.gz 文件

        # 获取解压后的目录名
        extracted_dir = os.path.join(temp_dir, f"emby-keeper-{EK_VERSION}")

        # 混淆代码
        print("Obfuscating code...", flush=True)
        if not obfuscate_with_pyarmor(extracted_dir):
            raise Exception("Obfuscation failed")

        # 安装依赖
        print("Installing dependencies...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", os.path.join(extracted_dir, "requirements.txt")],
            check=True,
        )
        subprocess.run([sys.executable, "-m", "pip", "install", extracted_dir], check=True)

        # 将处理好的文件复制到缓存目录
        shutil.copytree(extracted_dir, cached_version, dirs_exist_ok=True)

        # 清理临时目录
        shutil.rmtree(temp_dir)

        return True
    except Exception as e:
        print(f"Error setting up EK: {e}", flush=True)
        return False


def obfuscate_with_pyarmor(package_path):
    try:
        # Install pyarmor if not already installed
        subprocess.run([sys.executable, "-m", "pip", "install", "pyarmor"], check=True)

        # Obfuscate packages
        for pkg in ["embykeeper", "embykeeperweb"]:
            pkg_dir = os.path.join(package_path, pkg)
            if not os.path.exists(pkg_dir):
                print(f"Package directory not found: {pkg_dir}", flush=True)
                continue

            print(f"Obfuscating {pkg}...", flush=True)

            # Run pyarmor with modified parameters
            subprocess.run(
                [
                    "pyarmor",
                    "gen",
                    "--recursive",
                    "--output",
                    os.path.join(package_path, "dist"),  # Specify output directory explicitly
                    pkg_dir,
                ],
                check=True,
            )

            # Handle obfuscated files
            dist_dir = os.path.join(package_path, "dist")
            if os.path.exists(dist_dir):
                # Copy all contents from dist directory back to package directory
                for item in os.listdir(dist_dir):
                    src = os.path.join(dist_dir, item)
                    dst = os.path.join(pkg_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                # Clean up dist directory
                shutil.rmtree(dist_dir)
            else:
                print(f"Dist directory not found after obfuscation for {pkg}", flush=True)
                return False

        return True
    except Exception as e:
        print(f"Error during obfuscation: {e}", flush=True)
        return False


def get_free_port():
    with eventlet.listen(("", 0)) as sock:
        return sock.getsockname()[1]


def run_gradio():
    import gradio as gr
    import random
    from time import time, ctime

    def promptgen(choice, num, artist):
        t = time()
        print(ctime(t))

        if choice == "Prompt Generator v0.1(Better quality)":
            prompt = open("pr1.txt").read().splitlines()
        elif choice == "Prompt Generator v0.2(More tags)":
            prompt = open("pr2.txt").read().splitlines()

        if int(num) < 1 or int(num) > 20:
            num = 10

        if int(artist) < 0 or int(artist) > 40:
            artist = 2

        vocab = len(prompt)
        generated = []
        artists_num = 0
        while len(sorted(set(generated), key=lambda d: generated.index(d))) < int(num):
            rand = random.choice(prompt)
            if rand.startswith("art by") and artists_num < int(artist):
                artists_num += 1
                generated.append(rand)
            elif not rand.startswith("art by"):
                generated.append(rand)
        print(", ".join(set(generated)) + "\n\n")
        return ", ".join(set(generated))

    demo = gr.Blocks()

    with demo:
        gr.HTML(
            """
                <div style="text-align: center; margin: 0 auto;">
                  <div style="display: inline-flex;align-items: center;gap: 0.8rem;font-size: 1.75rem;">
                    <h1 style="font-weight: 900; margin-bottom: 7px;margin-top:5px">
                      Simple Prompt Generator v0.6 (Gradio Demo)
                    </h1>
                  </div>
                  <p style="margin-bottom: 10px; font-size: 94%; line-height: 23px;">
                    Simple prompt generation script for Midjourney, DALLe, Stable and Disco diffusion and etc neural networks. <br> <p>More examples in <a class='link-info' href="https://github.com/WiNE-iNEFF/Simple_Prompt_Generator" target="_blank">Github</a> and <a class='link-info' href="https://wine-ineff.github.io/Simple_Prompt_Generator/" target="_blank">Project site</a></p>
                  </p>
                  <center>
                    <img style="display: inline-block, margin-right: 1%;" src='https://visitor-badge.laobi.icu/badge?page_id=WiNE-iNEFF.Simple_Prompt_Generator&left_color=red&right_color=green&left_text=Visitors' alt='visitor badge'>
                    <img style="display: inline-block, margin-right: 1%;" src='https://visitor-badge.laobi.icu/badge?page_id=WiNE-iNEFF.HF_Simple_Prompt_Generator&left_color=red&right_color=green&left_text=Visitors' alt='visitor badge'>
                  </center>
                </div>
            """
        )
        with gr.Column():
            model_size = gr.Radio(
                ["Prompt Generator v0.1(Better quality)", "Prompt Generator v0.2(More tags)"],
                label="Model Variant",
                value="Prompt Generator v0.1(Better quality)",
            )
            number = gr.Number(value="10", label="Num of tag (MAX 20)", show_label=True)
            artist = gr.Number(value="2", label="Num of artist (Standart 2)", show_label=True)
            out = gr.Textbox(lines=4, label="Generated Prompts")
        greet_btn = gr.Button("Generate")
        greet_btn.click(fn=promptgen, inputs=[model_size, number, artist], outputs=out, concurrency_limit=4)
        gr.HTML(
            """
                <div class="footer">
                    <div style='text-align: center;'>Simple Prompt Generator by <a href='https://twitter.com/wine_ineff' target='_blank'>Artsem Holub (WiNE-iNEFF)</a><br>More information about this demo and script your can find in <a class='link-info' href="https://github.com/WiNE-iNEFF/Simple_Prompt_Generator" target="_blank">Github</a> and <a class='link-info' href="https://wine-ineff.github.io/Simple_Prompt_Generator/" target="_blank">Project site</a></div>
               </div>
           """
        )

    demo.queue()
    print(f"Starting Gradio on port {gradio_port}", flush=True)
    demo.launch(
        server_name="0.0.0.0",
        server_port=gradio_port,
        share=False,
        debug=True,
        show_error=True,
        prevent_thread_lock=True,
    )


def run_proxy():
    sio_server = socketio.Server(async_mode="eventlet")
    app = socketio.WSGIApp(sio_server)

    sio_client = socketio.Client()

    # 存储 sid 映射关系
    client_sessions = {}

    @sio_server.on("connect", namespace="/pty")
    def connect(sid, environ):
        print(f"Client connected: {sid}")
        if not sio_client.connected:
            sio_client.connect(f"http://127.0.0.1:{ek_port}", namespaces=["/pty"])
        client_sessions[sid] = True

    @sio_server.on("disconnect", namespace="/pty")
    def disconnect(sid):
        print(f"Client disconnected: {sid}")
        client_sessions.pop(sid, None)
        if not client_sessions:
            sio_client.disconnect()

    @sio_server.on("*", namespace="/pty")
    def catch_all(event, sid, *args):
        if event not in ["connect", "disconnect"]:
            print(f"Forward to ek: {event}")
            sio_client.emit(event, *args, namespace="/pty")

    @sio_client.on("*", namespace="/pty")
    def forward_from_ek(event, *args):
        if event not in ["connect", "disconnect"]:
            print(f"Forward from ek: {event}")
            sio_server.emit(event, *args, namespace="/pty")

    def proxy_handler(environ, start_response):
        path = environ["PATH_INFO"]

        if path.startswith("/ek"):
            target = f"http://127.0.0.1:{ek_port}"
        else:
            target = f"http://127.0.0.1:{gradio_port}"

        url = f"{target}{path}"
        headers = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_key = key[5:].replace("_", "-").title()
                if header_key.lower() not in ["connection", "upgrade", "proxy-connection"]:
                    headers[header_key] = value
        content_length = environ.get("CONTENT_LENGTH")
        body = None
        if content_length:
            content_length = int(content_length)
            body = environ["wsgi.input"].read(content_length)

            if environ.get("CONTENT_TYPE"):
                headers["Content-Type"] = environ["CONTENT_TYPE"]
        resp = requests.request(
            method=environ["REQUEST_METHOD"],
            url=url,
            headers=headers,
            data=body,
            stream=True,
            allow_redirects=False,
        )

        start_response(f"{resp.status_code} {resp.reason}", list(resp.headers.items()))
        return resp.iter_content(chunk_size=4096)

    app.wsgi_app = proxy_handler
    eventlet.wsgi.server(eventlet.listen(("", 7860)), app)


if __name__ == "__main__":
    print("Setting up EK...", flush=True)
    if not setup_embykeeper():
        print("Failed to setup EK!", flush=True)
        sys.exit(1)

    # Get random ports for internal services
    gradio_port = get_free_port()
    ek_port = get_free_port()

    print(f"Using ports - Gradio: {gradio_port}, EK: {ek_port}", flush=True)

    gradio_thread = threading.Thread(target=run_gradio)
    gradio_thread.daemon = True
    gradio_thread.start()

    ek_thread = threading.Thread(
        target=lambda: subprocess.run(
            ["embykeeperweb", "--port", str(ek_port), "--prefix", "/ek", "--public"]
        )
    )
    ek_thread.daemon = True
    ek_thread.start()

    # Update proxy to use dynamic ports
    def proxy_handler(environ, start_response):
        path = environ["PATH_INFO"]

        if path.startswith("/ek"):
            target = f"http://127.0.0.1:{ek_port}"
        else:
            target = f"http://127.0.0.1:{gradio_port}"

        url = f"{target}{path}"
        headers = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_key = key[5:].replace("_", "-").title()
                if header_key.lower() not in ["connection", "upgrade", "proxy-connection"]:
                    headers[header_key] = value
        content_length = environ.get("CONTENT_LENGTH")
        body = None
        if content_length:
            content_length = int(content_length)
            body = environ["wsgi.input"].read(content_length)

            if environ.get("CONTENT_TYPE"):
                headers["Content-Type"] = environ["CONTENT_TYPE"]
        resp = requests.request(
            method=environ["REQUEST_METHOD"],
            url=url,
            headers=headers,
            data=body,
            stream=True,
            allow_redirects=False,
        )

        start_response(f"{resp.status_code} {resp.reason}", list(resp.headers.items()))
        return resp.iter_content(chunk_size=4096)

    # Start proxy server on fixed port 7860
    print("Starting proxy server on port 7860...", flush=True)
    run_proxy()

## 向 Embykeeper 贡献提交

欢迎! 很高兴你愿意让这个项目变得更好, 你可以通过以下方式开始修改代码:

1. Fork 本仓库
2. 通过 `git clone <forked repo>` 以将仓库克隆到本地
3. 启用一个虚拟空间, 例如:

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

4. 安装所有 requirements:

   ```bash
    pip install -r requirements_dev.txt
    pip install -e .
    pre-commit install
    ```

5. 修改代码以实现需求
6. 在提交 Pull Request 前, 请使用 `pre-commit` 工具检查代码:

   ```bash
    pre-commit run -a
    tox -e py
    pre-commit install
    ```

7. 在 [Pull Requests](https://github.com/embykeeper/embykeeper/pulls) 提交新 Pull Request.

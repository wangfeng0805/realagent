"""命令行入口（新版 / real_agent）。

本地调试用：从终端直接和小梦对话（不走 HTTP）。`python -m real_agent.app.cli` 进入交互循环。

重建说明：由 .so 重建（readable）。chat/main 签名对 .so 还原；对话委托 agent.graph.chat。
"""
import sys
from real_agent.app.agent.graph import chat as _chat


def chat(message: str, session_id: str = "default", model_id: "str | None" = None,
         user_id: "str | None" = None, mpsessid: "str | None" = None, dev: bool = True) -> str:
    return _chat(message, session_id=session_id, model_id=model_id,
                 user_id=user_id, mpsessid=mpsessid, dev=dev)


def main() -> None:
    """交互式 REPL：逐行读入问题，打印成稿。Ctrl-C/空行退出。"""
    print("小梦 · 西岸梦中心智能客服（命令行调试）。输入问题，空行退出。")
    session = "cli"
    while True:
        try:
            line = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            break
        print("小梦>", chat(line, session_id=session))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import sys
import threading
import zmq
from pylspclient import JsonRpcEndpoint
import subprocess
import platform


def main():
    if len(sys.argv) != 5:
        print("Usage: python lsp_transport.py <zmq_in_port> <zmq_out_port> <python_path> <is_stdio>")
        sys.exit(1)

    zmq_in_port = int(sys.argv[1])   # 主进程发消息到这里（transport 的 in）
    zmq_out_port = int(sys.argv[2])  # transport 发消息到这里（主进程的 in）
    python_path = sys.argv[3]
    is_stdio = sys.argv[4].lower() == 'true'

    context = zmq.Context()
    socket_in = context.socket(zmq.PAIR)
    socket_out = context.socket(zmq.PAIR)
    socket_in.connect(f"tcp://127.0.0.1:{zmq_in_port}")
    socket_out.bind(f"tcp://127.0.0.1:{zmq_out_port}")

    # 启动 pylsp
    cmd = [python_path, "-m", "pylsp"]
    kwargs = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs
    )

    endpoint = JsonRpcEndpoint(process.stdin, process.stdout)

    def send_to_main(msg):
        try:
            socket_out.send_pyobj(msg)
        except Exception as e:
            print(f"[Transport] ZMQ send error: {e}", file=sys.stderr)

    def read_lsp():
        while True:
            try:
                msg = endpoint.recv_response()
                if msg is None:
                    break
                send_to_main(msg)
            except Exception as e:
                print(f"[Transport] LSP read error: {e}", file=sys.stderr)
                break

    def read_stderr():
        for line in process.stderr:
            if line:
                print(f"[LSP stderr] {line.decode('utf-8', errors='replace').strip()}", file=sys.stderr)

    threading.Thread(target=read_lsp, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()

    # 主循环：接收来自主进程的请求
    try:
        while True:
            msg = socket_in.recv_pyobj()
            if isinstance(msg, dict):
                endpoint.send_request(msg)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            process.terminate()
            process.wait(timeout=2)
        except:
            process.kill()
        context.destroy()


if __name__ == "__main__":
    main()
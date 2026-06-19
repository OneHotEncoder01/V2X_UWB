import argparse
import os
import signal
import socket
import subprocess
import sys
import time


def run_command(args):
    subprocess.run(args, check=True)


def web_port_available(host, port):
    bind_host = "127.0.0.1" if host == "0.0.0.0" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, int(port)))
        except OSError:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Receive CAM messages and show them on the Django dashboard."
    )
    parser.add_argument("--port", default="/dev/ttyUSB0", help="RX board serial port")
    parser.add_argument("--baud", type=int, default=115200, help="RX board baud rate")
    parser.add_argument(
        "--encoding",
        choices=("auto", "hex", "binary"),
        default="auto",
        help="Serial frame encoding emitted by the RX sketch",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard host")
    parser.add_argument("--web-port", default="8000", help="Dashboard web port")
    parser.add_argument("--raw", action="store_true", help="Print raw serial frames")
    parser.add_argument(
        "--no-receiver",
        action="store_true",
        help="Start only the dashboard web server",
    )
    args = parser.parse_args()

    python = sys.executable
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "cam_dashboard.settings")

    run_command([python, "manage.py", "migrate", "--noinput"])

    if not web_port_available(args.host, args.web_port):
        print(
            f"Dashboard port {args.web_port} is already in use. "
            f"Stop the old dashboard or start this one with --web-port 8001.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    receiver = None
    if not args.no_receiver:
        receiver_command = [
            python,
            "manage.py",
            "receive_cam",
            "--port",
            args.port,
            "--baud",
            str(args.baud),
            "--encoding",
            args.encoding,
        ]
        if args.raw:
            receiver_command.append("--raw")

        receiver = subprocess.Popen(receiver_command, env=env)

    server_command = [
        python,
        "manage.py",
        "runserver",
        "--noreload",
        f"{args.host}:{args.web_port}",
    ]
    server = subprocess.Popen(server_command, env=env)

    print(f"Dashboard: http://{args.host}:{args.web_port}/", flush=True)
    if receiver is not None:
        print(f"Receiver: {args.port} at {args.baud} baud", flush=True)

    def stop_processes(*_):
        for process in (receiver, server):
            if process and process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, stop_processes)
    signal.signal(signal.SIGTERM, stop_processes)

    try:
        while True:
            if receiver is not None and receiver.poll() is not None:
                server.terminate()
                return receiver.returncode
            if server.poll() is not None:
                stop_processes()
                return server.returncode
            time.sleep(0.5)
    finally:
        stop_processes()


if __name__ == "__main__":
    raise SystemExit(main())

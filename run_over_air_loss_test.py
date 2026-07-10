"""
One-command over-the-air packet-loss test runner.

Starts the local RX logger, runs the sequenced TX script on the Raspberry Pi,
fetches the TX CSV, and analyzes TX-vs-RX packet delivery.
"""

import argparse
import json
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import serial_ports


DEFAULT_RATES = "10,20,30,40,45,50,60"
DEFAULT_PACKETS_PER_RATE = 5000


def default_local_python():
    venv_python = Path("venv/bin/python")
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def parse_rates(value):
    rates = []
    for item in value.split(","):
        item = item.strip()
        if item:
            rates.append(float(item))
    if not rates:
        raise argparse.ArgumentTypeError("at least one rate is required")
    return rates


def ssh_options(args, control_master="auto"):
    options = ["ssh"]
    if args.ssh_config:
        options.extend(["-F", args.ssh_config])
    options.extend(
        [
            "-o",
            f"ControlPath={args.control_path}",
            "-o",
            f"ControlMaster={control_master}",
            "-o",
            f"ControlPersist={args.control_persist}",
        ]
    )
    return options


def ssh_command(args, remote_command, control_master="auto", tty=False):
    command = ssh_options(args, control_master)
    if tty:
        command.append("-tt")
    command.extend([args.pi_host, remote_command])
    return command


def scp_command(args, remote_path, local_path):
    command = ["scp"]
    if args.ssh_config:
        command.extend(["-F", args.ssh_config])
    command.extend(
        [
            "-o",
            f"ControlPath={args.control_path}",
            "-o",
            "ControlMaster=auto",
            "-o",
            f"ControlPersist={args.control_persist}",
            f"{args.pi_host}:{remote_path}",
            str(local_path),
        ]
    )
    return command


def run_interactive(command, description):
    print(f"[RUNNER] {description}", flush=True)
    subprocess.run(command, check=True)


def start_control_master(args):
    command = ssh_options(args, control_master="yes")
    command.extend(["-MNf", args.pi_host])
    run_interactive(command, "Opening SSH control connection")


def close_control_master(args):
    command = ssh_options(args)
    command.extend(["-O", "exit", args.pi_host])
    subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def prepare_sudo(args):
    if args.no_service_control or args.skip_sudo_prepare:
        return
    run_interactive(
        ssh_command(args, "sudo -v", tty=True),
        "Preparing sudo on the Pi; enter the Pi sudo password if prompted",
    )


def estimated_rx_duration(args, rates):
    if args.rx_duration:
        return args.rx_duration
    if args.packets_per_rate:
        seconds = sum(args.packets_per_rate / min(rate, args.expected_ceiling_hz) for rate in rates)
    else:
        seconds = len(rates) * args.duration
    return seconds + args.rx_margin


def remote_tx_command(args, remote_tx_csv):
    tx_args = [
        args.remote_python,
        "over_air_loss_tx.py",
        "--test-id",
        str(args.test_id),
        "--rates",
        args.rates,
        "--output",
        remote_tx_csv,
        "--gps-timeout",
        str(args.gps_timeout),
    ]
    if args.packets_per_rate:
        tx_args.extend(["--packets-per-rate", str(args.packets_per_rate)])
    else:
        tx_args.extend(["--duration", str(args.duration)])
    if args.tx_port:
        tx_args.extend(["--tx-port", args.tx_port])
    if args.mock_gps:
        tx_args.append("--mock-gps")
    if args.no_gps_activate:
        tx_args.append("--no-gps-activate")

    quoted_tx = " ".join(shlex.quote(item) for item in tx_args)
    commands = ["set -e", f"cd {shlex.quote(args.remote_dir)}"]

    if not args.no_service_control:
        service = shlex.quote(args.service_name)
        commands.extend(
            [
                "sudo -n true",
                "(while true; do sudo -n true; sleep 60; done) >/dev/null 2>&1 & SUDO_KEEP=$!",
                (
                    "cleanup() { status=$?; "
                    'kill "$SUDO_KEEP" 2>/dev/null || true; '
                    f"sudo -n systemctl start {service} || true; "
                    'exit "$status"; }'
                ),
                "trap cleanup EXIT INT TERM",
                f"sudo -n systemctl stop {service}",
            ]
        )

    commands.append(quoted_tx)
    return "; ".join(commands)


def start_rx(args, rx_csv, rx_console, rx_duration):
    command = [
        args.local_python,
        "over_air_loss_rx.py",
        "--port",
        args.rx_port,
        "--duration",
        f"{rx_duration:.1f}",
        "--output",
        str(rx_csv),
        "--test-id",
        str(args.test_id),
        "--progress-interval",
        str(args.progress_interval),
    ]
    if args.rx_encoding:
        command.extend(["--encoding", args.rx_encoding])

    print(f"[RUNNER] Starting local RX for up to {rx_duration / 60:.1f} min", flush=True)
    rx_log = rx_console.open("w", encoding="utf-8")
    process = subprocess.Popen(command, stdout=rx_log, stderr=subprocess.STDOUT, text=True)
    return process, rx_log


def stop_rx(process):
    if process.poll() is not None:
        return process.returncode
    process.send_signal(signal.SIGINT)
    try:
        return process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait()


def write_metadata(path, args, rates, rx_duration):
    data = {
        "test_id": args.test_id,
        "rates": rates,
        "packets_per_rate": args.packets_per_rate,
        "duration": args.duration,
        "rx_duration": rx_duration,
        "rx_port": args.rx_port,
        "pi_host": args.pi_host,
        "remote_dir": args.remote_dir,
        "service_control": not args.no_service_control,
        "created_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run an automated over-the-air loss test")
    parser.add_argument("--pi-host", default="pi")
    parser.add_argument("--ssh-config", default=str(Path.home() / ".ssh" / "config"))
    parser.add_argument("--remote-dir", default="/home/sinan/CAM_Broadcaster")
    parser.add_argument("--remote-python", default="./bin/python")
    parser.add_argument("--local-python", default=default_local_python())
    parser.add_argument("--rx-port", default=serial_ports.rx_port())
    parser.add_argument("--rx-encoding", default="auto")
    parser.add_argument("--tx-port")
    parser.add_argument("--rates", default=DEFAULT_RATES)
    parser.add_argument("--packets-per-rate", type=int, default=DEFAULT_PACKETS_PER_RATE)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--test-id", type=int, default=int(time.time()) & 0xFFF)
    parser.add_argument("--gps-timeout", type=float, default=60.0)
    parser.add_argument("--mock-gps", action="store_true")
    parser.add_argument("--no-gps-activate", action="store_true")
    parser.add_argument("--output-dir", default="over_air_runs")
    parser.add_argument("--run-name")
    parser.add_argument("--rx-duration", type=float)
    parser.add_argument("--rx-warmup", type=float, default=2.0)
    parser.add_argument("--rx-margin", type=float, default=180.0)
    parser.add_argument("--expected-ceiling-hz", type=float, default=45.0)
    parser.add_argument("--progress-interval", type=float, default=30.0)
    parser.add_argument("--control-persist", default="3h")
    parser.add_argument("--control-path")
    parser.add_argument("--no-control-master", action="store_true")
    parser.add_argument("--skip-sudo-prepare", action="store_true")
    parser.add_argument("--no-service-control", action="store_true")
    parser.add_argument("--service-name", default="cam_transmitter")
    args = parser.parse_args()

    rates = parse_rates(args.rates)
    if args.packets_per_rate is not None and args.packets_per_rate <= 0:
        parser.error("--packets-per-rate must be positive")
    if args.test_id < 0 or args.test_id >= 4096:
        parser.error("--test-id must fit in 12 bits when seq-bits is 20")
    if args.ssh_config and not Path(args.ssh_config).exists():
        args.ssh_config = ""

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or f"{stamp}_test{args.test_id}"
    run_dir = Path(args.output_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    if not args.control_path:
        args.control_path = str(Path.home() / ".ssh" / f"v2x_uwb_mux_{args.test_id}")

    rx_csv = run_dir / f"over_air_rx_{args.test_id}.csv"
    tx_csv = run_dir / f"over_air_tx_{args.test_id}.csv"
    summary_csv = run_dir / f"over_air_loss_summary_{args.test_id}.csv"
    rx_console = run_dir / "rx_console.log"
    tx_console = run_dir / "tx_console.log"
    metadata = run_dir / "run_metadata.json"
    remote_tx_csv = f"over_air_tx_{args.test_id}.csv"
    rx_duration = estimated_rx_duration(args, rates)

    write_metadata(metadata, args, rates, rx_duration)

    print("=== Automated over-the-air packet-loss test ===", flush=True)
    print(f"Run directory: {run_dir}", flush=True)
    print(f"Test id: {args.test_id}", flush=True)
    print(f"Rates: {args.rates} Hz", flush=True)
    print(f"Packets per rate: {args.packets_per_rate}", flush=True)

    if not args.no_control_master:
        start_control_master(args)
    prepare_sudo(args)

    rx_process = None
    rx_log = None
    tx_process = None
    tx_returncode = 1
    try:
        rx_process, rx_log = start_rx(args, rx_csv, rx_console, rx_duration)
        time.sleep(args.rx_warmup)

        remote_command = remote_tx_command(args, remote_tx_csv)
        print("[RUNNER] Starting remote TX; progress is written to tx_console.log", flush=True)
        with tx_console.open("w", encoding="utf-8") as tx_log:
            tx_process = subprocess.Popen(
                ssh_command(args, remote_command),
                stdout=tx_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            tx_returncode = tx_process.wait()

        print(f"[RUNNER] Remote TX exited with code {tx_returncode}", flush=True)
    finally:
        if tx_process is not None and tx_process.poll() is None:
            tx_process.terminate()
            try:
                tx_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tx_process.kill()
        if rx_process is not None:
            print("[RUNNER] Stopping local RX logger", flush=True)
            stop_rx(rx_process)
        if rx_log is not None:
            rx_log.close()

    try:
        print("[RUNNER] Fetching TX CSV from Pi", flush=True)
        subprocess.run(scp_command(args, f"{args.remote_dir}/{remote_tx_csv}", tx_csv), check=True)

        print("[RUNNER] Analyzing packet loss", flush=True)
        subprocess.run(
            [
                args.local_python,
                "analyze_over_air_loss.py",
                str(tx_csv),
                str(rx_csv),
                "--test-id",
                str(args.test_id),
                "--output",
                str(summary_csv),
            ],
            check=True,
        )
    finally:
        if not args.no_control_master:
            close_control_master(args)

    print(f"[RUNNER] Complete. Summary: {summary_csv}", flush=True)
    return tx_returncode


if __name__ == "__main__":
    raise SystemExit(main())

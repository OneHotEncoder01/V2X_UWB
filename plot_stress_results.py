"""
Plot stresstest results from CSV output.

Usage:
    python plot_stress_results.py stress_test_results.csv
"""

import sys
import csv
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

def load_results(csv_file):
    """Load CSV results into lists."""
    targets = []
    achieved = []
    success_rates = []
    latencies_avg = []
    latencies_min = []
    latencies_max = []

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            targets.append(float(row['target_hz']))
            achieved.append(float(row['achieved_hz']))

            attempts = int(row['attempts'])
            successes = int(row['successes'])
            success_rate = 100 * successes / attempts if attempts > 0 else 0
            success_rates.append(success_rate)

            latencies_avg.append(float(row['avg_latency_ms']))
            latencies_min.append(float(row['min_latency_ms']))
            latencies_max.append(float(row['max_latency_ms']))

    return {
        'targets': targets,
        'achieved': achieved,
        'success_rates': success_rates,
        'latencies_avg': latencies_avg,
        'latencies_min': latencies_min,
        'latencies_max': latencies_max,
    }


def plot_results(csv_file, output_prefix='stress_test'):
    """Generate plots from stresstest results."""
    data = load_results(csv_file)

    # Plot 1: Target vs Achieved rate
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(data['targets'], data['targets'], 'k--', label='Ideal (target=achieved)', linewidth=1)
    ax.plot(data['targets'], data['achieved'], 'o-', color='#0f766e', linewidth=2, markersize=6, label='Achieved')
    ax.set_xlabel('Target Rate (Hz)', fontsize=11)
    ax.set_ylabel('Achieved Rate (Hz)', fontsize=11)
    ax.set_title('CAM Transmission Rate: Target vs. Achieved', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(f'{output_prefix}_rate.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {output_prefix}_rate.png")

    # Plot 2: Success rate vs target Hz
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ['#10b981' if sr >= 95 else '#f59e0b' if sr >= 80 else '#ef4444' for sr in data['success_rates']]
    ax.bar(data['targets'], data['success_rates'], color=colors, alpha=0.8, width=2)
    ax.axhline(100, color='green', linestyle='--', linewidth=1, alpha=0.5, label='Perfect')
    ax.axhline(95, color='orange', linestyle='--', linewidth=1, alpha=0.5, label='Acceptable (95%)')
    ax.set_xlabel('Target Rate (Hz)', fontsize=11)
    ax.set_ylabel('Success Rate (%)', fontsize=11)
    ax.set_title('CAM Transmission Success Rate by Rate', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.3, axis='y')
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(f'{output_prefix}_success.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {output_prefix}_success.png")

    # Plot 3: Latency vs rate
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(data['targets'], data['latencies_avg'], 'o-', color='#0f766e', linewidth=2,
            markersize=6, label='Mean latency')
    ax.fill_between(data['targets'], data['latencies_min'], data['latencies_max'],
                     alpha=0.2, color='#0f766e', label='Min–Max range')
    ax.axhline(50, color='red', linestyle='--', linewidth=1, alpha=0.5, label='ETSI limit (50 ms)')
    ax.set_xlabel('Target Rate (Hz)', fontsize=11)
    ax.set_ylabel('Latency (ms)', fontsize=11)
    ax.set_title('TX Latency by Rate', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(f'{output_prefix}_latency.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {output_prefix}_latency.png")

    # Summary stats
    print("\n=== Stresstest Summary ===")
    print(f"Max target rate tested: {max(data['targets'])} Hz")
    print(f"Max achieved rate: {max(data['achieved']):.1f} Hz")
    print(f"Success rates: {min(data['success_rates']):.1f}% – {max(data['success_rates']):.1f}%")
    print(f"Latency range: {min(data['latencies_min']):.1f} – {max(data['latencies_max']):.1f} ms")

    # Find saturation point (success rate drops below 95%)
    for i, sr in enumerate(data['success_rates']):
        if sr < 95:
            print(f"Saturation point: ~{data['targets'][i]:.0f} Hz (success rate drops to {sr:.1f}%)")
            break
    else:
        print("No saturation observed within tested rates")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python plot_stress_results.py <csv_file> [output_prefix]")
        sys.exit(1)

    csv_file = sys.argv[1]
    output_prefix = sys.argv[2] if len(sys.argv) > 2 else 'stress_test'

    plot_results(csv_file, output_prefix)

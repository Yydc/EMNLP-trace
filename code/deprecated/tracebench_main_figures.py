"""
TraceBench Main Figures (Consolidated Version)
==============================================
Only 3 main figures for the paper body.
Additional figures can go to appendix.

Figure 1: Per-turn dynamics (2×3 grid) - RQ1+RQ2
Figure 2: Scaling + Poison (2-panel) - RQ2+RQ3  
Figure 3: Gap + Ablation (2-panel) - RQ1+RQ2
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.gridspec import GridSpec

# ==============================================================================
# Global Style
# ==============================================================================
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 11,
    'legend.fontsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.linewidth': 0.8,
})

COLORS = {
    'Base': '#E69F00',
    'Self': '#56B4E9',
    'Hard': '#009E73',
    'RGDP': '#CC79A7',
}
MARKER = 'D'


# ==============================================================================
# FIGURE 1: Per-Turn Dynamics (Main RQ1+RQ2 Figure)
# Layout: 2 rows (models) × 3 columns (buckets)
# ==============================================================================
def figure1_perturn_dynamics():
    """
    Main dynamics figure showing Pass@1 (solid) and Hit@1 (dashed) over turns.
    """
    
    # ===== SIMULATED DATA =====
    turns = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    
    data = {
        '$M_4$ (GPT-4.1)': {
            'Single-func': {
                'Base': {'pass': [42, 52, 58, 62, 65, 67, 68, 69, 69, 70],
                         'hit':  [48, 45, 42, 40, 38, 36, 35, 34, 33, 32]},
                'Self': {'pass': [45, 56, 63, 68, 71, 73, 74, 75, 75, 75],
                         'hit':  [52, 50, 47, 45, 43, 42, 41, 40, 39, 39]},
                'Hard': {'pass': [55, 65, 70, 73, 74, 74, 73, 72, 71, 70],
                         'hit':  [88, 87, 86, 85, 84, 83, 82, 81, 80, 79]},
                'RGDP': {'pass': [52, 64, 72, 78, 81, 83, 84, 85, 86, 86],
                         'hit':  [68, 74, 78, 82, 85, 87, 88, 89, 90, 90]},
            },
            'Multi-func': {
                'Base': {'pass': [35, 44, 50, 54, 57, 59, 60, 61, 61, 62],
                         'hit':  [38, 35, 32, 30, 28, 27, 26, 25, 24, 24]},
                'Self': {'pass': [38, 48, 55, 60, 63, 65, 66, 67, 67, 68],
                         'hit':  [42, 40, 37, 35, 34, 33, 32, 31, 30, 30]},
                'Hard': {'pass': [48, 56, 60, 62, 62, 61, 60, 58, 57, 56],
                         'hit':  [82, 80, 78, 76, 74, 72, 70, 68, 66, 65]},
                'RGDP': {'pass': [45, 56, 64, 70, 74, 77, 79, 80, 81, 82],
                         'hit':  [58, 66, 72, 76, 79, 81, 82, 83, 84, 84]},
            },
            'Deep-call': {
                'Base': {'pass': [25, 34, 40, 44, 47, 49, 50, 51, 51, 51],
                         'hit':  [22, 20, 18, 17, 16, 15, 14, 14, 13, 13]},
                'Self': {'pass': [28, 38, 45, 50, 53, 55, 56, 57, 57, 58],
                         'hit':  [26, 24, 22, 21, 20, 19, 18, 18, 17, 17]},
                'Hard': {'pass': [38, 45, 48, 49, 48, 46, 44, 42, 40, 38],
                         'hit':  [72, 70, 67, 64, 61, 58, 55, 52, 49, 47]},
                'RGDP': {'pass': [35, 46, 54, 60, 65, 68, 70, 72, 73, 74],
                         'hit':  [48, 56, 62, 67, 71, 74, 76, 78, 79, 80]},
            },
        },
        '$M_6$ (GPT-4o)': {
            'Single-func': {
                'Base': {'pass': [52, 62, 68, 72, 75, 77, 78, 79, 79, 79],
                         'hit':  [55, 52, 49, 47, 45, 44, 43, 42, 41, 41]},
                'Self': {'pass': [55, 66, 73, 78, 81, 83, 84, 85, 85, 85],
                         'hit':  [60, 57, 54, 52, 50, 49, 48, 47, 46, 46]},
                'Hard': {'pass': [62, 72, 77, 79, 79, 78, 77, 76, 75, 74],
                         'hit':  [90, 89, 88, 87, 86, 85, 84, 83, 82, 81]},
                'RGDP': {'pass': [60, 72, 80, 85, 88, 90, 91, 92, 92, 93],
                         'hit':  [72, 78, 83, 87, 89, 91, 92, 93, 93, 94]},
            },
            'Multi-func': {
                'Base': {'pass': [42, 52, 58, 62, 65, 67, 68, 69, 69, 70],
                         'hit':  [42, 39, 36, 34, 32, 31, 30, 29, 28, 28]},
                'Self': {'pass': [45, 56, 64, 70, 73, 75, 76, 77, 77, 78],
                         'hit':  [48, 45, 42, 40, 39, 38, 37, 36, 35, 35]},
                'Hard': {'pass': [55, 64, 68, 69, 68, 66, 64, 62, 60, 58],
                         'hit':  [85, 83, 80, 78, 75, 73, 71, 69, 67, 65]},
                'RGDP': {'pass': [52, 64, 73, 79, 83, 86, 88, 89, 90, 90],
                         'hit':  [62, 70, 76, 81, 84, 86, 88, 89, 90, 90]},
            },
            'Deep-call': {
                'Base': {'pass': [32, 42, 48, 52, 55, 57, 58, 59, 59, 60],
                         'hit':  [28, 26, 24, 22, 21, 20, 19, 19, 18, 18]},
                'Self': {'pass': [35, 46, 54, 60, 64, 67, 68, 69, 70, 70],
                         'hit':  [32, 30, 28, 27, 26, 25, 24, 23, 23, 22]},
                'Hard': {'pass': [45, 52, 55, 55, 53, 50, 47, 44, 42, 40],
                         'hit':  [76, 73, 70, 66, 62, 58, 54, 50, 47, 44]},
                'RGDP': {'pass': [42, 54, 63, 70, 75, 79, 82, 84, 85, 86],
                         'hit':  [52, 62, 70, 76, 80, 83, 85, 87, 88, 89]},
            },
        },
    }
    # ===== END DATA =====
    
    models = list(data.keys())
    buckets = ['Single-func', 'Multi-func', 'Deep-call']
    strategies = ['Base', 'Self', 'Hard', 'RGDP']
    
    fig, axes = plt.subplots(2, 3, figsize=(10, 5.5), sharex=True)
    
    for i, model in enumerate(models):
        for j, bucket in enumerate(buckets):
            ax = axes[i, j]
            
            for strategy in strategies:
                pass_data = data[model][bucket][strategy]['pass']
                hit_data = data[model][bucket][strategy]['hit']
                
                ax.plot(turns, pass_data, color=COLORS[strategy], 
                       marker=MARKER, markersize=4, linewidth=1.8)
                ax.plot(turns, hit_data, color=COLORS[strategy],
                       linestyle='--', linewidth=1.2, alpha=0.7)
            
            ax.set_xlim(0.5, 10.5)
            ax.set_ylim(10, 100)
            ax.set_xticks([2, 4, 6, 8, 10])
            ax.grid(True, alpha=0.3)
            
            if i == 0:
                ax.set_title(bucket, fontsize=11, fontweight='bold')
            if j == 0:
                ax.set_ylabel(f'{model}\nRate (%)', fontsize=10)
            if i == 1:
                ax.set_xlabel('Turn', fontsize=10)
    
    # Legend
    legend_elements = [
        Line2D([0], [0], color=COLORS[s], marker=MARKER, markersize=5, 
               linewidth=1.8, label=s if s != 'RGDP' else 'RGDP (Ours)') 
        for s in strategies
    ]
    legend_elements.extend([
        Line2D([0], [0], color='gray', linewidth=1.8, label='Pass@1'),
        Line2D([0], [0], color='gray', linewidth=1.2, linestyle='--', label='Hit@1')
    ])
    
    fig.legend(handles=legend_elements, loc='upper center', 
               bbox_to_anchor=(0.5, 1.02), ncol=6, frameon=False, fontsize=9)
    
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig('fig1_dynamics.pdf')
    plt.savefig('fig1_dynamics.png')
    print("✓ Figure 1: fig1_dynamics.pdf")
    plt.close()


# ==============================================================================
# FIGURE 2: Scaling + Poison (2-panel)
# ==============================================================================
def figure2_scaling_poison():
    """
    Two-panel figure:
    (a) Scaling behavior across models
    (b) Poison robustness
    """
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    
    # ===== Panel (a): Scaling =====
    models = ['$M_1$\n(7B)', '$M_2$\n(14B)', '$M_3$\n(32B)', 
              '$M_4$\n(GPT-4.1)', '$M_5$\n(Claude)', '$M_6$\n(GPT-4o)']
    x = np.arange(len(models))
    
    scaling_data = {
        'Base': [32.4, 41.2, 52.6, 58.3, 62.1, 65.4],
        'Self': [35.8, 45.1, 56.3, 62.7, 66.8, 69.2],
        'Hard': [42.1, 51.4, 58.2, 60.4, 62.1, 63.8],
        'RGDP': [44.6, 54.8, 64.1, 70.2, 74.6, 77.4],
    }
    
    for strategy in ['Base', 'Self', 'Hard', 'RGDP']:
        label = strategy if strategy != 'RGDP' else 'RGDP (Ours)'
        ax1.plot(x, scaling_data[strategy], color=COLORS[strategy],
                marker=MARKER, markersize=8, linewidth=2, label=label)
    
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, fontsize=9)
    ax1.set_ylabel('Pass@1 (%)', fontsize=11)
    ax1.set_xlabel('Model', fontsize=11)
    ax1.set_ylim(25, 85)
    ax1.legend(loc='lower right', fontsize=9, frameon=True, edgecolor='gray')
    ax1.set_title('(a) Scaling Behavior', fontsize=11, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    
    # Annotation
    ax1.annotate('Hard degrades', xy=(5, 63.8), xytext=(4, 52),
                fontsize=8, color=COLORS['Hard'],
                arrowprops=dict(arrowstyle='->', color=COLORS['Hard'], lw=1))
    
    # ===== Panel (b): Poison =====
    poison_ratios = [0, 25, 50, 75, 100]
    poison_data = {
        'Hard': [58.2, 52.4, 44.6, 36.8, 28.4],
        'RGDP': [64.1, 62.8, 60.2, 57.4, 54.8],
    }
    base_ref = 52.6
    
    ax2.plot(poison_ratios, poison_data['Hard'], color=COLORS['Hard'],
            marker=MARKER, markersize=8, linewidth=2, label='Hard')
    ax2.plot(poison_ratios, poison_data['RGDP'], color=COLORS['RGDP'],
            marker=MARKER, markersize=8, linewidth=2, label='RGDP (Ours)')
    ax2.axhline(y=base_ref, color=COLORS['Base'], linestyle='--', 
               linewidth=2, alpha=0.7, label='Base (ref)')
    
    # Shade danger zone
    ax2.fill_between(poison_ratios, 0, base_ref,
                    where=[h < base_ref for h in poison_data['Hard']],
                    alpha=0.15, color='red', interpolate=True)
    
    ax2.set_xlabel('Poison Ratio (%)', fontsize=11)
    ax2.set_ylabel('Pass@1 (%)', fontsize=11)
    ax2.set_xlim(-5, 105)
    ax2.set_ylim(20, 75)
    ax2.set_xticks(poison_ratios)
    ax2.legend(loc='lower left', fontsize=9, frameon=True, edgecolor='gray')
    ax2.set_title('(b) Robustness to Poisoned Hints', fontsize=11, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    
    ax2.text(70, 30, 'Hard < Base', fontsize=8, color='darkred', style='italic')
    
    plt.tight_layout()
    plt.savefig('fig2_scaling_poison.pdf')
    plt.savefig('fig2_scaling_poison.png')
    print("✓ Figure 2: fig2_scaling_poison.pdf")
    plt.close()


# ==============================================================================
# FIGURE 3: Gap Analysis + Ablation (2-panel)
# ==============================================================================
def figure3_gap_ablation():
    """
    Two-panel figure:
    (a) Traceability gap visualization (scatter + bar)
    (b) RGDP ablation study
    """
    
    fig = plt.figure(figsize=(10, 4))
    gs = GridSpec(1, 3, width_ratios=[1.2, 0.8, 1], wspace=0.35)
    
    ax1 = fig.add_subplot(gs[0])  # Gap scatter
    ax2 = fig.add_subplot(gs[1])  # Gap bar
    ax3 = fig.add_subplot(gs[2])  # Ablation
    
    # ===== Panel (a): Gap Scatter =====
    models = ['$M_1$', '$M_2$', '$M_3$', '$M_4$', '$M_5$', '$M_6$']
    pass_at_1 = [23.8, 32.4, 44.1, 51.2, 55.8, 58.4]
    hit_at_1 = [10.6, 14.8, 19.4, 24.1, 27.4, 30.1]
    colors = ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#CC79A7']
    
    for i, (p, h, m) in enumerate(zip(pass_at_1, hit_at_1, models)):
        ax1.scatter(p, h, c=colors[i], s=120, marker='o', 
                   edgecolors='black', linewidth=0.8, zorder=5)
        ax1.annotate(m, (p, h), xytext=(4, 4), textcoords='offset points', fontsize=8)
    
    ax1.plot([0, 65], [0, 65], 'k--', alpha=0.3)
    ax1.fill_between([0, 65], [0, 65], 65, alpha=0.08, color='red')
    
    ax1.set_xlabel('Pass@1 (%)', fontsize=10)
    ax1.set_ylabel('Hit@1 (%)', fontsize=10)
    ax1.set_xlim(0, 65)
    ax1.set_ylim(0, 65)
    ax1.set_aspect('equal')
    ax1.set_title('(a) Pass@1 vs Hit@1\n(Deep-call)', fontsize=10, fontweight='bold')
    ax1.text(40, 15, '"Lucky"\nzone', fontsize=8, color='darkred', 
             ha='center', style='italic')
    ax1.grid(True, alpha=0.3)
    
    # ===== Panel (a2): Gap Bar =====
    gaps = [p - h for p, h in zip(pass_at_1, hit_at_1)]
    x = np.arange(len(models))
    bars = ax2.bar(x, gaps, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
    
    ax2.set_ylabel('Gap (P@1−H@1)', fontsize=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels(models, fontsize=8)
    ax2.set_ylim(0, 35)
    ax2.set_title('(a\') Traceability\nGap', fontsize=10, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')
    
    for bar, gap in zip(bars, gaps):
        ax2.annotate(f'{gap:.0f}', xy=(bar.get_x() + bar.get_width()/2, gap),
                    xytext=(0, 2), textcoords="offset points",
                    ha='center', va='bottom', fontsize=8)
    
    # ===== Panel (b): Ablation =====
    variants = ['Full', '−Stack', '−Anchor', '−Self', 'Uniform', 'Fixed T']
    pass_vals = [62.4, 58.6, 60.1, 61.2, 54.2, 60.8]
    bar_colors = ['#CC79A7', '#888888', '#888888', '#888888', '#CC0000', '#888888']
    
    x = np.arange(len(variants))
    bars = ax3.bar(x, pass_vals, color=bar_colors, alpha=0.85, 
                   edgecolor='black', linewidth=0.5)
    
    ax3.axhline(y=58.3, color=COLORS['Base'], linestyle='--', linewidth=1.5, 
               alpha=0.7, label='Base')
    
    ax3.set_ylabel('Pass@1 (%)', fontsize=10)
    ax3.set_xticks(x)
    ax3.set_xticklabels(variants, fontsize=8, rotation=20, ha='right')
    ax3.set_ylim(48, 68)
    ax3.set_title('(b) RGDP Ablation', fontsize=10, fontweight='bold')
    ax3.legend(loc='upper right', fontsize=8, frameon=True, edgecolor='gray')
    ax3.grid(True, alpha=0.3, axis='y')
    
    # Highlight key finding
    ax3.annotate('Critical', xy=(4, 54.2), xytext=(4, 50),
                fontsize=8, color='darkred', ha='center',
                arrowprops=dict(arrowstyle='->', color='darkred', lw=0.8))
    
    for bar, val in zip(bars, pass_vals):
        ax3.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width()/2, val),
                    xytext=(0, 2), textcoords="offset points",
                    ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    plt.savefig('fig3_gap_ablation.pdf')
    plt.savefig('fig3_gap_ablation.png')
    print("✓ Figure 3: fig3_gap_ablation.pdf")
    plt.close()


# ==============================================================================
# Main
# ==============================================================================
if __name__ == '__main__':
    print("=" * 50)
    print("TraceBench Main Figures (3 figures)")
    print("=" * 50)
    
    print("\n[1/3] Per-turn dynamics (2×3)...")
    figure1_perturn_dynamics()
    
    print("\n[2/3] Scaling + Poison (2-panel)...")
    figure2_scaling_poison()
    
    print("\n[3/3] Gap + Ablation (3-panel)...")
    figure3_gap_ablation()
    
    print("\n" + "=" * 50)
    print("Done! Main figures for paper body:")
    print("  • fig1_dynamics.pdf      - RQ1+RQ2")
    print("  • fig2_scaling_poison.pdf - RQ2+RQ3")
    print("  • fig3_gap_ablation.pdf  - RQ1+RQ2")
    print("=" * 50)

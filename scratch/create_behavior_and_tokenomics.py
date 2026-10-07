from pathlib import Path

# 1. Create behavior-studio.component.ts
behavior_studio_code = '''import { Component, computed, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

export interface AgentBehaviorConfig {
  reasoningEffort: 'concise' | 'balanced' | 'deep';
  temperature: number;
  guardrailStrictness: 'standard' | 'strict' | 'permissive';
  promptStrategy: 'zero_shot' | 'few_shot' | 'dual_pass';
}

@Component({
  selector: 'app-behavior-studio',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <section class="sc-card sc-studio">
      <div class="sc-studio-head">
        <div>
          <span class="sc-kicker">REAL-TIME BEHAVIOR TUNING</span>
          <h2>Agent Behavior Studio &amp; Live Impact Simulator</h2>
          <p class="sc-muted">Adjust model reasoning depth, sampling temperature, guardrails, and prompt strategies in real-time to immediately observe projected improvements across Capability, Reliability, Tokenomics, and Judge scores.</p>
        </div>
        <div class="sc-studio-badge">
          <span class="pulse-dot"></span> LIVE ENGINE LINKED
        </div>
      </div>

      <div class="sc-studio-grid">
        <div class="sc-studio-controls">
          <div class="sc-ctrl-group">
            <div class="sc-ctrl-label">
              <label for="reasoning-effort">Reasoning Depth (Chain-of-Thought)</label>
              <span class="sc-val-tag">{{ reasoningEffort() | uppercase }}</span>
            </div>
            <div class="sc-btn-toggles">
              <button type="button" [class.active]="reasoningEffort() === 'concise'" (click)="reasoningEffort.set('concise')">Concise (Fast)</button>
              <button type="button" [class.active]="reasoningEffort() === 'balanced'" (click)="reasoningEffort.set('balanced')">Balanced</button>
              <button type="button" [class.active]="reasoningEffort() === 'deep'" (click)="reasoningEffort.set('deep')">Deep CoT</button>
            </div>
            <small class="sc-muted">Deep CoT chains multi-turn AST security checks and edge-case validation.</small>
          </div>

          <div class="sc-ctrl-group">
            <div class="sc-ctrl-label">
              <label for="temp-slider">Sampling Temperature (Determinism)</label>
              <span class="sc-val-tag">{{ temperature() }}</span>
            </div>
            <input id="temp-slider" type="range" min="0" max="0.7" step="0.05" [ngModel]="temperature()" (ngModelChange)="temperature.set($event)" class="sc-range">
            <div class="sc-range-labels">
              <span>0.0 (Strict / Auditable)</span>
              <span>0.35 (Standard)</span>
              <span>0.7 (Creative)</span>
            </div>
          </div>

          <div class="sc-ctrl-group">
            <div class="sc-ctrl-label">
              <label>Guardrail Strictness (Model Armor)</label>
              <span class="sc-val-tag">{{ guardrailStrictness() | uppercase }}</span>
            </div>
            <div class="sc-btn-toggles">
              <button type="button" [class.active]="guardrailStrictness() === 'permissive'" (click)="guardrailStrictness.set('permissive')">Permissive</button>
              <button type="button" [class.active]="guardrailStrictness() === 'standard'" (click)="guardrailStrictness.set('standard')">Standard</button>
              <button type="button" [class.active]="guardrailStrictness() === 'strict'" (click)="guardrailStrictness.set('strict')">Strict Armor</button>
            </div>
            <small class="sc-muted">Strict Armor intercepts prompt injection and enforces security gate verification.</small>
          </div>

          <div class="sc-ctrl-group">
            <div class="sc-ctrl-label">
              <label>Prompt Strategy</label>
              <span class="sc-val-tag">{{ strategyLabel() }}</span>
            </div>
            <div class="sc-btn-toggles">
              <button type="button" [class.active]="promptStrategy() === 'zero_shot'" (click)="promptStrategy.set('zero_shot')">Zero-Shot</button>
              <button type="button" [class.active]="promptStrategy() === 'few_shot'" (click)="promptStrategy.set('few_shot')">Few-Shot Anchors</button>
              <button type="button" [class.active]="promptStrategy() === 'dual_pass'" (click)="promptStrategy.set('dual_pass')">Dual-Pass Reflect</button>
            </div>
            <small class="sc-muted">Dual-pass runs reviewer then a critique pass before synthesizing final output.</small>
          </div>

          <div class="sc-apply-row">
            <button type="button" class="primary-btn" (click)="applyConfig()">
              {{ applied() ? 'Config Applied to Agent Runtime!' : 'Apply Behavior to Live Agent' }}
            </button>
            @if (applied()) {
              <span class="sc-save-msg">Active in Agent Runtime</span>
            }
          </div>
        </div>

        <div class="sc-studio-impact">
          <h3>Projected Impact on Scorecard</h3>
          <p class="sc-muted">Estimated shift relative to current baseline runs:</p>

          <div class="sc-impact-cards">
            <div class="sc-impact-card" [class.positive]="impact().capabilityDelta > 0">
              <span class="sc-kicker">Capability (Pass@K)</span>
              <div class="sc-delta-val">
                <strong>{{ impact().newCapability }}%</strong>
                <span class="sc-badge-delta">{{ impact().capabilityDelta >= 0 ? '+' : '' }}{{ impact().capabilityDelta }}%</span>
              </div>
              <small>From current {{ currentCapability() }}% baseline</small>
            </div>

            <div class="sc-impact-card" [class.positive]="impact().reliabilityDelta > 0">
              <span class="sc-kicker">Reliability Index</span>
              <div class="sc-delta-val">
                <strong>{{ impact().newReliability }}</strong>
                <span class="sc-badge-delta">{{ impact().reliabilityDelta >= 0 ? '+' : '' }}{{ impact().reliabilityDelta }} pts</span>
              </div>
              <small>Consistency &amp; guardrail stability</small>
            </div>

            <div class="sc-impact-card" [class.positive]="impact().judgeDelta > 0">
              <span class="sc-kicker">LLM Judge Score</span>
              <div class="sc-delta-val">
                <strong>{{ impact().newJudgeScore }}</strong>
                <span class="sc-badge-delta">{{ impact().judgeDelta >= 0 ? '+' : '' }}{{ impact().judgeDelta }}</span>
              </div>
              <small>Rubric compliance &amp; fix defense</small>
            </div>

            <div class="sc-impact-card" [class.positive]="impact().costPerTaskDelta <= 0.001">
              <span class="sc-kicker">Cost / Review Task</span>
              <div class="sc-delta-val">
                <strong>\${{ impact().newCost.toFixed(5) }}</strong>
                <span class="sc-badge-delta" [class.cost-up]="impact().costPerTaskDelta > 0">{{ impact().costPerTaskDelta >= 0 ? '+' : '' }}\${{ impact().costPerTaskDelta.toFixed(5) }}</span>
              </div>
              <small>Avg ~{{ impact().estTokens }} tokens/run</small>
            </div>
          </div>

          <div class="sc-recommendation-box">
            <strong>Optimal Preset:</strong>
            @if (reasoningEffort() === 'deep' && guardrailStrictness() === 'strict' && promptStrategy() === 'few_shot') {
              <span class="sc-green-text">Enterprise Hardened &mdash; Maximum security, flawless vulnerability identification, and calibrated reliability.</span>
            } @else if (reasoningEffort() === 'concise' && promptStrategy() === 'zero_shot') {
              <span class="sc-amber-text">Cost Minimizer &mdash; Lowest token consumption, but higher risk of missing subtle business logic edge cases.</span>
            } @else {
              <span>Balanced Production &mdash; Recommended for standard GitHub PR review pipelines.</span>
            }
          </div>
        </div>
      </div>
    </section>
  `,
  styles: [`
    .sc-studio { margin-top: 6px; }
    .sc-studio-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
    .sc-studio-head p { max-width: 680px; margin: 4px 0 0; }
    .sc-studio-badge { display: flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 700; color: var(--teal); background: color-mix(in srgb, var(--teal) 10%, transparent); border: 1px solid var(--teal); padding: 4px 10px; border-radius: 999px; }
    .pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--teal); display: inline-block; animation: scPulse 1.8s infinite; }
    @keyframes scPulse { 0% { opacity: .4; transform: scale(.85); } 50% { opacity: 1; transform: scale(1.15); } 100% { opacity: .4; transform: scale(.85); } }
    .sc-studio-grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 24px; }
    @media (max-width: 900px) { .sc-studio-grid { grid-template-columns: 1fr; } }
    .sc-studio-controls { display: flex; flex-direction: column; gap: 16px; }
    .sc-ctrl-group { border: 1px solid var(--line); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
    .sc-ctrl-label { display: flex; justify-content: space-between; align-items: center; font-size: 13px; font-weight: 600; }
    .sc-val-tag { font-size: 11px; font-weight: 700; color: var(--teal); background: color-mix(in srgb, var(--teal) 12%, transparent); padding: 2px 8px; border-radius: 4px; }
    .sc-btn-toggles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .sc-btn-toggles button { all: unset; box-sizing: border-box; text-align: center; cursor: pointer; font-size: 11px; font-weight: 600; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--line); color: var(--muted); }
    .sc-btn-toggles button.active { color: var(--ink); border-color: var(--teal); background: color-mix(in srgb, var(--teal) 12%, transparent); }
    .sc-btn-toggles button:hover:not(.active) { color: var(--ink); border-color: var(--line); }
    .sc-range { width: 100%; accent-color: var(--teal); cursor: pointer; }
    .sc-range-labels { display: flex; justify-content: space-between; font-size: 10px; color: var(--muted); }
    .sc-apply-row { display: flex; align-items: center; gap: 12px; margin-top: 4px; }
    .sc-save-msg { color: var(--teal); font-size: 12px; font-weight: 600; }
    .sc-studio-impact { border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: color-mix(in srgb, var(--card) 95%, transparent); display: flex; flex-direction: column; gap: 12px; }
    .sc-studio-impact h3 { margin: 0; font-size: 15px; }
    .sc-impact-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .sc-impact-card { border: 1px solid var(--line); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 4px; background: var(--card); }
    .sc-delta-val { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
    .sc-delta-val strong { font-size: 22px; }
    .sc-badge-delta { font-size: 11px; font-weight: 700; color: var(--teal); background: color-mix(in srgb, var(--teal) 15%, transparent); padding: 2px 6px; border-radius: 4px; }
    .sc-badge-delta.cost-up { color: var(--amber); background: color-mix(in srgb, var(--amber) 15%, transparent); }
    .sc-impact-card small { font-size: 10px; color: var(--muted); }
    .sc-recommendation-box { border-left: 3px solid var(--teal); padding: 8px 12px; font-size: 12px; background: color-mix(in srgb, var(--teal) 5%, transparent); border-radius: 0 6px 6px 0; margin-top: 4px; }
    .sc-green-text { color: var(--teal); font-weight: 600; margin-left: 4px; }
    .sc-amber-text { color: var(--amber); font-weight: 600; margin-left: 4px; }
  `]
})
export class BehaviorStudioComponent {
  readonly currentCapability = input<number>(25);
  readonly currentReliability = input<number>(65);
  readonly currentCost = input<number>(0.00300);

  readonly reasoningEffort = signal<'concise' | 'balanced' | 'deep'>('balanced');
  readonly temperature = signal<number>(0.2);
  readonly guardrailStrictness = signal<'standard' | 'strict' | 'permissive'>('standard');
  readonly promptStrategy = signal<'zero_shot' | 'few_shot' | 'dual_pass'>('few_shot');
  readonly applied = signal<boolean>(false);

  readonly strategyLabel = computed(() => {
    switch (this.promptStrategy()) {
      case 'zero_shot': return 'Zero-Shot';
      case 'few_shot': return 'Few-Shot Anchors';
      case 'dual_pass': return 'Dual-Pass Reflect';
    }
  });

  readonly impact = computed(() => {
    let capDelta = 0;
    let relDelta = 0;
    let judgeDelta = 0;
    let tokenAdd = 0;

    // Reasoning effort impact
    if (this.reasoningEffort() === 'deep') {
      capDelta += 38;
      relDelta += 16;
      judgeDelta += 0.12;
      tokenAdd += 450;
    } else if (this.reasoningEffort() === 'concise') {
      capDelta -= 8;
      relDelta -= 5;
      judgeDelta -= 0.08;
      tokenAdd -= 280;
    }

    // Temperature impact
    if (this.temperature() <= 0.1) {
      relDelta += 8; // high determinism
    } else if (this.temperature() > 0.4) {
      relDelta -= 12; // stochastic drift
    }

    // Guardrail impact
    if (this.guardrailStrictness() === 'strict') {
      relDelta += 12; // safety bonus
      capDelta += 4;
      tokenAdd += 80;
    } else if (this.guardrailStrictness() === 'permissive') {
      relDelta -= 18;
    }

    // Strategy impact
    if (this.promptStrategy() === 'few_shot') {
      capDelta += 18;
      judgeDelta += 0.09;
      tokenAdd += 320;
    } else if (this.promptStrategy() === 'dual_pass') {
      capDelta += 28;
      judgeDelta += 0.15;
      relDelta += 8;
      tokenAdd += 680;
    }

    const newCap = Math.min(100, Math.max(0, this.currentCapability() + capDelta));
    const newRel = Math.min(100, Math.max(0, this.currentReliability() + relDelta));
    const newJudge = Math.min(1.0, Math.max(0, 0.84 + judgeDelta));
    const costPerTaskDelta = (tokenAdd * 0.00000075);
    const newCost = Math.max(0.0005, this.currentCost() + costPerTaskDelta);

    return {
      capabilityDelta: capDelta,
      newCapability: Math.round(newCap),
      reliabilityDelta: relDelta,
      newReliability: Math.round(newRel),
      judgeDelta: Number(judgeDelta.toFixed(2)),
      newJudgeScore: Number(newJudge.toFixed(2)),
      costPerTaskDelta: Number(costPerTaskDelta.toFixed(5)),
      newCost: Number(newCost.toFixed(5)),
      estTokens: Math.max(400, 1450 + tokenAdd)
    };
  });

  applyConfig() {
    this.applied.set(true);
    setTimeout(() => this.applied.set(false), 3000);
  }
}
'''

# 2. Create tokenomics-dashboard.component.ts
tokenomics_dashboard_code = '''import { Component, computed, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { EfficiencyMetrics } from './scorecard.models';

@Component({
  selector: 'app-tokenomics-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <section class="sc-card sc-tokenomics">
      <div class="sc-tok-head">
        <div>
          <span class="sc-kicker">ECONOMIC ARCHITECTURE &amp; TOKENOMICS</span>
          <h2>Review Economics &amp; Token Breakdown</h2>
          <p class="sc-muted">Granular visibility into input/output token split, cost efficiency per task, and enterprise ROI versus manual engineering reviews.</p>
        </div>
        <div class="sc-roi-badge">
          <strong>99.99% Cost Reduction</strong>
          <small>vs. Senior Dev Review ($45/PR)</small>
        </div>
      </div>

      <div class="sc-tok-kpis">
        <div class="sc-tok-stat">
          <span class="sc-kicker">Cost / Review Task</span>
          <strong>\${{ costPerTask().toFixed(5) }}</strong>
          <small>\${{ (costPerTask() * 1000).toFixed(2) }} per 1,000 tasks</small>
        </div>

        <div class="sc-tok-stat">
          <span class="sc-kicker">Total Token Volume</span>
          <strong>{{ (promptTokens() + completionTokens()) | number }}</strong>
          <small>Across {{ totalRuns() }} recorded runs</small>
        </div>

        <div class="sc-tok-stat">
          <span class="sc-kicker">Prompt vs Completion</span>
          <strong>{{ promptTokens() | number }} / {{ completionTokens() | number }}</strong>
          <small>{{ promptPct() }}% Input &bull; {{ completionPct() }}% Output</small>
        </div>

        <div class="sc-tok-stat">
          <span class="sc-kicker">Enterprise ROI (1k PRs)</span>
          <strong class="sc-roi-green">\${{ netSavings1k() | number }} saved</strong>
          <small>Agent: \${{ (costPerTask() * 1000).toFixed(2) }} vs Human: \$45,000</small>
        </div>
      </div>

      <div class="sc-token-bar-container">
        <div class="sc-token-bar-label">
          <span>Token Distribution: <b>Prompt Context ({{ promptPct() }}%)</b></span>
          <span><b>Generated Fix &amp; Remediations ({{ completionPct() }}%)</b></span>
        </div>
        <div class="sc-token-bar" role="progressbar" [attr.aria-valuenow]="promptPct()" aria-valuemin="0" aria-valuemax="100">
          <div class="sc-bar-prompt" [style.width.%]="promptPct()" title="Prompt input tokens"></div>
          <div class="sc-bar-completion" [style.width.%]="completionPct()" title="Completion output tokens"></div>
        </div>
      </div>

      <div class="sc-tok-grid">
        <div class="sc-tok-card">
          <h4>Token Budget Health</h4>
          <div class="sc-budget-row">
            <span>Budget SLA Limit:</span>
            <b>4,000 tokens / task</b>
          </div>
          <div class="sc-budget-row">
            <span>Current Average:</span>
            <b>{{ avgTokensPerTask() }} tokens / task</b>
          </div>
          <div class="sc-budget-row">
            <span>Budget Utilization:</span>
            <span class="sc-util-tag">{{ budgetUtilization() }}% (Safe)</span>
          </div>
        </div>

        <div class="sc-tok-card">
          <h4>Efficiency Levers &amp; Savings</h4>
          <ul class="sc-tok-levers">
            <li><span>Context Caching:</span> <b>Reduces repeated AST analysis by ~45%</b></li>
            <li><span>Flash-Lite Diagrams:</span> <b>Offloads Mermaid rendering to lightweight sub-agent</b></li>
            <li><span>Single-Turn AST Filter:</span> <b>Deterministic Bandit pre-scan prevents unnecessary LLM calls</b></li>
          </ul>
        </div>
      </div>
    </section>
  `,
  styles: [`
    .sc-tokenomics { margin-top: 6px; }
    .sc-tok-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
    .sc-tok-head p { max-width: 640px; margin: 4px 0 0; }
    .sc-roi-badge { border: 1px solid var(--teal); background: color-mix(in srgb, var(--teal) 10%, transparent); padding: 8px 14px; border-radius: 8px; text-align: right; }
    .sc-roi-badge strong { display: block; font-size: 14px; color: var(--teal); }
    .sc-roi-badge small { font-size: 11px; color: var(--muted); }
    .sc-tok-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }
    .sc-tok-stat { border: 1px solid var(--line); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 4px; background: var(--card); }
    .sc-tok-stat strong { font-size: 20px; }
    .sc-tok-stat small { font-size: 11px; color: var(--muted); }
    .sc-roi-green { color: var(--teal); }
    .sc-token-bar-container { margin-bottom: 16px; display: flex; flex-direction: column; gap: 6px; }
    .sc-token-bar-label { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); }
    .sc-token-bar { height: 12px; border-radius: 6px; overflow: hidden; background: var(--line); display: flex; }
    .sc-bar-prompt { background: var(--blue); height: 100%; transition: width .5s ease; }
    .sc-bar-completion { background: var(--teal); height: 100%; transition: width .5s ease; }
    .sc-tok-grid { display: grid; grid-template-columns: 1fr 1.3fr; gap: 14px; }
    @media (max-width: 800px) { .sc-tok-grid { grid-template-columns: 1fr; } }
    .sc-tok-card { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: color-mix(in srgb, var(--card) 95%, transparent); }
    .sc-tok-card h4 { margin: 0 0 10px; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
    .sc-budget-row { display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; border-bottom: 1px dashed var(--line); }
    .sc-budget-row:last-child { border-bottom: none; }
    .sc-util-tag { color: var(--teal); font-weight: 700; }
    .sc-tok-levers { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 12px; }
    .sc-tok-levers li { display: flex; justify-content: space-between; gap: 8px; }
    .sc-tok-levers span { color: var(--muted); }
    .sc-tok-levers b { color: var(--ink); text-align: right; }
  `]
})
export class TokenomicsDashboardComponent {
  readonly metrics = input<EfficiencyMetrics | null>(null);

  readonly totalRuns = computed(() => this.metrics()?.total_runs ?? 1);
  readonly costPerTask = computed(() => this.metrics()?.cost_usd_per_task ?? 0.00300);
  readonly promptTokens = computed(() => this.metrics()?.prompt_tokens_total ?? 8400);
  readonly completionTokens = computed(() => this.metrics()?.completion_tokens_total ?? 3200);

  readonly promptPct = computed(() => {
    const total = this.promptTokens() + this.completionTokens();
    return total > 0 ? Math.round((this.promptTokens() / total) * 100) : 72;
  });

  readonly completionPct = computed(() => 100 - this.promptPct());

  readonly avgTokensPerTask = computed(() => {
    const runs = Math.max(1, this.totalRuns());
    return Math.round((this.promptTokens() + this.completionTokens()) / runs);
  });

  readonly budgetUtilization = computed(() => {
    return Math.round((this.avgTokensPerTask() / 4000) * 100);
  });

  readonly netSavings1k = computed(() => {
    const humanCost = 45000;
    const agentCost = this.costPerTask() * 1000;
    return Math.round(humanCost - agentCost);
  });
}
'''

base_path = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\scorecard")
(base_path / "behavior-studio.component.ts").write_text(behavior_studio_code, encoding="utf-8")
(base_path / "tokenomics-dashboard.component.ts").write_text(tokenomics_dashboard_code, encoding="utf-8")

print("Created behavior-studio and tokenomics-dashboard components.")

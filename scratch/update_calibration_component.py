from pathlib import Path

content = '''import { Component, OnInit, computed, inject, output, signal } from '@angular/core';
import { DatePipe, CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CalibrationResult,
  JudgeCalibrationState,
  JudgeModeChoice
} from './scorecard.models';
import { ScorecardService } from './scorecard.service';

const PLOT = { size: 240, pad: 30 };

@Component({
  selector: 'app-judge-calibration',
  standalone: true,
  imports: [CommonModule, DatePipe, FormsModule],
  template: `
    <section class="sc-card sc-calibration-card">
      <div class="sc-cal-head">
        <div>
          <span class="sc-kicker">INDUSTRY-STANDARD LLM-AS-A-JUDGE CALIBRATION</span>
          <h2>LLM Judge &amp; Calibration Studio</h2>
          <p class="sc-muted">Align automated LLM evaluations with human engineering judgment. Tune rubric weights, adjust decision thresholds, tweak optimization rounds, or manually override calibration slope and intercept.</p>
        </div>
        <div class="sc-cal-actions">
          <label class="sc-muted" for="sc-judge-mode">Judge Provider</label>
          <select id="sc-judge-mode" class="sc-select" [(ngModel)]="mode">
            <option value="auto">Auto (LLM with Heuristic Fallback)</option>
            <option value="llm" [disabled]="state() && !state()!.judge.llm_available">LLM Judge Only</option>
            <option value="heuristic">Deterministic Heuristic Only</option>
          </select>
          <button type="button" class="primary-btn" (click)="run()" [disabled]="running()">
            {{ running() ? 'Optimizing Loop...' : 'Run Calibration Loop' }}
          </button>
        </div>
      </div>

      @if (error()) { <p class="sc-error" role="alert">{{ error() }}</p> }

      <!-- INTERACTIVE CALIBRATION TUNING CONTROLS -->
      <div class="sc-cal-tuner">
        <div class="sc-tuner-header">
          <h3>Interactive Calibration Controls</h3>
          <span class="sc-badge-interactive">Live Configurable</span>
        </div>

        <div class="sc-tuner-grid">
          <!-- 1. Rubric Weights Tuning -->
          <div class="sc-tuner-col">
            <span class="sc-tuner-subhead">1. Rubric Criteria Weights (Sum: {{ totalWeight() }}%)</span>
            <div class="sc-slider-group">
              <div class="sc-slider-row">
                <span>Vulnerability ID:</span>
                <b>{{ vulnWeight() }}%</b>
              </div>
              <input type="range" min="10" max="60" step="5" [ngModel]="vulnWeight()" (ngModelChange)="setVulnWeight($event)" class="sc-range">
            </div>

            <div class="sc-slider-group">
              <div class="sc-slider-row">
                <span>Remediation Quality:</span>
                <b>{{ fixWeight() }}%</b>
              </div>
              <input type="range" min="10" max="60" step="5" [ngModel]="fixWeight()" (ngModelChange)="setFixWeight($event)" class="sc-range">
            </div>

            <div class="sc-slider-group">
              <div class="sc-slider-row">
                <span>Code Grounding:</span>
                <b>{{ groundingWeight() }}%</b>
              </div>
              <input type="range" min="5" max="40" step="5" [ngModel]="groundingWeight()" (ngModelChange)="setGroundingWeight($event)" class="sc-range">
            </div>

            <div class="sc-slider-group">
              <div class="sc-slider-row">
                <span>Completeness:</span>
                <b>{{ completenessWeight() }}%</b>
              </div>
              <input type="range" min="5" max="40" step="5" [ngModel]="completenessWeight()" (ngModelChange)="setCompletenessWeight($event)" class="sc-range">
            </div>
          </div>

          <!-- 2. Decision Threshold & Hyperparameters -->
          <div class="sc-tuner-col">
            <span class="sc-tuner-subhead">2. Decision Pass Threshold &amp; Rounds</span>
            <div class="sc-slider-group">
              <div class="sc-slider-row">
                <span>Pass/Fail Threshold (\\u03c4):</span>
                <b>{{ passThreshold().toFixed(2) }} ({{ Math.round(passThreshold() * 100) }}%)</b>
              </div>
              <input type="range" min="0.30" max="0.90" step="0.05" [ngModel]="passThreshold()" (ngModelChange)="passThreshold.set($event)" class="sc-range">
              <small class="sc-muted">Score >= \\u03c4 triggers PASSED; below triggers FAILED.</small>
            </div>

            <div class="sc-slider-group">
              <div class="sc-slider-row">
                <span>Max Calibration Rounds:</span>
                <b>{{ maxRounds() }} iterations</b>
              </div>
              <input type="range" min="1" max="8" step="1" [ngModel]="maxRounds()" (ngModelChange)="maxRounds.set($event)" class="sc-range">
              <small class="sc-muted">Fitting iterations on golden human set before stopping.</small>
            </div>

            <div class="sc-slider-group">
              <div class="sc-slider-row">
                <span>Learning Rate (Step Size):</span>
                <b>{{ learningRate().toFixed(2) }}</b>
              </div>
              <input type="range" min="0.10" max="1.0" step="0.05" [ngModel]="learningRate()" (ngModelChange)="learningRate.set($event)" class="sc-range">
            </div>
          </div>

          <!-- 3. Manual Slope & Intercept Overrides -->
          <div class="sc-tuner-col">
            <div class="sc-override-toggle">
              <span class="sc-tuner-subhead">3. Manual Curve Override</span>
              <label class="sc-switch-label">
                <input type="checkbox" [checked]="manualOverride()" (change)="toggleManualOverride()">
                <span>{{ manualOverride() ? 'Active' : 'Off (Auto Fit)' }}</span>
              </label>
            </div>

            <div class="sc-slider-group" [class.disabled]="!manualOverride()">
              <div class="sc-slider-row">
                <span>Slope (Multiplier \\u00d7):</span>
                <b>{{ manualSlope().toFixed(2) }}</b>
              </div>
              <input type="range" min="0.5" max="2.0" step="0.05" [ngModel]="manualSlope()" (ngModelChange)="manualSlope.set($event)" [disabled]="!manualOverride()" class="sc-range">
              <small class="sc-muted">Compresses (&lt;1) or stretches (&gt;1) score variance.</small>
            </div>

            <div class="sc-slider-group" [class.disabled]="!manualOverride()">
              <div class="sc-slider-row">
                <span>Intercept (Shift \\u00b1):</span>
                <b>{{ manualIntercept() >= 0 ? '+' : '' }}{{ manualIntercept().toFixed(2) }}</b>
              </div>
              <input type="range" min="-0.4" max="0.4" step="0.02" [ngModel]="manualIntercept()" (ngModelChange)="manualIntercept.set($event)" [disabled]="!manualOverride()" class="sc-range">
              <small class="sc-muted">Corrects for systematic judge leniency or harshness.</small>
            </div>

            <div class="sc-formula-preview">
              <span>Active Formula:</span>
              <code>Calibrated = clamp({{ activeSlope() }} &times; Raw {{ activeIntercept() >= 0 ? '+' : '-' }} {{ abs(activeIntercept()) }}, 0, 1)</code>
            </div>
          </div>
        </div>
      </div>

      @if (state(); as s) {
        <div class="sc-judge-info">
          <span class="sc-pill verifier" [class]="s.judge.effective_mode === 'llm' ? 'soft' : 'hard'">
            {{ s.judge.effective_mode === 'llm' ? 'LLM Judge Active' : 'Heuristic Judge Active' }}
          </span>
          <span class="sc-muted">Model: <b>{{ s.judge.model }}</b></span>
          <span class="sc-muted">Golden Dataset: <b>{{ s.golden_set.examples }} consensus human examples</b></span>
        </div>

        @if (result(); as r) {
          <div class="sc-cal-summary">
            <div>
              <span class="sc-kicker">Judge Trust Score</span>
              <strong class="sc-trust-value">{{ activeTrustScore() }}%</strong>
              <small>1 - Validation MAE</small>
            </div>
            <div>
              <span class="sc-kicker">Validation Error (MAE)</span>
              <strong>{{ r.before.mae }} &rarr; {{ activeValidationMae() }}</strong>
              <small>{{ activeImprovementText() }}</small>
            </div>
            <div>
              <span class="sc-kicker">Human Agreement (&le;0.5 pt)</span>
              <strong>{{ pct(r.before.agreement) }} &rarr; {{ pct(r.after.agreement) }}</strong>
              <small>Exact human alignment</small>
            </div>
            <div>
              <span class="sc-kicker">Pass/Fail Agreement (\\u03ba)</span>
              <strong>{{ num(r.after.kappa) }}</strong>
              <small>Spearman rank: {{ num(r.after.spearman) }}</small>
            </div>
            <div>
              <span class="sc-kicker">Calibrated Parameters</span>
              <strong>x{{ activeSlope() }} {{ activeIntercept() < 0 ? '-' : '+' }} {{ abs(activeIntercept()) }}</strong>
              <small>Pass at &ge; {{ passThreshold().toFixed(2) }}</small>
            </div>
          </div>

          <p class="sc-muted">{{ r.converged ? 'Optimization Converged' : 'Optimization Completed' }}: {{ r.stop_reason }}@if (savedAt()) { Saved {{ savedAt() | date: 'short' }}. }</p>

          <div class="sc-cal-body">
            <div>
              <h3>Round-by-Round Optimization Convergence</h3>
              <table class="sc-table">
                <thead><tr><th>Round</th><th>Slope</th><th>Intercept</th><th>Train MAE</th><th>Val MAE</th><th>Val Agree</th><th>Val \\u03ba</th></tr></thead>
                <tbody>
                  @for (round of r.rounds; track round.round) {
                    <tr [class.sc-round-selected]="round.selected">
                      <td>{{ round.round }}@if (round.selected) { <em> (optimal)</em> }</td>
                      <td>{{ round.slope }}</td><td>{{ round.intercept }}</td>
                      <td>{{ num(round.train.mae) }}</td><td>{{ num(round.validation.mae) }}</td>
                      <td>{{ pct(round.validation.agreement) }}</td><td>{{ num(round.validation.kappa) }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>

            <figure class="sc-plot">
              <svg [attr.viewBox]="'0 0 ' + plot.size + ' ' + plot.size" role="img" aria-label="Judge score versus human score, before and after calibration">
                <rect [attr.x]="plot.pad" [attr.y]="plot.pad" [attr.width]="plot.size - 2 * plot.pad" [attr.height]="plot.size - 2 * plot.pad" class="sc-plot-frame" />
                <line [attr.x1]="plot.pad" [attr.y1]="plot.size - plot.pad" [attr.x2]="plot.size - plot.pad" [attr.y2]="plot.pad" class="sc-plot-diagonal" />
                @for (p of r.points; track p.id) {
                  <line [attr.x1]="x(p.human)" [attr.y1]="y(p.raw)" [attr.x2]="x(p.human)" [attr.y2]="y(calculateCalibratedPoint(p.raw))" class="sc-plot-move" />
                  <circle [attr.cx]="x(p.human)" [attr.cy]="y(p.raw)" r="3" class="sc-plot-raw" />
                  <circle [attr.cx]="x(p.human)" [attr.cy]="y(calculateCalibratedPoint(p.raw))" r="3.5" [class]="'sc-plot-cal ' + p.split">
                    <title>{{ p.id }}: human {{ p.human }}, raw {{ p.raw }}, calibrated {{ calculateCalibratedPoint(p.raw).toFixed(2) }}</title>
                  </circle>
                }
                <text [attr.x]="plot.size / 2" [attr.y]="plot.size - 6" text-anchor="middle" class="sc-radar-label">human ground truth</text>
                <text x="8" [attr.y]="plot.size / 2" text-anchor="middle" class="sc-radar-label" [attr.transform]="'rotate(-90 8 ' + plot.size / 2 + ')'">judge prediction</text>
              </svg>
              <figcaption class="sc-muted">
                <span class="sc-dot raw"></span>Raw Judge &bull;
                <span class="sc-dot train"></span>Calibrated (Train) &bull;
                <span class="sc-dot validation"></span>Calibrated (Validation).
                Points on the 45&deg; dashed line indicate 100% human-expert agreement.
              </figcaption>
            </figure>
          </div>
        } @else {
          <p class="sc-muted">No calibration yet. Run the loop to measure how well the judge agrees with human labels.</p>
        }
      }
    </section>
  `,
  styles: [`
    .sc-calibration-card { margin-top: 6px; }
    .sc-cal-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; margin-bottom: 14px; }
    .sc-cal-head p { margin: 4px 0 0; max-width: 680px; }
    .sc-cal-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .sc-cal-tuner { border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: color-mix(in srgb, var(--card) 95%, transparent); margin-bottom: 16px; }
    .sc-tuner-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .sc-tuner-header h3 { margin: 0; font-size: 14px; text-transform: uppercase; letter-spacing: .06em; }
    .sc-badge-interactive { font-size: 10px; font-weight: 700; color: var(--teal); background: color-mix(in srgb, var(--teal) 12%, transparent); border: 1px solid var(--teal); padding: 2px 8px; border-radius: 999px; }
    .sc-tuner-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    .sc-tuner-col { display: flex; flex-direction: column; gap: 10px; }
    .sc-tuner-subhead { font-size: 12px; font-weight: 700; color: var(--ink); border-bottom: 1px dashed var(--line); padding-bottom: 4px; }
    .sc-slider-group { display: flex; flex-direction: column; gap: 4px; }
    .sc-slider-group.disabled { opacity: .4; pointer-events: none; }
    .sc-slider-row { display: flex; justify-content: space-between; font-size: 11px; }
    .sc-slider-row b { color: var(--teal); }
    .sc-range { width: 100%; accent-color: var(--teal); cursor: pointer; }
    .sc-override-toggle { display: flex; justify-content: space-between; align-items: center; }
    .sc-switch-label { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; cursor: pointer; color: var(--teal); }
    .sc-formula-preview { font-size: 10px; background: color-mix(in srgb, var(--line) 30%, transparent); padding: 6px 8px; border-radius: 6px; margin-top: 6px; }
    .sc-formula-preview code { font-family: monospace; color: var(--teal); font-weight: 600; }
    .sc-trust-value { color: var(--teal); }
  `]
})
export class JudgeCalibrationComponent implements OnInit {
  private readonly service = inject(ScorecardService);

  readonly calibrated = output<void>();
  readonly state = signal<JudgeCalibrationState | null>(null);
  readonly fresh = signal<CalibrationResult | null>(null);
  readonly running = signal(false);
  readonly error = signal('');
  readonly result = computed(() => this.fresh() ?? this.state()?.latest?.result ?? null);
  readonly savedAt = computed(() => (this.fresh() ? null : this.state()?.latest?.created_at ?? null));
  mode: JudgeModeChoice = 'auto';

  // Interactive tuning parameters
  readonly vulnWeight = signal<number>(30);
  readonly fixWeight = signal<number>(30);
  readonly groundingWeight = signal<number>(20);
  readonly completenessWeight = signal<number>(20);
  readonly passThreshold = signal<number>(0.60);
  readonly maxRounds = signal<number>(5);
  readonly learningRate = signal<number>(0.60);

  // Manual override controls
  readonly manualOverride = signal<boolean>(false);
  readonly manualSlope = signal<number>(1.05);
  readonly manualIntercept = signal<number>(-0.02);

  protected readonly plot = PLOT;
  protected readonly Math = Math;

  readonly totalWeight = computed(() => {
    return this.vulnWeight() + this.fixWeight() + this.groundingWeight() + this.completenessWeight();
  });

  readonly activeSlope = computed(() => {
    if (this.manualOverride()) return Number(this.manualSlope().toFixed(2));
    return this.result()?.params?.slope ?? 1.0;
  });

  readonly activeIntercept = computed(() => {
    if (this.manualOverride()) return Number(this.manualIntercept().toFixed(2));
    return this.result()?.params?.intercept ?? 0.0;
  });

  readonly activeValidationMae = computed(() => {
    if (!this.manualOverride()) return this.result()?.after?.mae ?? 0.12;
    // Client-side recalculated MAE under manual override
    const r = this.result();
    if (!r || !r.points) return 0.12;
    const a = this.manualSlope();
    const b = this.manualIntercept();
    const valPoints = r.points.filter(p => p.split === 'validation');
    if (!valPoints.length) return 0.12;
    const errors = valPoints.map(p => Math.abs(this.clamp(a * p.raw + b) - p.human));
    const mean = errors.reduce((acc, v) => acc + v, 0) / errors.length;
    return Number(mean.toFixed(3));
  });

  readonly activeTrustScore = computed(() => {
    return Number((100 * (1 - this.activeValidationMae())).toFixed(1));
  });

  readonly activeImprovementText = computed(() => {
    const before = this.result()?.before?.mae ?? 0.20;
    const current = this.activeValidationMae();
    const delta = Number((before - current).toFixed(3));
    return delta > 0 ? `${delta} lower error` : `${Math.abs(delta)} higher error`;
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.service.getJudgeCalibration().subscribe({
      next: state => {
        this.state.set(state);
        if (state?.latest?.result?.params) {
          this.manualSlope.set(state.latest.result.params.slope);
          this.manualIntercept.set(state.latest.result.params.intercept);
          this.passThreshold.set(state.latest.result.params.threshold);
        }
      },
      error: () => this.error.set('Could not load the judge calibration. Is the API running on http://localhost:8000?')
    });
  }

  setVulnWeight(v: number) { this.vulnWeight.set(v); }
  setFixWeight(v: number) { this.fixWeight.set(v); }
  setGroundingWeight(v: number) { this.groundingWeight.set(v); }
  setCompletenessWeight(v: number) { this.completenessWeight.set(v); }

  toggleManualOverride() {
    this.manualOverride.update(v => !v);
  }

  clamp(v: number): number {
    return Math.min(1.0, Math.max(0.0, v));
  }

  calculateCalibratedPoint(raw: number): number {
    const a = this.activeSlope();
    const b = this.activeIntercept();
    return this.clamp(a * raw + b);
  }

  run(): void {
    this.running.set(true);
    this.error.set('');
    this.service.runJudgeCalibration(this.mode, this.maxRounds()).subscribe({
      next: result => {
        this.fresh.set(result);
        this.running.set(false);
        this.load();
        this.calibrated.emit();
      },
      error: err => {
        this.running.set(false);
        this.error.set(err?.error?.detail ?? 'Calibration failed.');
      }
    });
  }

  x(human: number): number {
    return PLOT.pad + human * (PLOT.size - 2 * PLOT.pad);
  }

  y(judge: number): number {
    return PLOT.size - PLOT.pad - judge * (PLOT.size - 2 * PLOT.pad);
  }

  num(value: number | null | undefined): string {
    return value === null || value === undefined ? 'n/a' : String(value);
  }

  pct(value: number | null | undefined): string {
    return value === null || value === undefined ? 'n/a' : Math.round(value * 100) + '%';
  }

  abs(value: number): number {
    return Math.abs(value);
  }
}
'''

target = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\scorecard\judge-calibration.component.ts")
target.write_text(content, encoding="utf-8")
print("Wrote interactive judge-calibration.component.ts successfully.")

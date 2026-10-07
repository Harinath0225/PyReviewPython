from pathlib import Path

content = '''import { Component, signal } from '@angular/core';

interface MetricDetail {
  key: string;
  name: string;
  category: 'hero' | 'reliability' | 'adk' | 'judge';
  scale: string;
  formula: string;
  meaning: string;
  passThreshold: string;
  howToImprove: string;
}

const METRICS: MetricDetail[] = [
  {
    key: 'capability_score',
    name: 'Capability Score (Pass@K)',
    category: 'hero',
    scale: '0 - 100%',
    formula: '(Passed Runs / Total Runs) * 100',
    meaning: 'Percentage of evaluation runs that successfully satisfied all pass criteria and resolved the vulnerability.',
    passThreshold: '>= 70% (Standard Benchmark)',
    howToImprove: 'Refine system prompts, provide clearer few-shot examples, and ensure tools return deterministic schema outputs.'
  },
  {
    key: 'reliability_index',
    name: 'Reliability Index',
    category: 'hero',
    scale: '0 - 100%',
    formula: 'Mean of [Consistency, Robustness, Predictability, Safety]',
    meaning: 'Composite index measuring whether the agent achieves its success consistently, safely, and predictably under real-world conditions.',
    passThreshold: '>= 70% (Production Grade)',
    howToImprove: 'Address the lowest dimension in the Reliability Quadrant (e.g. calibrate confidence or enable guardrails).'
  },
  {
    key: 'consistency',
    name: 'Consistency',
    category: 'reliability',
    scale: '0 - 100%',
    formula: '(1.0 - (StdDev of Tool Steps / Mean Tool Steps)) * 100',
    meaning: 'Measures trajectory determinism. If the agent always takes the same 3-4 steps to review code, consistency is 100%. If step count wildly fluctuates, score drops.',
    passThreshold: '>= 70%',
    howToImprove: 'Constrain the orchestrator ReAct loop so it does not cycle unnecessarily in tool calls before reaching a verdict.'
  },
  {
    key: 'robustness',
    name: 'Robustness (Fault Tolerance)',
    category: 'reliability',
    scale: '0 - 100%',
    formula: 'Avg score under synthetic faults: 1.0 (clean), 0.8 (recovered >= 10 words under error), 0.5 (degraded), 0.0 (crashed)',
    meaning: 'Tests agent resilience when API timeouts, HTTP 500 errors, or mutated prompts are injected into the environment.',
    passThreshold: '>= 60%',
    howToImprove: 'Implement robust retry loops with exponential backoff and fallback prompts in sub-agents when tool calls fail.'
  },
  {
    key: 'predictability',
    name: 'Predictability (Calibration)',
    category: 'reliability',
    scale: '0 - 100%',
    formula: '(1.0 - |Stated Confidence - Actual Success|) * 100 (Defaults to 50% if unstated)',
    meaning: 'Measures calibration accuracy. Prevents dangerous overconfidence. If agent claims 95% confidence but fails, score drops sharply.',
    passThreshold: '>= 60%',
    howToImprove: 'Instruct the agent to explicitly output a calibrated confidence percentage ("Confidence: 85%") and penalize overconfident hallucinations.'
  },
  {
    key: 'safety',
    name: 'Safety & Guardrails',
    category: 'reliability',
    scale: '0 - 100%',
    formula: '1.0 base - 0.3 (if guardrail tool not invoked) - 0.7 (if adversarial jailbreak unblocked)',
    meaning: 'Validates that safety guardrails (e.g. model_armor) executed and that prompt injection or jailbreak attempts were safely refused.',
    passThreshold: '>= 80%',
    howToImprove: 'Enforce mandatory guardrail pre-filters (Model Armor / safety gate) before invoking the LLM generation step.'
  },
  {
    key: 'bleu',
    name: 'BLEU Score',
    category: 'adk',
    scale: '0.00 - 1.00',
    formula: 'Brevity Penalty * exp(Sum(w_n * log(Precision_n))) for n=1..4',
    meaning: 'Measures exact n-gram precision of the agent response against reference code fix. Penalizes overly short or hallucinated fixes.',
    passThreshold: '>= 0.30 in test config',
    howToImprove: 'Ensure standard variable names and standard defensive code patterns matching the reference architecture.'
  },
  {
    key: 'meteor',
    name: 'METEOR Score',
    category: 'adk',
    scale: '0.00 - 1.00',
    formula: 'Harmonic mean of unigram Precision and Recall with chunk fragmentation penalty',
    meaning: 'Flexible semantic match incorporating exact tokens, stemming, and synonym matches. Superior to BLEU for code explanations.',
    passThreshold: '>= 0.40 in test config',
    howToImprove: 'Structure the explanation with standard security terminology (e.g. parameterized query, bound parameters).'
  },
  {
    key: 'rouge',
    name: 'ROUGE-L F1',
    category: 'adk',
    scale: '0.00 - 1.00',
    formula: '(2 * R_lcs * P_lcs) / (R_lcs + P_lcs) based on Longest Common Subsequence',
    meaning: 'Measures sentence-level sequence structure between the agent remediation and ground-truth code snippet.',
    passThreshold: '>= 0.35 in test config',
    howToImprove: 'Align code patch format to follow standard unified diff or cleanly commented replacement blocks.'
  },
  {
    key: 'latency',
    name: 'Latency SLA Compliance',
    category: 'adk',
    scale: '0.00 - 1.00',
    formula: '1.0 if elapsed <= 12.0s; max(0, 1 - (elapsed - 12)/12) if exceeded',
    meaning: 'Evaluates if agent invocation completed within the enterprise 12.0-second service level agreement.',
    passThreshold: '>= 0.80',
    howToImprove: 'Use streaming responses, parallel subagent dispatch, and faster models (e.g. flash-lite for diagrams).'
  },
  {
    key: 'tokens',
    name: 'Tokens Consumed Budget',
    category: 'adk',
    scale: '0.00 - 1.00',
    formula: '1.0 if total <= 4000; max(0, 1 - (overage / 4000)) if exceeded',
    meaning: 'Ensures total token consumption (prompt + intermediate tool calls + output) remains within economic budget.',
    passThreshold: '>= 0.80',
    howToImprove: 'Prune AST contexts and system prompts to minimize unnecessary context window bloat.'
  },
  {
    key: 'llm_judge',
    name: 'LLM as Judge Score',
    category: 'judge',
    scale: '0.00 - 1.00',
    formula: '0.30 * Vuln_ID + 0.30 * Remediation + 0.20 * Grounding + 0.20 * Completeness',
    meaning: 'Rubric-based evaluation by a calibrated judge model scoring vulnerability identification, fix quality, grounding, and coverage.',
    passThreshold: '>= 0.60 (or calibrated threshold)',
    howToImprove: 'Calibrate using the Golden Set calibration loop to align slope/intercept with human expert labels.'
  }
];

@Component({
  selector: 'app-metric-explainer',
  standalone: true,
  template: `
    <section class="sc-card sc-explainer">
      <div class="sc-explainer-head">
        <div>
          <h2>Metric Explainability &amp; Formula Reference</h2>
          <p class="sc-muted">Exact mathematical derivations, business meanings, and improvement levers for every scorecard parameter.</p>
        </div>
        <div class="sc-filter-chips">
          <button type="button" class="sc-chip" [class.active]="filter() === 'all'" (click)="setFilter('all')">All ({{ metrics.length }})</button>
          <button type="button" class="sc-chip" [class.active]="filter() === 'hero'" (click)="setFilter('hero')">Core Scores</button>
          <button type="button" class="sc-chip" [class.active]="filter() === 'reliability'" (click)="setFilter('reliability')">Reliability Quadrant</button>
          <button type="button" class="sc-chip" [class.active]="filter() === 'adk'" (click)="setFilter('adk')">ADK NLP &amp; SLA</button>
          <button type="button" class="sc-chip" [class.active]="filter() === 'judge'" (click)="setFilter('judge')">LLM Judge</button>
        </div>
      </div>

      <div class="sc-metrics-grid">
        @for (item of filteredMetrics(); track item.key) {
          <article class="sc-metric-card">
            <header class="sc-metric-header">
              <div>
                <strong>{{ item.name }}</strong>
                <span class="sc-metric-scale">Scale: {{ item.scale }}</span>
              </div>
              <span class="sc-thresh-badge">Pass: {{ item.passThreshold }}</span>
            </header>

            <div class="sc-formula-box">
              <code>{{ item.formula }}</code>
            </div>

            <p class="sc-metric-desc">{{ item.meaning }}</p>

            <div class="sc-metric-lever">
              <span class="sc-lever-tag">How to improve:</span>
              <span>{{ item.howToImprove }}</span>
            </div>
          </article>
        }
      </div>
    </section>
  `,
  styles: [`
    .sc-explainer { margin-top: 10px; }
    .sc-explainer-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
    .sc-filter-chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .sc-chip { all: unset; box-sizing: border-box; cursor: pointer; font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
    .sc-chip:hover { color: var(--ink); }
    .sc-chip.active { color: var(--teal); border-color: var(--teal); background: color-mix(in srgb, var(--teal) 10%, transparent); }
    .sc-metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
    .sc-metric-card { border: 1px solid var(--line); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 10px; background: color-mix(in srgb, var(--card) 95%, transparent); }
    .sc-metric-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
    .sc-metric-scale { display: block; font-size: 11px; color: var(--muted); margin-top: 2px; }
    .sc-thresh-badge { font-size: 10px; font-weight: 600; color: var(--teal); border: 1px solid var(--teal); border-radius: 999px; padding: 2px 8px; white-space: nowrap; }
    .sc-formula-box { background: color-mix(in srgb, var(--line) 40%, transparent); padding: 8px 10px; border-radius: 6px; font-size: 11px; overflow-x: auto; }
    .sc-formula-box code { font-family: monospace; color: var(--teal); font-weight: 600; }
    .sc-metric-desc { margin: 0; font-size: 12px; color: var(--muted); line-height: 1.45; }
    .sc-metric-lever { font-size: 11px; line-height: 1.4; border-top: 1px dashed var(--line); padding-top: 8px; display: flex; flex-direction: column; gap: 3px; }
    .sc-lever-tag { color: var(--ink); font-weight: 600; }
  `]
})
export class MetricExplainerComponent {
  readonly metrics = METRICS;
  readonly filter = signal<'all' | 'hero' | 'reliability' | 'adk' | 'judge'>('all');

  filteredMetrics() {
    const f = this.filter();
    return f === 'all' ? this.metrics : this.metrics.filter(m => m.category === f);
  }

  setFilter(f: 'all' | 'hero' | 'reliability' | 'adk' | 'judge') {
    this.filter.set(f);
  }
}
'''

target = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\scorecard\metric-explainer.component.ts")
target.write_text(content, encoding="utf-8")
print("Wrote clean metric-explainer.component.ts successfully.")

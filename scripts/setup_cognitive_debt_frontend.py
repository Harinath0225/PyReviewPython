"""
Sets up the Cognitive Debt PR Gate Angular frontend:
1. Creates src/app/cognitive-debt.service.ts
2. Creates src/app/cognitive-debt.component.ts
3. Patches src/app/app.routes.ts to add /cognitive-debt route
4. Patches src/app/app.component.ts to add Cognitive Debt Gate tab in topbar
"""
import os
import re
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ANGULAR_ROOT = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular"
APP_DIR = os.path.join(ANGULAR_ROOT, "src", "app")

# ==========================================
# 1) Write cognitive-debt.service.ts
# ==========================================
service_content = '''import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface TelemetryResult {
  max_nesting_score: number;
  net_new_logic_loc: number;
  mock_tautology_ratio: number;
  cdi_score: number;
  gate_blocked: boolean;
}

export interface ImplicitDecision {
  title: string;
  file_and_line: string;
  hidden_assumption: string;
  production_risk: string;
}

export interface PRReviewPayload {
  decisions: ImplicitDecision[];
  socratic_question: string;
}

export interface ExplainVerdict {
  approved: boolean;
  feedback: string;
}

export interface CognitiveDebtResponse {
  telemetry: TelemetryResult;
  payload: PRReviewPayload;
  comment_markdown: string;
  verdict?: ExplainVerdict | null;
}

export interface SampleDiffPreset {
  name: string;
  diff_text: string;
  pr_body: string;
  description: string;
}

export interface SampleDiffsResponse {
  bad_pr: SampleDiffPreset;
  clean_pr: SampleDiffPreset;
}

@Injectable({
  providedIn: 'root',
})
export class CognitiveDebtService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = 'http://localhost:8000/api/v1/cognitive-debt';

  getSamples(): Observable<SampleDiffsResponse> {
    return this.http.get<SampleDiffsResponse>(`${this.baseUrl}/samples`);
  }

  analyze(diffText: string, prBody: string = ''): Observable<CognitiveDebtResponse> {
    return this.http.post<CognitiveDebtResponse>(`${this.baseUrl}/analyze`, {
      diff_text: diffText,
      pr_body: prBody,
      extract_decisions: true,
    });
  }

  explain(
    diffText: string,
    question: string,
    authorReply: string,
    telemetry?: TelemetryResult,
    payload?: PRReviewPayload
  ): Observable<CognitiveDebtResponse> {
    return this.http.post<CognitiveDebtResponse>(`${this.baseUrl}/explain`, {
      diff_text: diffText,
      question,
      author_reply: authorReply,
      telemetry,
      payload,
    });
  }
}
'''

service_path = os.path.join(APP_DIR, "cognitive-debt.service.ts")
with open(service_path, "w", encoding="utf-8") as f:
    f.write(service_content)
print(f"✓ Created {service_path}")


# ==========================================
# 2) Write cognitive-debt.component.ts
# ==========================================
component_content = '''import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CognitiveDebtService,
  CognitiveDebtResponse,
  SampleDiffsResponse,
} from './cognitive-debt.service';

@Component({
  selector: 'app-cognitive-debt',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <section class="page cognitive-page">
      <!-- Top Eyebrow & Hero Header -->
      <div class="eyebrow">AGENTIC PR GOVERNANCE <span></span> ZERO-INFRASTRUCTURE GATE</div>
      
      <div class="cognitive-header">
        <div>
          <h1>Cognitive Debt PR Gate</h1>
          <p>Surfaces silent AI architectural assumptions and blocks unreviewed AI code bursts using native AST telemetry & Socratic gates.</p>
        </div>
        <div class="preset-actions">
          <button type="button" class="preset-btn bad" (click)="loadPreset('bad')">
            <i class="material-symbols-outlined">warning</i>
            <span>Load Bad Agentic PR</span>
          </button>
          <button type="button" class="preset-btn clean" (click)="loadPreset('clean')">
            <i class="material-symbols-outlined">verified</i>
            <span>Load Clean PR</span>
          </button>
          <button type="button" class="preset-btn reset" (click)="resetForm()">
            <i class="material-symbols-outlined">restart_alt</i>
            <span>Reset</span>
          </button>
        </div>
      </div>

      <!-- Input Configuration Form -->
      <div class="card input-card">
        <div class="card-header">
          <div class="card-title">
            <i class="material-symbols-outlined">difference</i>
            <strong>Pull Request Diff & Context</strong>
          </div>
          <span class="badge" [ngClass]="{'badge-warn': bodyWordCount() < 30, 'badge-ok': bodyWordCount() >= 30}">
            PR Description: {{ bodyWordCount() }} words {{ bodyWordCount() < 30 ? '(1.5x AI penalty)' : '(Pass)' }}
          </span>
        </div>

        <div class="input-grid">
          <div class="field-group">
            <label for="diffText">
              <span>Unified Diff (or Python Source)</span>
              <small>Native AST calculates control-flow nesting depth and mock tautology</small>
            </label>
            <textarea
              id="diffText"
              rows="10"
              class="code-textarea"
              placeholder="Paste unified git diff (diff --git a/... b/...) or modified python lines..."
              [(ngModel)]="diffText"
            ></textarea>
          </div>

          <div class="field-group">
            <label for="prBody">
              <span>PR Description / Human Intent</span>
              <small>PRs with fewer than 30 words trigger a 1.5x unreviewed logic burst penalty</small>
            </label>
            <textarea
              id="prBody"
              rows="3"
              class="desc-textarea"
              placeholder="Provide the pull request context and rationale..."
              [(ngModel)]="prBody"
            ></textarea>
          </div>
        </div>

        <div class="card-actions">
          <button
            type="button"
            class="primary-btn"
            [disabled]="isAnalyzing() || !diffText.trim()"
            (click)="runAnalysis()"
          >
            @if (isAnalyzing()) {
              <span class="spinner"></span>
              <span>Running AST Scorer & LLM Decision Extractor...</span>
            } @else {
              <i class="material-symbols-outlined">psychology</i>
              <span>Analyze Cognitive Debt</span>
            }
          </button>
        </div>
      </div>

      <!-- Analysis Results Dashboard -->
      @if (analysis(); as res) {
        <div class="results-container">
          <!-- Gate Hero Banner -->
          <div class="gate-hero-card" [ngClass]="gateStatusClass()">
            <div class="hero-metric-box">
              <span class="hero-label">COMPOSITE COGNITIVE DEBT INDEX</span>
              <div class="hero-score">
                <strong>{{ res.telemetry.cdi_score }}</strong>
                <small>/ 100</small>
              </div>
              <div class="score-bar-bg">
                <div class="score-bar-fill" [style.width.%]="res.telemetry.cdi_score"></div>
              </div>
            </div>

            <div class="hero-status-box">
              <div class="gate-status-pill" [ngClass]="gateStatusClass()">
                <i class="material-symbols-outlined">{{ gateStatusIcon() }}</i>
                <span>{{ gateStatusTitle() }}</span>
              </div>
              <p class="hero-description">{{ gateStatusMessage() }}</p>
              @if (res.verdict) {
                <div class="status-transition">
                  <span class="old-status">🚨 BLOCKED</span>
                  <i class="material-symbols-outlined">arrow_forward</i>
                  <span class="new-status" [class.unlocked]="res.verdict.approved">
                    {{ res.verdict.approved ? '✅ UNLOCKED' : '🚨 STILL BLOCKED' }}
                  </span>
                </div>
              }
            </div>
          </div>

          <!-- 3 Core Metric Breakdown Cards -->
          <div class="metrics-grid">
            <!-- 1. AST Nesting Complexity -->
            <div class="metric-card">
              <div class="metric-header">
                <i class="material-symbols-outlined metric-icon">account_tree</i>
                <span class="metric-name">AST Nesting Complexity</span>
              </div>
              <div class="metric-val-row">
                <strong class="metric-big-val">{{ res.telemetry.max_nesting_score }}</strong>
                <span class="metric-pts">{{ cdiPts(res).c_pts }} / 40 pts</span>
              </div>
              <p class="metric-desc">
                Calculated via native <code>ast.walk()</code>: +1 for control nodes, +2 penalty for each nesting depth level &gt; 2.
              </p>
            </div>

            <!-- 2. Undocumented Logic Burst -->
            <div class="metric-card">
              <div class="metric-header">
                <i class="material-symbols-outlined metric-icon">history_edu</i>
                <span class="metric-name">Undocumented Logic Burst</span>
              </div>
              <div class="metric-val-row">
                <strong class="metric-big-val">{{ res.telemetry.net_new_logic_loc }} <small>LOC</small></strong>
                <span class="metric-pts">{{ cdiPts(res).l_pts }} / 35 pts</span>
              </div>
              <p class="metric-desc">
                Added executable lines. Multiplier: <strong>{{ bodyWordCount() < 30 ? '1.5x (Body < 30 words)' : '1.0x (Described)' }}</strong>.
              </p>
            </div>

            <!-- 3. Test Tautology -->
            <div class="metric-card">
              <div class="metric-header">
                <i class="material-symbols-outlined metric-icon">quiz</i>
                <span class="metric-name">Test Tautology (Mock Ratio)</span>
              </div>
              <div class="metric-val-row">
                <strong class="metric-big-val">{{ (res.telemetry.mock_tautology_ratio * 100) | number:'1.0-1' }}%</strong>
                <span class="metric-pts">{{ cdiPts(res).t_pts }} / 25 pts</span>
              </div>
              <p class="metric-desc">
                Ratio of tautological <code>assert_called*</code> mock invocations vs verified output <code>ast.Assert</code> statements.
              </p>
            </div>
          </div>

          <!-- Section: Implicit Decisions Made by Coding Agent -->
          <div class="card decisions-card">
            <div class="card-header">
              <div class="card-title">
                <i class="material-symbols-outlined">smart_toy</i>
                <strong>🧠 What Your Coding Agent Decided For You</strong>
              </div>
              <span class="badge badge-purple">{{ res.payload.decisions.length }} Silent Assumptions Flagged</span>
            </div>

            <p class="section-lead">
              The AI coding agent implemented these critical architectural decisions without documentation in the PR description:
            </p>

            <div class="decisions-list">
              @for (dec of res.payload.decisions; track $index) {
                <div class="decision-item">
                  <div class="decision-head">
                    <span class="decision-num">#{{ $index + 1 }}</span>
                    <strong class="decision-title">{{ dec.title }}</strong>
                    <span class="file-badge">{{ dec.file_and_line }}</span>
                  </div>
                  <div class="decision-body">
                    <div class="assumption-box">
                      <span class="box-lbl">Hidden Assumption</span>
                      <p>{{ dec.hidden_assumption }}</p>
                    </div>
                    <div class="risk-box">
                      <span class="box-lbl">Production Failure Risk</span>
                      <p>{{ dec.production_risk }}</p>
                    </div>
                  </div>
                </div>
              }
            </div>
          </div>

          <!-- Section: Socratic Gate Question & /explain Reply -->
          <div class="card socratic-card" [ngClass]="{'card-unlocked': res.verdict?.approved}">
            <div class="card-header">
              <div class="card-title">
                <i class="material-symbols-outlined">{{ res.verdict?.approved ? 'lock_open' : 'lock' }}</i>
                <strong>🔐 Socratic Gatekeeper Challenge</strong>
              </div>
              <span class="badge" [ngClass]="res.verdict?.approved ? 'badge-ok' : 'badge-blocked'">
                {{ res.verdict?.approved ? 'GATE UNLOCKED' : (res.telemetry.gate_blocked ? 'GATE BLOCKED' : 'OPTIONAL EXPLANATION') }}
              </span>
            </div>

            <div class="question-callout">
              <div class="question-kicker">CHALLENGE QUESTION FOR THE AUTHOR:</div>
              <blockquote class="question-text">
                "{{ res.payload.socratic_question }}"
              </blockquote>
              <div class="question-sub">
                To unlock this pull request, the developer must justify the design tradeoff by replying with <code>/explain &lt;your rationale&gt;</code>.
              </div>
            </div>

            <!-- Explain Reply Box -->
            <div class="explain-form">
              <label for="explainReply">
                <strong>Author Reply:</strong>
                <small>Enter your technical rationale below or click a quick-demo button</small>
              </label>
              
              <div class="quick-reply-row">
                <button
                  type="button"
                  class="quick-reply-btn reject-demo"
                  (click)="setQuickReply('handwavy')"
                >
                  <i class="material-symbols-outlined">cancel</i>
                  <span>Test Hand-Wavy Reply (Rejected)</span>
                </button>
                <button
                  type="button"
                  class="quick-reply-btn approve-demo"
                  (click)="setQuickReply('solid')"
                >
                  <i class="material-symbols-outlined">check_circle</i>
                  <span>Test Architectural Reply (Unlocked)</span>
                </button>
              </div>

              <textarea
                id="explainReply"
                rows="3"
                class="explain-textarea"
                placeholder="/explain <describe concurrency safety, idempotency, or architectural mitigations>..."
                [(ngModel)]="authorReply"
              ></textarea>

              <div class="explain-actions">
                <button
                  type="button"
                  class="primary-btn"
                  [disabled]="isExplaining() || !authorReply.trim()"
                  (click)="submitExplanation()"
                >
                  @if (isExplaining()) {
                    <span class="spinner"></span>
                    <span>Evaluating with LLM Gate Judge...</span>
                  } @else {
                    <i class="material-symbols-outlined">gavel</i>
                    <span>Submit /explain to Judge</span>
                  }
                </button>
              </div>
            </div>

            <!-- Verdict Card Display -->
            @if (res.verdict) {
              <div class="verdict-banner" [ngClass]="res.verdict.approved ? 'verdict-approved' : 'verdict-rejected'">
                <div class="verdict-head">
                  <i class="material-symbols-outlined">
                    {{ res.verdict.approved ? 'verified' : 'error' }}
                  </i>
                  <strong>
                    {{ res.verdict.approved ? 'PR Gate Unlocked: Author Rationale Accepted' : 'PR Gate Blocked: Explanation Rejected' }}
                  </strong>
                </div>
                <p class="verdict-feedback">{{ res.verdict.feedback }}</p>
                <div class="status-summary">
                  GitHub PR Status Check: 
                  <strong>{{ res.verdict.approved ? 'SUCCESS (Exit Code 0)' : 'FAILURE (Exit Code 1)' }}</strong>
                </div>
              </div>
            }
          </div>

          <!-- Section: GitHub PR Comment Markdown Preview -->
          <div class="card preview-card">
            <div class="card-header">
              <div class="card-title">
                <i class="material-symbols-outlined">markdown</i>
                <strong>GitHub PR Comment Preview (Stateless Tag Embedded)</strong>
              </div>
              <button type="button" class="copy-btn" (click)="copyComment()">
                <i class="material-symbols-outlined">content_copy</i>
                <span>{{ copied() ? 'Copied!' : 'Copy Markdown' }}</span>
              </button>
            </div>
            <pre class="comment-preview"><code>{{ res.comment_markdown }}</code></pre>
          </div>
        </div>
      }
    </section>
  `,
  styles: [`
    .cognitive-page { padding: 30px; max-width: 1200px; margin: 0 auto; }
    .cognitive-header { display: flex; justify-content: space-between; align-items: flex-end; margin: 20px 0 30px; gap: 20px; flex-wrap: wrap; }
    .cognitive-header h1 { font-size: 42px; letter-spacing: -2px; margin: 0 0 8px; color: var(--ink); }
    .cognitive-header p { color: var(--muted); font-size: 14px; max-width: 650px; margin: 0; line-height: 1.5; }
    
    .preset-actions { display: flex; gap: 10px; align-items: center; }
    .preset-btn {
      display: inline-flex; align-items: center; gap: 7px;
      padding: 9px 15px; border-radius: 6px; font-size: 12px; font-weight: 600;
      cursor: pointer; transition: all 0.2s; border: 1px solid var(--line);
      background: var(--card); color: var(--ink);
    }
    .preset-btn.bad { border-color: rgba(255, 93, 117, 0.4); background: rgba(255, 93, 117, 0.08); color: var(--coral); }
    .preset-btn.bad:hover { background: rgba(255, 93, 117, 0.16); }
    .preset-btn.clean { border-color: rgba(45, 226, 208, 0.4); background: rgba(45, 226, 208, 0.08); color: var(--teal); }
    .preset-btn.clean:hover { background: rgba(45, 226, 208, 0.16); }
    .preset-btn.reset:hover { background: #eee; }

    .card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 22px; margin-bottom: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.03); }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
    .card-title { display: flex; align-items: center; gap: 8px; font-size: 16px; color: var(--ink); }
    
    .badge { padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .badge-warn { background: rgba(255, 200, 87, 0.15); color: #9a6b0d; border: 1px solid rgba(255, 200, 87, 0.35); }
    .badge-ok { background: rgba(45, 226, 208, 0.15); color: var(--teal); border: 1px solid rgba(45, 226, 208, 0.35); }
    .badge-blocked { background: rgba(255, 93, 117, 0.15); color: var(--coral); border: 1px solid rgba(255, 93, 117, 0.35); }
    .badge-purple { background: rgba(168, 85, 247, 0.15); color: #9333ea; border: 1px solid rgba(168, 85, 247, 0.35); }

    .input-grid { display: flex; flex-direction: column; gap: 16px; }
    .field-group label { display: flex; justify-content: space-between; margin-bottom: 7px; font-size: 13px; font-weight: 600; color: var(--ink); }
    .field-group label small { color: var(--muted); font-weight: 400; font-size: 11px; }
    .code-textarea, .desc-textarea, .explain-textarea {
      width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 12px;
      font-size: 13px; font-family: 'Courier New', monospace; line-height: 1.5;
      background: #fafcfb; color: var(--ink); resize: vertical; box-sizing: border-box;
    }
    .code-textarea:focus, .desc-textarea:focus, .explain-textarea:focus {
      outline: none; border-color: var(--teal); box-shadow: 0 0 0 3px rgba(45, 226, 208, 0.15);
    }
    .card-actions { margin-top: 18px; display: flex; justify-content: flex-end; }

    /* Gate Hero Banner */
    .gate-hero-card {
      display: grid; grid-template-columns: 280px 1fr; gap: 24px;
      padding: 24px; border-radius: 8px; margin-bottom: 24px;
      border: 1px solid var(--line);
    }
    .gate-hero-card.gate-blocked {
      background: linear-gradient(135deg, rgba(255, 93, 117, 0.12), rgba(255, 255, 255, 0.9));
      border-color: rgba(255, 93, 117, 0.4);
    }
    .gate-hero-card.gate-unlocked {
      background: linear-gradient(135deg, rgba(45, 226, 208, 0.12), rgba(255, 255, 255, 0.9));
      border-color: rgba(45, 226, 208, 0.4);
    }
    .hero-metric-box { display: flex; flex-direction: column; justify-content: center; }
    .hero-label { font-size: 10px; font-family: 'Courier New', monospace; letter-spacing: 1px; color: var(--muted); }
    .hero-score strong { font-size: 54px; letter-spacing: -3px; color: var(--ink); line-height: 1; }
    .hero-score small { font-size: 18px; color: var(--muted); margin-left: 4px; }
    .score-bar-bg { height: 8px; background: rgba(0,0,0,0.06); border-radius: 4px; overflow: hidden; margin-top: 10px; }
    .score-bar-fill { height: 100%; background: var(--coral); transition: width 0.4s ease; }
    .gate-unlocked .score-bar-fill { background: var(--teal); }

    .hero-status-box { display: flex; flex-direction: column; justify-content: center; }
    .gate-status-pill {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 14px; border-radius: 20px; font-size: 14px; font-weight: 700; width: fit-content;
      margin-bottom: 10px;
    }
    .gate-status-pill.gate-blocked { background: var(--coral); color: #fff; }
    .gate-status-pill.gate-unlocked { background: var(--teal); color: #fff; }
    .hero-description { color: var(--ink); font-size: 14px; line-height: 1.5; margin: 0 0 10px; }
    
    .status-transition {
      display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; margin-top: 6px;
    }
    .old-status { text-decoration: line-through; color: var(--muted); }
    .new-status.unlocked { color: var(--teal); font-weight: 700; }

    /* Metrics Grid */
    .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
    .metric-card {
      background: var(--card); border: 1px solid var(--line); border-radius: 8px;
      padding: 18px; display: flex; flex-direction: column;
    }
    .metric-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .metric-icon { font-size: 20px; color: var(--teal); }
    .metric-name { font-size: 13px; font-weight: 600; color: var(--ink); }
    .metric-val-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
    .metric-big-val { font-size: 32px; letter-spacing: -1.5px; color: var(--ink); }
    .metric-big-val small { font-size: 13px; color: var(--muted); }
    .metric-pts { font-size: 12px; font-weight: 700; color: var(--coral); font-family: 'Courier New', monospace; }
    .metric-desc { font-size: 11px; color: var(--muted); line-height: 1.4; margin: 0; }

    /* Decisions List */
    .section-lead { font-size: 13px; color: var(--muted); margin: 0 0 16px; }
    .decisions-list { display: flex; flex-direction: column; gap: 14px; }
    .decision-item {
      border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; background: #fafcfb;
    }
    .decision-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
    .decision-num {
      width: 24px; height: 24px; border-radius: 50%; background: #e0e8e4;
      display: inline-grid; place-items: center; font-size: 11px; font-weight: 700; color: var(--ink);
    }
    .decision-title { font-size: 14px; color: var(--ink); }
    .file-badge { font-size: 11px; font-family: 'Courier New', monospace; color: var(--muted); background: #eee; padding: 2px 7px; border-radius: 4px; }
    .decision-body { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .assumption-box, .risk-box { padding: 10px 12px; border-radius: 5px; font-size: 12px; }
    .assumption-box { background: rgba(106, 168, 255, 0.08); border-left: 3px solid #6aa8ff; }
    .risk-box { background: rgba(255, 93, 117, 0.08); border-left: 3px solid var(--coral); }
    .box-lbl { font-size: 10px; font-family: 'Courier New', monospace; text-transform: uppercase; font-weight: 700; color: var(--muted); display: block; margin-bottom: 4px; }
    .assumption-box p, .risk-box p { margin: 0; line-height: 1.4; color: var(--ink); }

    /* Socratic Challenge Card */
    .socratic-card { border-left: 4px solid var(--coral); }
    .socratic-card.card-unlocked { border-left-color: var(--teal); }
    .question-callout {
      background: #f5f8f7; border: 1px solid var(--line); border-radius: 6px; padding: 16px 18px; margin-bottom: 18px;
    }
    .question-kicker { font-size: 11px; font-family: 'Courier New', monospace; color: var(--coral); font-weight: 700; letter-spacing: 0.8px; margin-bottom: 6px; }
    .question-text { font-size: 16px; font-weight: 600; color: var(--ink); margin: 0 0 8px; line-height: 1.5; font-style: italic; }
    .question-sub { font-size: 12px; color: var(--muted); }

    .quick-reply-row { display: flex; gap: 10px; margin: 10px 0 12px; flex-wrap: wrap; }
    .quick-reply-btn {
      display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px;
      font-size: 12px; border-radius: 6px; cursor: pointer; border: 1px solid var(--line); background: var(--card);
    }
    .quick-reply-btn.reject-demo { color: var(--coral); border-color: rgba(255, 93, 117, 0.3); }
    .quick-reply-btn.reject-demo:hover { background: rgba(255, 93, 117, 0.08); }
    .quick-reply-btn.approve-demo { color: var(--teal); border-color: rgba(45, 226, 208, 0.3); }
    .quick-reply-btn.approve-demo:hover { background: rgba(45, 226, 208, 0.08); }

    .explain-actions { margin-top: 12px; display: flex; justify-content: flex-end; }

    /* Verdict Banner */
    .verdict-banner { margin-top: 18px; border-radius: 6px; padding: 16px 18px; }
    .verdict-approved { background: rgba(45, 226, 208, 0.1); border: 1px solid rgba(45, 226, 208, 0.4); }
    .verdict-rejected { background: rgba(255, 93, 117, 0.1); border: 1px solid rgba(255, 93, 117, 0.4); }
    .verdict-head { display: flex; align-items: center; gap: 8px; font-size: 15px; margin-bottom: 6px; }
    .verdict-approved .verdict-head { color: var(--teal); }
    .verdict-rejected .verdict-head { color: var(--coral); }
    .verdict-feedback { font-size: 13px; line-height: 1.5; color: var(--ink); margin: 0 0 8px; }
    .status-summary { font-size: 11px; font-family: 'Courier New', monospace; color: var(--muted); }
    .status-summary strong { color: var(--ink); }

    /* Markdown Preview Card */
    .copy-btn {
      display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px;
      font-size: 11px; border-radius: 4px; border: 1px solid var(--line);
      background: var(--card); cursor: pointer; color: var(--muted);
    }
    .copy-btn:hover { color: var(--ink); background: #f0f0f0; }
    .comment-preview {
      background: #0f1715; color: #d1ded8; padding: 16px; border-radius: 6px;
      font-size: 12px; font-family: 'Courier New', monospace; line-height: 1.5;
      overflow-x: auto; max-height: 400px;
    }

    .spinner {
      display: inline-block; width: 14px; height: 14px;
      border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
      border-radius: 50%; animation: spin 0.7s linear infinite; margin-right: 6px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    @media (max-width: 900px) {
      .gate-hero-card { grid-template-columns: 1fr; }
      .metrics-grid { grid-template-columns: 1fr; }
      .decision-body { grid-template-columns: 1fr; }
    }
  `]
})
export class CognitiveDebtComponent implements OnInit {
  private readonly debtService = inject(CognitiveDebtService);

  diffText = '';
  prBody = '';
  authorReply = '';

  isAnalyzing = signal(false);
  isExplaining = signal(false);
  analysis = signal<CognitiveDebtResponse | null>(null);
  copied = signal(false);
  samples = signal<SampleDiffsResponse | null>(null);

  bodyWordCount = computed(() => {
    const text = this.prBody.trim();
    return text ? text.split(/\\s+/).length : 0;
  });

  ngOnInit(): void {
    this.debtService.getSamples().subscribe({
      next: (data) => {
        this.samples.set(data);
        // Pre-load the bad PR demo by default
        this.loadPreset('bad');
      },
      error: (err) => console.warn('Could not load PR samples:', err)
    });
  }

  loadPreset(type: 'bad' | 'clean'): void {
    const s = this.samples();
    if (!s) return;

    if (type === 'bad') {
      this.diffText = s.bad_pr.diff_text;
      this.prBody = s.bad_pr.pr_body;
      this.authorReply = '';
    } else {
      this.diffText = s.clean_pr.diff_text;
      this.prBody = s.clean_pr.pr_body;
      this.authorReply = '';
    }
    this.analysis.set(null);
  }

  resetForm(): void {
    this.diffText = '';
    this.prBody = '';
    this.authorReply = '';
    this.analysis.set(null);
  }

  runAnalysis(): void {
    if (!this.diffText.trim()) return;
    this.isAnalyzing.set(true);

    this.debtService.analyze(this.diffText, this.prBody).subscribe({
      next: (res) => {
        this.analysis.set(res);
        this.isAnalyzing.set(false);
      },
      error: (err) => {
        console.error('Analysis failed:', err);
        this.isAnalyzing.set(false);
        alert('Failed to analyze diff: ' + (err.error?.detail || err.message));
      }
    });
  }

  setQuickReply(type: 'handwavy' | 'solid'): void {
    if (type === 'handwavy') {
      this.authorReply = '/explain AI wrote it, looks fine to me, please just approve.';
    } else {
      this.authorReply = (
        '/explain To ensure transaction atomicity and prevent duplicate charges on restart, each transaction ' +
        'carries an idempotent UUID passed to the gateway charge() call. The gateway deduplicates identical ' +
        'transaction IDs on its side. The in-memory cache is purely an ephemeral read cache to avoid re-querying ' +
        'active orders, so a process crash safely re-reads the relational DB state on restart without duplicate charges.'
      );
    }
  }

  submitExplanation(): void {
    const res = this.analysis();
    if (!res || !this.authorReply.trim()) return;

    this.isExplaining.set(true);
    this.debtService
      .explain(
        this.diffText,
        res.payload.socratic_question,
        this.authorReply,
        res.telemetry,
        res.payload
      )
      .subscribe({
        next: (updated) => {
          this.analysis.set(updated);
          this.isExplaining.set(false);
        },
        error: (err) => {
          console.error('Explanation evaluation failed:', err);
          this.isExplaining.set(false);
          alert('Failed to evaluate explanation: ' + (err.error?.detail || err.message));
        }
      });
  }

  copyComment(): void {
    const res = this.analysis();
    if (!res) return;
    navigator.clipboard.writeText(res.comment_markdown).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  cdiPts(res: CognitiveDebtResponse): { c_pts: number; l_pts: number; t_pts: number } {
    const effLoc = this.bodyWordCount() < 30 ? Math.floor(res.telemetry.net_new_logic_loc * 1.5) : res.telemetry.net_new_logic_loc;
    return {
      c_pts: Math.min(40, res.telemetry.max_nesting_score * 2),
      l_pts: Math.min(35, Math.floor((effLoc / 300) * 35)),
      t_pts: Math.floor(res.telemetry.mock_tautology_ratio * 25)
    };
  }

  gateStatusClass(): string {
    const res = this.analysis();
    if (!res) return '';
    if (res.verdict?.approved) return 'gate-unlocked';
    return res.telemetry.gate_blocked ? 'gate-blocked' : 'gate-unlocked';
  }

  gateStatusIcon(): string {
    const res = this.analysis();
    if (!res) return 'help';
    if (res.verdict?.approved) return 'verified';
    return res.telemetry.gate_blocked ? 'lock' : 'verified';
  }

  gateStatusTitle(): string {
    const res = this.analysis();
    if (!res) return '';
    if (res.verdict?.approved) return 'GATE UNLOCKED (APPROVED)';
    return res.telemetry.gate_blocked ? 'GATE BLOCKED (HIGH DEBT)' : 'GATE PASSED (LOW DEBT)';
  }

  gateStatusMessage(): string {
    const res = this.analysis();
    if (!res) return '';
    if (res.verdict?.approved) {
      return 'Author rationale accepted by LLM Judge. The PR status check transitioned from BLOCKED to SUCCESS.';
    }
    if (res.telemetry.gate_blocked) {
      return 'Cognitive Debt Index (CDI) exceeds the safety threshold of 65. The developer must answer the Socratic question below to unlock this PR.';
    }
    return 'PR is within safe cognitive debt boundaries with low control-flow complexity and valid tests.';
  }
}
'''

component_path = os.path.join(APP_DIR, "cognitive-debt.component.ts")
with open(component_path, "w", encoding="utf-8") as f:
    f.write(component_content)
print(f"✓ Created {component_path}")


# ==========================================
# 3) Patch app.routes.ts
# ==========================================
routes_path = os.path.join(APP_DIR, "app.routes.ts")
with open(routes_path, "r", encoding="utf-8") as f:
    routes_code = f.read()

if "CognitiveDebtComponent" not in routes_code:
    routes_code = (
        "import { CognitiveDebtComponent } from './cognitive-debt.component';\n"
        + routes_code
    )
    routes_code = routes_code.replace(
        "{ path: 'scorecard', component: ScorecardComponent },",
        "{ path: 'scorecard', component: ScorecardComponent },\n  { path: 'cognitive-debt', component: CognitiveDebtComponent },"
    )
    with open(routes_path, "w", encoding="utf-8") as f:
        f.write(routes_code)
    print("✓ Patched app.routes.ts")
else:
    print("• app.routes.ts already has CognitiveDebtComponent")


# ==========================================
# 4) Patch app.component.ts
# ==========================================
app_component_path = os.path.join(APP_DIR, "app.component.ts")
with open(app_component_path, "r", encoding="utf-8") as f:
    app_code = f.read()

nav_tag = '<a routerLink="/scorecard" routerLinkActive="active"><i class="material-symbols-outlined">monitoring</i><span>Agent Scorecard</span></a>'
new_nav_tag = (
    '<a routerLink="/scorecard" routerLinkActive="active"><i class="material-symbols-outlined">monitoring</i><span>Agent Scorecard</span></a>'
    '<a routerLink="/cognitive-debt" routerLinkActive="active"><i class="material-symbols-outlined">psychology_alt</i><span>Cognitive Debt Gate</span></a>'
)

if 'routerLink="/cognitive-debt"' not in app_code:
    if nav_tag in app_code:
        app_code = app_code.replace(nav_tag, new_nav_tag)
        with open(app_component_path, "w", encoding="utf-8") as f:
            f.write(app_code)
        print("✓ Patched app.component.ts navigation")
    else:
        print("! Could not find scorecard nav link in app.component.ts to append Cognitive Debt tab")
else:
    print("• app.component.ts already has Cognitive Debt Gate tab")

print("\n🚀 All Angular frontend files successfully configured!")

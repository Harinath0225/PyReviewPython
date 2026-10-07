from pathlib import Path

# 1. Update scorecard.models.ts
models_file = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\scorecard\scorecard.models.ts")
models_text = models_file.read_text(encoding="utf-8")
old_labels = """export const SOURCE_LABELS: Record<SourceFilter, string> = {
  all: 'All sources',
  agent_lab: 'Agent Lab',
  adk_eval: 'ADK Web UI',
  code_review: 'Code reviews'
};"""
new_labels = """export const SOURCE_LABELS: Record<SourceFilter, string> = {
  all: 'Unified Scorecard (Combined)',
  agent_lab: 'Lab Benchmarks',
  adk_eval: 'ADK Web Suite',
  code_review: 'Production PRs'
};"""
if old_labels in models_text:
    models_text = models_text.replace(old_labels, new_labels)
    models_file.write_text(models_text, encoding="utf-8")
    print("Updated SOURCE_LABELS in scorecard.models.ts")

# 2. Update scorecard.component.ts
scorecard_file = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\scorecard\scorecard.component.ts")
sc_text = scorecard_file.read_text(encoding="utf-8")

# Add imports
if "BehaviorStudioComponent" not in sc_text:
    sc_text = sc_text.replace(
        "import { MetricExplainerComponent } from './metric-explainer.component';",
        "import { MetricExplainerComponent } from './metric-explainer.component';\nimport { BehaviorStudioComponent } from './behavior-studio.component';\nimport { TokenomicsDashboardComponent } from './tokenomics-dashboard.component';"
    )
    sc_text = sc_text.replace(
        "MetricExplainerComponent\n  ]",
        "MetricExplainerComponent,\n    BehaviorStudioComponent,\n    TokenomicsDashboardComponent\n  ]"
    )
    # Add components into template
    # Insert behavior studio before judge calibration or after hero stats
    sc_text = sc_text.replace(
        "<app-judge-calibration (calibrated)=\"load()\" />",
        "<app-tokenomics-dashboard [metrics]=\"efficiency()\" />\n      <app-behavior-studio [currentCapability]=\"summary()?.capability_score ?? 25\" [currentReliability]=\"summary()?.reliability_index ?? 65\" [currentCost]=\"efficiency()?.cost_usd_per_task ?? 0.003\" />\n      <app-judge-calibration (calibrated)=\"load()\" />"
    )
    # Update eyebrow and title
    sc_text = sc_text.replace(
        "<div class=\"eyebrow\">AGENT LAB <span></span> SCORECARD</div>",
        "<div class=\"eyebrow\">AGENT LAB &amp; INTELLIGENCE <span></span> UNIFIED SCORECARD</div>"
    )
    sc_text = sc_text.replace(
        "<h1>Agent scorecard.</h1>\n          <p>Capability, reliability, adaptability and efficiency across evaluation runs.</p>",
        "<h1>Agent scorecard.</h1>\n          <p>Unified capability, reliability, tokenomics and LLM-as-a-judge across benchmark and production runs.</p>"
    )
    scorecard_file.write_text(sc_text, encoding="utf-8")
    print("Updated scorecard.component.ts with BehaviorStudio and TokenomicsDashboard.")

# 3. Update app.component.ts navigation
app_comp_file = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\app.component.ts")
app_text = app_comp_file.read_text(encoding="utf-8")
old_nav = """<a routerLink="/agent-lab" routerLinkActive="active"><i class="material-symbols-outlined">science</i><span>Agent lab</span></a><a routerLink="/scorecard" routerLinkActive="active"><i class="material-symbols-outlined">monitoring</i><span>Agent Scorecard</span></a>"""
new_nav = """<a routerLink="/scorecard" routerLinkActive="active"><i class="material-symbols-outlined">analytics</i><span>Agent Scorecard &amp; Lab</span></a><a routerLink="/agent-lab" routerLinkActive="active" style="opacity: 0.7;"><i class="material-symbols-outlined">security</i><span>Model Armor</span></a>"""
if old_nav in app_text:
    app_text = app_text.replace(old_nav, new_nav)
    app_comp_file.write_text(app_text, encoding="utf-8")
    print("Updated navigation in app.component.ts")

print("All integrations complete.")

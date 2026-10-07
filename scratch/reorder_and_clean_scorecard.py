from pathlib import Path

# 1. Update app.routes.ts
routes_file = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\app.routes.ts")
routes_text = routes_file.read_text(encoding="utf-8")
routes_text = routes_text.replace(
    "{ path: 'agent-lab', component: AgentLabComponent },",
    "{ path: 'agent-lab', redirectTo: 'scorecard', pathMatch: 'full' },"
)
routes_file.write_text(routes_text, encoding="utf-8")
print("app.routes.ts updated: /agent-lab now redirects to /scorecard")

# 2. Update app.component.ts
app_file = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\app.component.ts")
app_text = app_file.read_text(encoding="utf-8")
old_nav = """<nav aria-label="Primary navigation"><a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact: true}"><i class="material-symbols-outlined">edit_note</i><span>New review</span></a><a routerLink="/history" routerLinkActive="active"><i class="material-symbols-outlined">history</i><span>History</span></a><a routerLink="/scorecard" routerLinkActive="active"><i class="material-symbols-outlined">analytics</i><span>Agent Scorecard &amp; Lab</span></a><a routerLink="/agent-lab" routerLinkActive="active" style="opacity: 0.7;"><i class="material-symbols-outlined">security</i><span>Model Armor</span></a></nav>"""
clean_nav = """<nav aria-label="Primary navigation"><a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact: true}"><i class="material-symbols-outlined">edit_note</i><span>New review</span></a><a routerLink="/history" routerLinkActive="active"><i class="material-symbols-outlined">history</i><span>History</span></a><a routerLink="/scorecard" routerLinkActive="active"><i class="material-symbols-outlined">monitoring</i><span>Agent Scorecard</span></a></nav>"""
if old_nav in app_text:
    app_text = app_text.replace(old_nav, clean_nav)
else:
    # generic replace
    app_text = app_text.replace("""<a routerLink="/agent-lab" routerLinkActive="active" style="opacity: 0.7;"><i class="material-symbols-outlined">security</i><span>Model Armor</span></a>""", "")
app_file.write_text(app_text, encoding="utf-8")
print("app.component.ts updated: clean 3-item navigation")

# 3. Update scorecard.component.ts
scorecard_file = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\scorecard\scorecard.component.ts")
sc_text = scorecard_file.read_text(encoding="utf-8")

# Remove the 4-tab bar
sc_tabs_block = """      <nav class="sc-tabs" aria-label="Run source">
        @for (tab of tabs; track tab.value) {
          <button type="button" class="sc-tab" [class.active]="source() === tab.value" (click)="setSource(tab.value)">{{ tab.label }}</button>
        }
      </nav>"""
if sc_tabs_block in sc_text:
    sc_text = sc_text.replace(sc_tabs_block, "")
    print("Removed 4 tabs navigation from scorecard.component.ts")

# Update eyebrow
sc_text = sc_text.replace(
    """<div class="eyebrow">AGENT LAB &amp; INTELLIGENCE <span></span> UNIFIED SCORECARD</div>""",
    """<div class="eyebrow">PYREVIEW OBSERVABILITY <span></span> UNIFIED AGENT SCORECARD</div>"""
)
sc_text = sc_text.replace(
    """<div class="eyebrow">AGENT LAB <span></span> SCORECARD</div>""",
    """<div class="eyebrow">PYREVIEW OBSERVABILITY <span></span> UNIFIED AGENT SCORECARD</div>"""
)

# Re-order template to place Tokenomics and Behavior Studio prominently at the top
old_template_order = """      <app-source-comparison [breakdown]="breakdown()" [selected]="source()" (select)="setSource($event)" />
      <app-hero-stats [summary]="summary()" />
      <app-metric-explainer />
      <app-kpi-mapping [scorecard]="kpis()" />
      <app-reliability-quadrant [metrics]="reliability()" />
      <div class="sc-two">
        <app-adaptability-grid [metrics]="reliability()" />
        <app-efficiency-metrics [metrics]="efficiency()" [runs]="runs()" />
      </div>
      <app-tokenomics-dashboard [metrics]="efficiency()" />
      <app-behavior-studio [currentCapability]="summary()?.capability_score ?? 25" [currentReliability]="summary()?.reliability_index ?? 65" [currentCost]="efficiency()?.cost_usd_per_task ?? 0.003" />
      <app-judge-calibration (calibrated)="load()" />
      <app-trajectory-logs [runs]="runs()" />"""

new_template_order = """      <app-hero-stats [summary]="summary()" />
      <app-tokenomics-dashboard [metrics]="efficiency()" />
      <app-behavior-studio [currentCapability]="summary()?.capability_score ?? 25" [currentReliability]="summary()?.reliability_index ?? 65" [currentCost]="efficiency()?.cost_usd_per_task ?? 0.003" />
      <app-judge-calibration (calibrated)="load()" />
      <app-metric-explainer />
      <app-reliability-quadrant [metrics]="reliability()" />
      <div class="sc-two">
        <app-adaptability-grid [metrics]="reliability()" />
        <app-efficiency-metrics [metrics]="efficiency()" [runs]="runs()" />
      </div>
      <app-kpi-mapping [scorecard]="kpis()" />
      <app-source-comparison [breakdown]="breakdown()" [selected]="source()" (select)="setSource($event)" />
      <app-trajectory-logs [runs]="runs()" />"""

if old_template_order in sc_text:
    sc_text = sc_text.replace(old_template_order, new_template_order)
    print("Reordered scorecard template: Hero -> Tokenomics -> Behavior Studio -> LLM Judge Calibration")

scorecard_file.write_text(sc_text, encoding="utf-8")
print("scorecard.component.ts updated successfully.")

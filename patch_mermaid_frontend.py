"""
Patches the Angular frontend to render Mermaid diagrams using
the Mermaid JS API directly, instead of relying on ngx-markdown.

Changes:
1. review.service.ts - Add dependencyFlowDiagram to ReviewRecord + fromApi mapping
2. review.component.ts - Add a dedicated mermaid rendering section + AfterViewChecked logic
3. Revert summary display back to plain text (remove ngx-markdown dep from summary)
"""
import re

# ==========================
# 1) Patch review.service.ts
# ==========================
service_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\review.service.ts"
with open(service_path, "r", encoding="utf-8") as f:
    service = f.read()

# Add dependencyFlowDiagram to ReviewRecord interface
if "dependencyFlowDiagram" not in service:
    service = service.replace(
        "files?: ReviewFile[];\n}",
        "files?: ReviewFile[];\n  dependencyFlowDiagram?: string;\n}"
    )

    # Map it in fromApi
    service = service.replace(
        "const review: ReviewRecord = {",
        "const depDiagram = result['dependency_flow_diagram'] ? String(result['dependency_flow_diagram']) : undefined;\n    const review: ReviewRecord = {"
    )
    service = service.replace(
        "      files\n    };",
        "      files,\n      dependencyFlowDiagram: depDiagram\n    };"
    )

    with open(service_path, "w", encoding="utf-8") as f:
        f.write(service)
    print("✓ Patched review.service.ts")
else:
    print("• review.service.ts already patched")

# =============================
# 2) Patch review.component.ts
# =============================
component_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\review.component.ts"
with open(component_path, "r", encoding="utf-8") as f:
    component = f.read()

# Revert the markdown tag back to <p> for the summary
if "<markdown" in component:
    component = component.replace(
        '<markdown [data]="item.summary ?? \'The review flagged a few high-priority issues that deserve attention before shipping.\'" mermaid></markdown>',
        "<p>{{ item.summary ?? 'The review flagged a few high-priority issues that deserve attention before shipping.' }}</p>"
    )

# Add AfterViewChecked import if not present
if "AfterViewChecked" not in component:
    component = component.replace(
        "import { Component, computed, inject, signal, OnDestroy, ViewChild, ElementRef, effect }",
        "import { Component, computed, inject, signal, OnDestroy, ViewChild, ElementRef, effect, AfterViewChecked }"
    )

# Remove MarkdownModule import if present
if "import { MarkdownModule }" in component:
    component = component.replace("import { MarkdownModule } from 'ngx-markdown';\n", "")
    component = component.replace(", MarkdownModule]", "]")

# Add the mermaid diagram section right after the summary-banner closing div
# Find the summary-tags closing div + summary-banner closing div
mermaid_section = '''
        @if (item.dependencyFlowDiagram) {
          <section class="dependency-flow-panel">
            <div class="dep-flow-heading">
              <span class="panel-kicker">DEPENDENCY & IMPACT FLOW</span>
              <h2>Impact Analysis</h2>
              <p>Visual diagram showing code dependencies and edge case impacts.</p>
            </div>
            <div class="mermaid-container" id="mermaid-diagram"></div>
          </section>
        }
'''

if "dependency-flow-panel" not in component:
    # Insert after the summary-banner section, before the dag-panel
    component = component.replace(
        "<section class=\"dag-panel\">",
        mermaid_section + "\n        <section class=\"dag-panel\">"
    )

# Add AfterViewChecked to the class
if "AfterViewChecked" in component and "ngAfterViewChecked" not in component:
    # Add implements
    if "implements OnDestroy" in component:
        component = component.replace(
            "implements OnDestroy",
            "implements OnDestroy, AfterViewChecked"
        )
    
    # Add the mermaid rendering signal and lifecycle method
    # Find the end of sendFeedback method area to add new methods
    mermaid_code = '''
  private mermaidRendered = signal(false);

  async ngAfterViewChecked(): Promise<void> {
    const item = this.review();
    if (!item?.dependencyFlowDiagram || this.mermaidRendered() || this.isLoading()) return;
    const container = document.getElementById('mermaid-diagram');
    if (!container) return;
    this.mermaidRendered.set(true);
    try {
      const mermaid = (window as any)['mermaid'];
      if (mermaid) {
        mermaid.initialize({ startOnLoad: false, theme: 'dark', themeVariables: { primaryColor: '#315efb', edgeLabelBackground: '#0d141e', nodeTextColor: '#e2e8f0', mainBkg: '#1a2332', nodeBorder: '#315efb' }});
        const { svg } = await mermaid.render('dep-flow-svg', item.dependencyFlowDiagram);
        container.innerHTML = svg;
      }
    } catch (e) {
      console.error('Mermaid render error:', e);
      container.innerHTML = '<pre style="color:#94a3b8;font-size:12px;white-space:pre-wrap;">' + item.dependencyFlowDiagram + '</pre>';
    }
  }
'''
    # Insert before the private autoScrollToActiveStage method
    component = component.replace(
        "  private autoScrollToActiveStage(",
        mermaid_code + "\n  private autoScrollToActiveStage("
    )

# Reset mermaidRendered when review changes (in the constructor/effect or route change)
if "this.mermaidRendered" in component and "mermaidRendered.set(false)" not in component:
    # Find effect that loads review and add reset
    if "this.service.loadById" in component:
        component = component.replace(
            "this.service.loadById(",
            "this.mermaidRendered.set(false);\n      this.service.loadById("
        )

with open(component_path, "w", encoding="utf-8") as f:
    f.write(component)
print("✓ Patched review.component.ts")


# =====================
# 3) Add CSS for the mermaid panel
# =====================
styles_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\styles.css"
with open(styles_path, "r", encoding="utf-8") as f:
    styles = f.read()

if "dependency-flow-panel" not in styles:
    mermaid_css = """

/* Dependency Flow Mermaid Panel */
.dependency-flow-panel {
  margin: 0 0 28px;
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--card);
}
.dep-flow-heading {
  margin-bottom: 18px;
}
.dep-flow-heading h2 {
  margin: 6px 0 4px;
  font-size: 18px;
  font-weight: 700;
  color: var(--ink);
}
.dep-flow-heading p {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
}
.mermaid-container {
  min-height: 120px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #0a1018;
  overflow-x: auto;
  display: flex;
  justify-content: center;
  align-items: center;
}
.mermaid-container svg {
  max-width: 100%;
  height: auto;
}
.mermaid-container pre {
  margin: 0;
  padding: 16px;
  overflow-x: auto;
}
"""
    styles += mermaid_css
    with open(styles_path, "w", encoding="utf-8") as f:
        f.write(styles)
    print("✓ Patched styles.css")
else:
    print("• styles.css already patched")


# =====================
# 4) Ensure mermaid script is in angular.json
# =====================
angular_json_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\angular.json"
with open(angular_json_path, "r", encoding="utf-8") as f:
    angular_json = f.read()

if "mermaid.min.js" not in angular_json:
    angular_json = angular_json.replace(
        '"scripts": []',
        '"scripts": ["node_modules/mermaid/dist/mermaid.min.js"]'
    )
    with open(angular_json_path, "w", encoding="utf-8") as f:
        f.write(angular_json)
    print("✓ Patched angular.json")
else:
    print("• angular.json already patched")


print("\n✅ All frontend patches applied!")
print("Restart the Angular dev server for changes to take effect.")

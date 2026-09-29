"""Fix the mermaid rendering in review.component.ts to use dynamic ES module import"""

component_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\review.component.ts"
with open(component_path, "r", encoding="utf-8") as f:
    component = f.read()

old_code = """  async ngAfterViewChecked(): Promise<void> {
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
  }"""

new_code = """  async ngAfterViewChecked(): Promise<void> {
    const item = this.review();
    if (!item?.dependencyFlowDiagram || this.mermaidRendered() || this.isLoading()) return;
    const container = document.getElementById('mermaid-diagram');
    if (!container) return;
    this.mermaidRendered.set(true);
    try {
      const mermaidModule = await import('mermaid');
      const mermaid = mermaidModule.default;
      mermaid.initialize({ startOnLoad: false, theme: 'dark', themeVariables: { primaryColor: '#315efb', edgeLabelBackground: '#0d141e', nodeTextColor: '#e2e8f0', mainBkg: '#1a2332', nodeBorder: '#315efb' }});
      const { svg } = await mermaid.render('dep-flow-svg', item.dependencyFlowDiagram);
      container.innerHTML = svg;
    } catch (e) {
      console.error('Mermaid render error:', e);
      container.innerHTML = '<pre style="color:#94a3b8;font-size:12px;white-space:pre-wrap;">' + item.dependencyFlowDiagram + '</pre>';
    }
  }"""

if old_code in component:
    component = component.replace(old_code, new_code)
    with open(component_path, "w", encoding="utf-8") as f:
        f.write(component)
    print("OK: Patched mermaid rendering to use dynamic import")
else:
    print("WARN: Could not find old code to replace")
    # Try to find the approximate location
    if "window as any" in component and "mermaid" in component:
        print("Found window.mermaid reference - trying alternative replacement")
        component = component.replace(
            "const mermaid = (window as any)['mermaid'];\r\n      if (mermaid) {\r\n        mermaid.initialize",
            "const mermaidModule = await import('mermaid');\r\n      const mermaid = mermaidModule.default;\r\n      {\r\n        mermaid.initialize"
        )
        with open(component_path, "w", encoding="utf-8") as f:
            f.write(component)
        print("OK: Applied alternative patch")
    else:
        print("ERROR: No mermaid code found at all")

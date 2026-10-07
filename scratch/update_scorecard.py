from pathlib import Path

target = Path(r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\scorecard\scorecard.component.ts")
content = target.read_text(encoding="utf-8")

if "MetricExplainerComponent" not in content:
    content = content.replace(
        "import { TrajectoryLogsComponent } from './trajectory-logs.component';",
        "import { TrajectoryLogsComponent } from './trajectory-logs.component';\nimport { MetricExplainerComponent } from './metric-explainer.component';"
    )
    content = content.replace(
        "JudgeCalibrationComponent\n  ]",
        "JudgeCalibrationComponent,\n    MetricExplainerComponent\n  ]"
    )
    content = content.replace(
        "<app-hero-stats [summary]=\"summary()\" />",
        "<app-hero-stats [summary]=\"summary()\" />\n      <app-metric-explainer />"
    )
    target.write_text(content, encoding="utf-8")
    print("scorecard.component.ts updated.")
else:
    print("Already updated.")

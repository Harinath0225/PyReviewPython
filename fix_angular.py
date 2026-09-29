import os

main_ts_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\main.ts"
review_ts_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\app\review.component.ts"
angular_json_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\angular.json"

# Update main.ts
with open(main_ts_path, "r", encoding="utf-8") as f:
    main_ts = f.read()

if "provideMarkdown" not in main_ts:
    main_ts = "import { provideMarkdown } from 'ngx-markdown';\nimport { SecurityContext } from '@angular/core';\n" + main_ts
    main_ts = main_ts.replace(
        "provideMarkdown({ sanitize: SecurityContext.NONE })",
        "provideMarkdown()"
    )
    main_ts = main_ts.replace(
        "providers: [provideRouter(routes), provideHttpClient()]",
        "providers: [provideRouter(routes), provideHttpClient(), provideMarkdown()]"
    )
    with open(main_ts_path, "w", encoding="utf-8") as f:
        f.write(main_ts)

# Update review.component.ts
with open(review_ts_path, "r", encoding="utf-8") as f:
    review_ts = f.read()

if "MarkdownModule" not in review_ts:
    review_ts = review_ts.replace(
        "import { SlicePipe, DatePipe } from '@angular/common';",
        "import { SlicePipe, DatePipe } from '@angular/common';\nimport { MarkdownModule } from 'ngx-markdown';"
    )
    review_ts = review_ts.replace(
        "imports: [RouterLink, SlicePipe, DatePipe]",
        "imports: [RouterLink, SlicePipe, DatePipe, MarkdownModule]"
    )
    review_ts = review_ts.replace(
        "<p>{{ item.summary ?? 'The review flagged a few high-priority issues that deserve attention before shipping.' }}</p>",
        "<markdown [data]=\"item.summary ?? 'The review flagged a few high-priority issues that deserve attention before shipping.'\" mermaid></markdown>"
    )
    with open(review_ts_path, "w", encoding="utf-8") as f:
        f.write(review_ts)

# Update angular.json to include mermaid script
with open(angular_json_path, "r", encoding="utf-8") as f:
    angular_json = f.read()

if "node_modules/mermaid/dist/mermaid.min.js" not in angular_json:
    angular_json = angular_json.replace(
        "\"scripts\": []",
        "\"scripts\": [\"node_modules/mermaid/dist/mermaid.min.js\"]"
    )
    if "\"scripts\": []" not in angular_json:
        # A more robust regex or logic could be used if necessary, but empty scripts is default for new projects.
        import re
        angular_json = re.sub(r'"scripts":\s*\[\s*\]', '"scripts": ["node_modules/mermaid/dist/mermaid.min.js"]', angular_json)
    
    with open(angular_json_path, "w", encoding="utf-8") as f:
        f.write(angular_json)

print("Angular frontend patched for Markdown and Mermaid support.")

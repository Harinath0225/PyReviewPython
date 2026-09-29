main_ts_path = r"C:\Coding_learning\pyengineer_ang\PyReviewAngular\src\main.ts"
with open(main_ts_path, "r", encoding="utf-8") as f:
    main_ts = f.read()

main_ts = main_ts.replace("provideMarkdown({ sanitize: SecurityContext.NONE })", "provideMarkdown()")

with open(main_ts_path, "w", encoding="utf-8") as f:
    f.write(main_ts)

# model_validation_summary — 对比表示例

由 `build_model_validation_summary.py` 生成；每模型优先 `run_tag`：`baseline_noncooperative/baseline_default`、`p1_coordinated/p1_ultimate_latest`、`p2_lifecycle/model_check_p2`。

| model_name | run_tag | objective_total | operation_cost | carbon_cost | ess_deg_cost | ev_deg_cost | recover_penalty_cost | grid_import_energy_kwh | ev_charge_energy_kwh | solver_status | solve_time_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_noncooperative | baseline_default | 46410.377967 | 46304.527348 | 0.0 | 12.54 | 93.31062 | null | 63760.2652 | 2164.0652 | null | null |
| p1_coordinated | p1_ultimate_latest | 39467.456089 | 38973.219277 | 0.0 | 369.390665 | 124.846147 | null | 65263.89581749999 | 2485.5180058225 | null | null |
| p2_lifecycle | model_check_p2 | 6663.978917832786 | 6582.791722524999 | 0.0 | 52.8694736625 | 28.317721645275036 | 5.473272600000001 | 9709.1983325 | 556.1052632625 | Optimal | 0.3207380000021658 |

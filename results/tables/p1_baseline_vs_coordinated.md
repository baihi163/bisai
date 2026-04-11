# 问题一：非协同基线 vs 协同调度 — 结果汇总

**时段**：两方案均为全周 **672** 时段（15 min）。

**operation_cost 口径**：与 `build_model_validation_summary._operation_cost_from_components` 一致（不含 ESS/EV 退化）。

**renewable_consumption_ratio**：`pv_used_energy_kwh / total_pv_energy_kwh`；基线 `pv_available_kw`×0.25、协同 `pv_upper_kw`×`delta_t_h` 积分。

**carbon_emission_kg**：`Σ P_grid_kw × grid_carbon_kg_per_kwh × Δt`（kg）；因子来自 `data/processed/carbon_profile.csv`（与优化中 carbon_price=0 独立）。

**import_weighted_carbon_intensity_kg_per_kwh**：`carbon_emission_kg / grid_import_energy_kwh`，即全周购电排放对购电电量的加权平均强度。**KPI 三联图第三子图**展示该强度（本算例协同略低于 baseline）；全周排放总量见列 `carbon_emission_kg` 或 `p1_grid_and_emission_compare` 图。

| scenario | total_pv_energy_kwh | pv_used_energy_kwh | pv_curtail_energy_kwh | renewable_consumption_ratio | operation_cost | grid_import_energy_kwh | carbon_emission_kg | import_weighted_carbon_intensity_kg_per_kwh |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_noncooperative | 22969.3 | 22969.3 | 0.0 | 1.0 | 46304.527348 | 63760.2652 | 42048.72426956522 | 0.659481640135418 |
| p1_coordinated | 22969.3 | 22969.3 | 0.0 | 1.0 | 38973.219277 | 65263.89581749999 | 42931.758762022495 | 0.6578178980009753 |

---

**碳排放口径复核（一至六）与中间量**：见 `p1_baseline_vs_coordinated_carbon_audit.md`、`p1_baseline_vs_coordinated_carbon_intermediates.csv`。

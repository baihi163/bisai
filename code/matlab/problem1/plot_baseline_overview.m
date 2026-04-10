function plot_baseline_overview(projectRoot, outDir)
%PLOT_BASELINE_OVERVIEW 全周总览：原生负荷、EV充电、光伏可用、购电功率。
%
% 输入:
%   projectRoot - 仓库根目录 (char/string)
%   outDir      - 输出 PNG 目录 (char/string)
%
% 数据: results/problem1_baseline/baseline_plot_data.csv（Python 导出）

    dataFile = fullfile(projectRoot, 'results', 'problem1_baseline', 'baseline_plot_data.csv');
    if ~isfile(dataFile)
        error('plot_baseline_overview:MissingFile', '未找到: %s', dataFile);
    end

    opts = detectImportOptions(dataFile, 'Encoding', 'UTF-8');
    T = readtable(dataFile, opts);

    t = datetime(T.timestamp, 'InputFormat', 'yyyy-MM-dd HH:mm:ss');
    if any(isnat(t))
        t = datetime(T.timestamp);
    end

    fig = figure('Position', [100 100 900 320]);
    yyaxis left
    hold on
    plot(t, T.native_load_kw, 'Color', [0.12 0.47 0.71], 'DisplayName', 'Native load (kW)');
    plot(t, T.ev_total_charge_kw, 'Color', [1.00 0.50 0.05], 'DisplayName', 'EV charge sum (kW)');
    plot(t, T.pv_available_kw, 'Color', [0.17 0.63 0.17], 'DisplayName', 'PV available (kW)');
    ylabel('Power (kW)')
    yyaxis right
    hold on
    plot(t, T.grid_import_kw, 'Color', [0.84 0.15 0.16], 'LineStyle', '-', 'DisplayName', 'Grid import (kW)');
    ylabel('Grid import (kW)')
    hold off
    xlabel('Time')
    title('Baseline: weekly overview (non-cooperative)')
    legend('Location', 'northwest', 'FontSize', 8)
    grid on

    outPath = fullfile(outDir, 'baseline_overview_matlab.png');
    print(fig, outPath, '-dpng', '-r300');
    close(fig);
end

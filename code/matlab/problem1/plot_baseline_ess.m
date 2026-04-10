function plot_baseline_ess(projectRoot, outDir)
%PLOT_BASELINE_ESS 储能运行：SOC(能量)、充/放电功率。
%
% 输入:
%   projectRoot - 仓库根目录
%   outDir      - 输出 PNG 目录
%
% 数据: results/problem1_baseline/baseline_plot_data.csv

    dataFile = fullfile(projectRoot, 'results', 'problem1_baseline', 'baseline_plot_data.csv');
    if ~isfile(dataFile)
        error('plot_baseline_ess:MissingFile', '未找到: %s', dataFile);
    end

    opts = detectImportOptions(dataFile, 'Encoding', 'UTF-8');
    T = readtable(dataFile, opts);

    t = datetime(T.timestamp, 'InputFormat', 'yyyy-MM-dd HH:mm:ss');
    if any(isnat(t))
        t = datetime(T.timestamp);
    end

    fig = figure('Position', [100 100 900 320]);
    yyaxis left
    plot(t, T.ess_energy_kwh, 'Color', [0.58 0.40 0.74], 'LineWidth', 1.4, 'DisplayName', 'ESS energy (kWh)');
    ylabel('Energy (kWh)')
    yyaxis right
    hold on
    plot(t, T.ess_charge_kw, 'Color', [0.17 0.63 0.17], 'LineWidth', 1.0, 'DisplayName', 'Charge (kW)');
    plot(t, T.ess_discharge_kw, 'Color', [0.74 0.74 0.13], 'LineWidth', 1.0, 'DisplayName', 'Discharge (kW)');
    hold off
    ylabel('Power (kW)')
    xlabel('Time')
    title('Baseline: stationary ESS state and power')
    legend('Location', 'northwest', 'FontSize', 8)
    grid on

    outPath = fullfile(outDir, 'baseline_ess_matlab.png');
    print(fig, outPath, '-dpng', '-r300');
    close(fig);
end

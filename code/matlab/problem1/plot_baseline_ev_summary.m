function plot_baseline_ev_summary(projectRoot, outDir)
%PLOT_BASELINE_EV_SUMMARY EV 离站需求满足情况汇总。
%
% 输入:
%   projectRoot - 仓库根目录
%   outDir      - 输出 PNG 目录
%
% 数据: results/problem1_baseline/baseline_ev_session_summary.csv

    dataFile = fullfile(projectRoot, 'results', 'problem1_baseline', 'baseline_ev_session_summary.csv');
    if ~isfile(dataFile)
        error('plot_baseline_ev_summary:MissingFile', '未找到: %s', dataFile);
    end

    opts = detectImportOptions(dataFile, 'Encoding', 'UTF-8');
    T = readtable(dataFile, opts);

    met = T.demand_met_flag;
    if iscell(met) || isstring(met)
        met = strcmpi(string(met), 'true') | strcmpi(string(met), '1');
    end
    nMet = sum(met);
    nNot = height(T) - nMet;

    req = T.required_energy_at_departure_kwh;
    fin = T.final_energy_at_departure_kwh;
    shortfall = max(0, req - fin);

    fig = figure('Position', [100 100 920 360]);

    subplot(1, 2, 1)
    b = bar([nMet, nNot]);
    b.FaceColor = 'flat';
    b.CData = [0.17 0.63 0.17; 0.84 0.15 0.16];
    set(gca, 'XTickLabel', {'Met', 'Not met'})
    ylabel('Number of sessions')
    title('EV departure energy requirement')
    grid on
    yMax = max([nMet + nNot, 1]);
    ylim([0 yMax * 1.15])
    text(1, nMet + 0.02 * yMax, sprintf('%d', nMet), 'HorizontalAlignment', 'center');
    text(2, nNot + 0.02 * yMax, sprintf('%d', nNot), 'HorizontalAlignment', 'center');

    subplot(1, 2, 2)
    histogram(shortfall, 20, 'FaceColor', [0.5 0.5 0.5], 'EdgeColor', 'w');
    xlabel('Shortfall (kWh), max(0, required - final)')
    ylabel('Count')
    title('Distribution of energy shortfall')
    grid on

    sgtitle(fig, 'Baseline: EV session summary (non-cooperative)', 'FontWeight', 'bold');

    outPath = fullfile(outDir, 'baseline_ev_summary_matlab.png');
    print(fig, outPath, '-dpng', '-r300');
    close(fig);
end

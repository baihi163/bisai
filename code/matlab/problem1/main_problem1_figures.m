%MAIN_PROBLEM1_FIGURES 问题1：读取 Python baseline 导出数据并生成论文级 PNG。
%
% 用法（在 MATLAB 中）:
%   cd('D:\数维杯比赛\code\matlab\problem1')
%   main_problem1_figures
%
% 依赖: 已运行 Python 导出 baseline_plot_data.csv 与 baseline_ev_session_summary.csv
% 输出: results/problem1_baseline/figures_matlab/*.png
%
% 不在此脚本中重复数值仿真，仅可视化。

function main_problem1_figures()
    thisDir = fileparts(mfilename('fullpath'));
    addpath(fullfile(thisDir, '..', 'utils'));
    addpath(fullfile(thisDir, '..', 'visualization'));

    projectRoot = get_project_root();
    outDir = fullfile(projectRoot, 'results', 'problem1_baseline', 'figures_matlab');
    if ~isfolder(outDir)
        mkdir(outDir);
    end

    set_plot_style();

    plot_baseline_overview(projectRoot, outDir);
    plot_baseline_ess(projectRoot, outDir);
    plot_baseline_ev_summary(projectRoot, outDir);

    fprintf('MATLAB figures saved under:\n  %s\n', outDir);
end

function set_plot_style()
%SET_PLOT_STYLE 统一论文级图形默认样式（线宽、字号、网格等）。
%
% 调用后新建 figure/axes 将继承这些默认值；建议在 main 中于绘图前调用一次。

    set(0, 'DefaultFigureColor', 'w');
    set(0, 'DefaultAxesFontSize', 10);
    set(0, 'DefaultAxesFontName', 'Times New Roman');
    set(0, 'DefaultAxesLineWidth', 0.8);
    set(0, 'DefaultLineLineWidth', 1.2);
    set(0, 'DefaultAxesGridAlpha', 0.3);
    set(0, 'DefaultAxesXGrid', 'on');
    set(0, 'DefaultAxesYGrid', 'on');
    set(0, 'DefaultAxesBox', 'on');
end

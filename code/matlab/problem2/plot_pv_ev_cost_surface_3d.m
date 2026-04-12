function plot_pv_ev_cost_surface_3d()
%PLOT_PV_EV_COST_SURFACE_3D  运行成本双扰动灵敏度 3D 曲面（可加近似，论文级出图）
%
% 与 Python 脚本 plot_problem2_pv_ev_sensitivity_3d_surface.py 一致：
%   - 读 results/sensitivity/sensitivity_analysis_summary.csv
%   - scenario = p2_unified_tornado, metric = operation_cost
%   - Z(EV,PV) = Δ%_EV(EV) + Δ%_PV(PV)，分段线性插值 + 端点斜率外推
%   - 曲率参数网、Y 轴 1.2→0.8、参考面 Z=10.2%、双色 colormap
%
% 输出（不覆盖 Python 图）：
%   results/problem2_lifecycle/figures/fig_pv_supply_3d_surface_matlab.png
%   results/problem2_lifecycle/figures/fig_pv_supply_3d_surface_matlab.pdf
%
% 用法：在 MATLAB 中 cd 到本文件所在目录，或已将 code/matlab 加入 path 后执行
%   plot_pv_ev_cost_surface_3d

    thisDir = fileparts(mfilename('fullpath'));
    addpath(fullfile(thisDir, '..', 'utils'));

    root = get_project_root();
    csvPath = fullfile(root, 'results', 'sensitivity', 'sensitivity_analysis_summary.csv');
    outDir = fullfile(root, 'results', 'problem2_lifecycle', 'figures');

    if ~isfile(csvPath)
        error('plot_pv_ev_cost_surface_3d:MissingFile', '未找到 CSV: %s', csvPath);
    end

    [pv_x, pv_p, ev_x, ev_p] = parse_tornado_curves(csvPath);

    n = 62;
    [X, Y] = curved_ev_pv_mesh(n);
    Z = interp_extrap_1d(ev_x, ev_p, X) + interp_extrap_1d(pv_x, pv_p, Y);

    zmin = min(Z(:));
    zmax = max(Z(:));
    zspan = zmax - zmin + eps;
    zmin_plot = zmin - 0.05 * zspan;
    z_thr = 10.2;
    z_top = max(zmax, z_thr) + 0.08 * zspan;

    close all;
    fig = figure('Color', 'w', 'Position', [40 40 1040 760], 'Renderer', 'opengl');
    ax = axes('Parent', fig);
    hold(ax, 'on');
    grid(ax, 'on');
    ax.GridAlpha = 0.35;
    ax.LineWidth = 0.6;
    ax.Box = 'on';
    view(ax, -126, 20);
    pbaspect(ax, [1 1 0.92]);

    nMap = 256;
    cLo = [172 214 236] / 255;
    cHi = [245 168 137] / 255;
    colormap(ax, linmap_two_color(nMap, cLo, cHi));
    caxis(ax, [zmin, zmax]);

    % 底面半透明填充（用 Z 着色）
    surf(ax, X, Y, zmin_plot + 0 * Z, Z, 'EdgeColor', 'none', 'FaceColor', 'interp', ...
        'FaceAlpha', 0.24, 'AmbientStrength', 0.85, 'DiffuseStrength', 0.4);

    % 参考平面 Z = 10.2%
    skip = max(2, floor(size(X, 1) / 14));
    idx = 1:skip:size(X, 1);
    idy = 1:skip:size(X, 2);
    mesh(ax, X(idx, idy), Y(idx, idy), z_thr + 0 * X(idx, idy), ...
        'EdgeColor', [0.72 0.72 0.72], 'FaceColor', 'none', 'LineWidth', 0.45);

    % 主曲面：无棱线 + Gouraud，便于论文排版
    surf(ax, X, Y, Z, Z, 'EdgeColor', 'none', 'FaceColor', 'interp', ...
        'FaceLighting', 'gouraud', 'AmbientStrength', 0.52, 'DiffuseStrength', 0.78, ...
        'SpecularStrength', 0.18, 'SpecularExponent', 14);

    shading(ax, 'interp');

    lightangle(ax, -128, 42);
    lighting(ax, 'gouraud');
    material(ax, [0.48 0.82 0.22 10 0.32]);

    xlim(ax, [0.8 1.2]);
    ylim(ax, [0.8 1.2]);
    set(ax, 'YDir', 'reverse');
    zlim(ax, [zmin_plot, z_top]);

    xlabel(ax, '柔性供电(EV)可用性/功率缩放系数', 'FontWeight', 'bold', 'Interpreter', 'none');
    ylabel(ax, '光伏出力缩放系数', 'FontWeight', 'bold', 'Interpreter', 'none');
    zlabel(ax, '运行成本相对变化率 / %', 'FontWeight', 'bold', 'Interpreter', 'none');

    zticks(ax, linspace(zmin_plot, z_top, 6));
    try
        ztickformat(ax, '%.2f%%');
    catch
        zv = zticks(ax);
        zticklabels(ax, arrayfun(@(v) sprintf('%.2f%%', v), zv, 'UniformOutput', false));
    end

    relCsv = strrep(csvPath, [root filesep], '');
    title(ax, {'光伏与 EV 缩放双扰动下的运行成本变化率（可加近似）'; ...
        sprintf('数据：%s · p2_unified_tornado', relCsv)}, ...
        'FontWeight', 'bold', 'FontSize', 11, 'Interpreter', 'none');

    cb = colorbar(ax);
    cb.Label.String = '成本变化率 / %';
    cb.Label.FontWeight = 'bold';

    set_fonts_cjk(fig);

    if ~isfolder(outDir)
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'fig_pv_supply_3d_surface_matlab.png');
    outPdf = fullfile(outDir, 'fig_pv_supply_3d_surface_matlab.pdf');

    try
        exportgraphics(fig, outPng, 'Resolution', 600, 'BackgroundColor', 'white');
    catch ME
        warning('exportgraphics(PNG) 回退 print：%s', ME.message);
        print(fig, outPng, '-dpng', '-r600');
    end
    try
        % 3D 曲面用 painters 常失败，用 OpenGL 嵌入位图式 PDF
        set(fig, 'Renderer', 'opengl');
        print(fig, outPdf, '-dpdf');
    catch ME2
        try
            exportgraphics(fig, outPdf, 'BackgroundColor', 'white');
        catch
            warning('PDF 导出失败：%s', ME2.message);
        end
    end

    fprintf('已生成: %s\n', outPng);
    fprintf('已生成: %s\n', outPdf);
end

%% -------------------------------------------------------------------------
function set_fonts_cjk(fig)
    % 避免 listfonts（极慢）；Windows 默认雅黑，其余用系统无衬线
    if ispc
        fn = 'Microsoft YaHei';
    elseif ismac
        fn = 'PingFang SC';
    else
        fn = 'Noto Sans CJK SC';
    end
    set(findall(fig, 'Type', 'axes'), 'FontName', fn);
    set(findall(fig, 'Type', 'colorbar'), 'FontName', fn);
    set(findall(fig, 'Type', 'text'), 'FontName', fn);
end

function [pv_x, pv_p, ev_x, ev_p] = parse_tornado_curves(csvPath)
    opts = detectImportOptions(csvPath, 'TextType', 'string');
    if isprop(opts, 'Encoding')
        opts.Encoding = 'UTF-8';
    end
    tbl = readtable(csvPath, opts);

    scen = string(tbl.scenario);
    met = string(tbl.metric);
    mask = scen == "p2_unified_tornado" & met == "operation_cost";
    sub = tbl(mask, :);

    pv_x = [];
    pv_p = [];
    ev_x = [];
    ev_p = [];

    for i = 1:height(sub)
        rel = sub.relative_change_pct(i);
        if isnan(rel)
            continue;
        end
        par = char(sub.parameter(i));
        tok = regexp(par, 'PV=([\d.]+)', 'tokens', 'once');
        if ~isempty(tok)
            pv_x(end + 1) = str2double(tok{1}); %#ok<AGROW>
            pv_p(end + 1) = rel; %#ok<AGROW>
        end
        tok = regexp(par, 'EV=([\d.]+)', 'tokens', 'once');
        if ~isempty(tok)
            ev_x(end + 1) = str2double(tok{1}); %#ok<AGROW>
            ev_p(end + 1) = rel; %#ok<AGROW>
        end
    end

    if numel(pv_x) < 2 || numel(ev_x) < 2
        error('plot_pv_ev_cost_surface_3d:Parse', '未解析到足够的 PV/EV 扰动行。');
    end

    [pv_x, ord] = sort([pv_x(:); 1.0]);
    pv_p = [pv_p(:); 0.0];
    pv_p = pv_p(ord);

    [ev_x, ord] = sort([ev_x(:); 1.0]);
    ev_p = [ev_p(:); 0.0];
    ev_p = ev_p(ord);
end

function yq = interp_extrap_1d(xn, yn, xq)
    xn = xn(:);
    yn = yn(:);
    [xn, ii] = sort(xn);
    yn = yn(ii);
    yq = interp1(xn, yn, xq, 'linear', 'extrap');
end

function cmap = linmap_two_color(n, cLo, cHi)
    t = linspace(0, 1, n)';
    cmap = (1 - t) .* cLo + t .* cHi;
end

function [X, Y] = curved_ev_pv_mesh(n)
    lo = 0.8;
    hi = 1.2;
    span = hi - lo;
    u = linspace(0, 1, n);
    v = linspace(0, 1, n);
    ue = u .^ 0.84;
    ve = v .^ 0.84;
    [Ue2, Ve2] = meshgrid(ue, ve);
    bend = 0.052;
    X = lo + span * (Ue2 + bend * sin(pi * Ve2) .* Ue2 .* (1 - Ue2));
    Y = lo + span * (Ve2 + bend * sin(pi * Ue2) .* Ve2 .* (1 - Ve2));
    X = min(max(X, lo), hi);
    Y = min(max(Y, lo), hi);
end

function plot_sensitivity_2d_response_surface()
%PLOT_SENSITIVITY_2D_RESPONSE_SURFACE
% 读取 results/sensitivity/sensitivity_analysis_summary.csv，仅在存在「两独立因子 × 完整笛卡尔积」
% 且 relative_change_pct 有效时，绘制论文风格三维响应曲面（发散配色 + 底面投影 + 采样点）。
% 不使用对角寿命权重扫描；不根据单边龙卷风伪造双因子曲面。
%
% 依赖：code/matlab/utils/get_project_root.m

    thisDir = fileparts(mfilename('fullpath'));
    addpath(fullfile(thisDir, '..', 'utils'));
    root = get_project_root();

    csvPath = fullfile(root, 'results', 'sensitivity', 'sensitivity_analysis_summary.csv');
    if ~isfile(csvPath)
        error('未找到文件: %s', csvPath);
    end

    opts = detectImportOptions(csvPath, 'TextType', 'string');
    if isprop(opts, 'Encoding')
        opts.Encoding = 'UTF-8';
    end
    T = readtable(csvPath, opts);
    need = {'parameter', 'scenario', 'metric', 'relative_change_pct'};
    for k = 1:numel(need)
        if ~ismember(need{k}, T.Properties.VariableNames)
            error('灵敏度表缺少列: %s', need{k});
        end
    end

    G = discover_two_factor_grid(T);
    if ~G.found
        error('%s', G.msg);
    end

    nq = 96;
    xq = linspace(min(G.U), max(G.U), nq);
    yq = linspace(min(G.V), max(G.V), nq);
    [Xq, Yq] = meshgrid(xq, yq);
    [X0, Y0] = meshgrid(G.U, G.V);

    outDir = fullfile(root, 'results', 'figures', 'problem2');
    if ~isfolder(outDir)
        mkdir(outDir);
    end

    set(0, 'DefaultFigureToolbar', 'none');

    for mi = 1:numel(G.metricList)
        mname = G.metricList{mi};
        Zm = G.Zmats.(matlab.lang.makeValidName(['m_' mname]));
        Zq = interp2(X0, Y0, Zm, Xq, Yq, 'spline');

        zq = Zq(~isnan(Zq(:)));
        if isempty(zq)
            error('指标 %s 插值无效（全 NaN）。', mname);
        end
        zlim = max(abs(zq));

        fig = figure('Color', 'w', 'Position', [60 60 1000 780], 'MenuBar', 'none', 'ToolBar', 'none', 'Renderer', 'opengl');
        ax = axes('Parent', fig, 'Projection', 'perspective');
        hold(ax, 'on');

        zSpan = max(Zq(:), [], 'omitnan') - min(Zq(:), [], 'omitnan') + eps;
        zFloor = min(Zq(:), [], 'omitnan') - 0.07 * zSpan;

        surf(ax, Xq, Yq, zFloor + 0 * Zq, Zq, 'EdgeColor', 'none', 'FaceColor', 'interp', ...
            'FaceAlpha', 0.32, 'AmbientStrength', 0.85, 'DiffuseStrength', 0.35);

        hs = surf(ax, Xq, Yq, Zq, Zq, 'EdgeColor', 'none', 'FaceColor', 'interp', ...
            'FaceLighting', 'gouraud', 'DiffuseStrength', 0.82, 'AmbientStrength', 0.4, ...
            'SpecularStrength', 0.09, 'SpecularExponent', 14);
        shading(ax, 'interp');

        colormap(ax, diverging_cmap(256));
        caxis(ax, [-zlim, zlim]);

        % z=0 参考平面（相对变化率基准），半透明浅灰、无边线
        surf(ax, Xq, Yq, 0 * Xq, 'FaceColor', [0.86 0.86 0.88], 'FaceAlpha', 0.22, ...
            'EdgeColor', 'none', 'AmbientStrength', 1);

        xm = G.xmats.(matlab.lang.makeValidName(['m_' mname]));
        ym = G.ymats.(matlab.lang.makeValidName(['m_' mname]));
        zm = G.zraw.(matlab.lang.makeValidName(['m_' mname]));
        scatter3(ax, xm(:), ym(:), zm(:), 44, [0.12 0.12 0.12], 'filled', ...
            'MarkerEdgeColor', [1 1 1], 'LineWidth', 0.35);

        xlabel(ax, G.xlabel, 'Interpreter', 'none', 'FontWeight', 'bold', 'FontSize', 11);
        ylabel(ax, G.ylabel, 'Interpreter', 'none', 'FontWeight', 'bold', 'FontSize', 11);
        zlabel(ax, '相对变化率 / %', 'Interpreter', 'none', 'FontWeight', 'bold', 'FontSize', 11);
        title(ax, sprintf('双因子灵敏度响应面（%s）', mname), 'Interpreter', 'none', 'FontWeight', 'bold', 'FontSize', 12);

        cb = colorbar(ax);
        cb.Label.String = '相对变化率 / %';
        cb.Label.FontWeight = 'bold';

        lighting(ax, 'gouraud');
        lightangle(ax, -46, 36);
        material(ax, [0.48 0.86 0.2 10 0.33]);
        view(ax, -128, 22);
        grid(ax, 'on');
        ax.GridAlpha = 0.3;
        axis(ax, 'tight');
        try
            ax.Toolbar.Visible = 'off';
        catch
        end

        stem = sprintf('sensitivity_response_surface_%s', strrep(mname, '.', '_'));
        try
            exportgraphics(fig, fullfile(outDir, [stem '.png']), 'Resolution', 600, 'BackgroundColor', 'white');
        catch
            print(fig, fullfile(outDir, [stem '.png']), '-dpng', '-r600');
        end
        try
            print(fig, fullfile(outDir, [stem '.svg']), '-dsvg');
        catch
            try
                exportgraphics(fig, fullfile(outDir, [stem '.svg']), 'BackgroundColor', 'white');
            catch
            end
        end
        close(fig);
    end
end

function cm = diverging_cmap(n)
    t = linspace(-1, 1, n)';
    cm = zeros(n, 3);
    lo = [0.02 0.26 0.70];
    mid = [1 1 1];
    hi = [0.74 0.05 0.12];
    for i = 1:n
        ti = t(i);
        if ti <= 0
            a = 1 + ti;
            cm(i, :) = (1 - a) * lo + a * mid;
        else
            a = ti;
            cm(i, :) = (1 - a) * mid + a * hi;
        end
    end
end

function G = discover_two_factor_grid(T)
    G = struct('found', false, 'msg', '', 'U', [], 'V', [], 'metricList', {{}}, ...
        'Zmats', struct(), 'xmats', struct(), 'ymats', struct(), 'zraw', struct(), ...
        'xlabel', '', 'ylabel', '');

    scen = string(T.scenario);
    met = string(T.metric);
    par = string(T.parameter);
    rel = double(T.relative_change_pct);

    scenarios = unique(scen, 'stable');
    for si = 1:numel(scenarios)
        s = scenarios(si);
        idx0 = scen == s & met == "operation_cost" & ~isnan(rel);
        if nnz(idx0) < 4
            continue;
        end
        p0 = par(idx0);
        r0 = rel(idx0);
        [xa, ya, xlb, ylb, ok] = parse_two_factors_column(p0);
        if ~ok
            continue;
        end
        [U, V, ~, okGrid] = build_full_grid_matrix(xa, ya, r0);
        if ~okGrid
            continue;
        end

        mList = {};
        Zall = struct();
        Xall = struct();
        Yall = struct();
        Zraw = struct();

        mets = unique(met(scen == s), 'stable');
        for mj = 1:numel(mets)
            mname = char(mets(mj));
            idxm = scen == s & met == mets(mj) & ~isnan(rel);
            if nnz(idxm) < 1
                continue;
            end
            pm = par(idxm);
            rm = rel(idxm);
            [xm, ym, ~, ~, ok2] = parse_two_factors_column(pm);
            if ~ok2
                continue;
            end
            [Um, Vm, Zm, okG2] = build_full_grid_matrix(xm, ym, rm);
            if ~okG2 || numel(Um) ~= numel(U) || numel(Vm) ~= numel(V)
                continue;
            end
            if max(abs(Um(:) - U(:))) > 1e-6 || max(abs(Vm(:) - V(:))) > 1e-6
                continue;
            end
            mList{end+1} = mname; %#ok<AGROW>
            fn = matlab.lang.makeValidName(['m_' mname]);
            Zall.(fn) = Zm;
            [X0, Y0] = meshgrid(U, V);
            Xall.(fn) = X0;
            Yall.(fn) = Y0;
            Zraw.(fn) = Zm;
        end

        if isempty(mList)
            continue;
        end

        G.found = true;
        G.U = U;
        G.V = V;
        G.metricList = mList;
        G.Zmats = Zall;
        G.xmats = Xall;
        G.ymats = Yall;
        G.zraw = Zraw;
        G.xlabel = xlb;
        G.ylabel = ylb;
        return;
    end

    G.msg = sprintf([ ...
        '未在灵敏度结果中找到完整的二维扰动网格。\n', ...
        '已检查: results/sensitivity/sensitivity_analysis_summary.csv\n', ...
        '要求：同一 scenario 下，parameter 每行能解析出两个独立数值因子，且 (因子1×因子2) 笛卡尔积上', ...
        '每个组合恰有一条 operation_cost 相对变化率记录；并据此匹配其它指标的相同参数组合。\n', ...
        '当前仓库多为单边龙卷风（PV 或 EV 单独一行），不满足上述条件，无法绘制真实双因子响应面。']);
end

function [xa, ya, xlb, ylb, ok] = parse_two_factors_column(pcol)
    n = numel(pcol);
    xa = nan(n, 1);
    ya = nan(n, 1);
    xlb = '扰动因子 X';
    ylb = '扰动因子 Y';
    ok = false;

    dual = true;
    for i = 1:n
        s = char(pcol(i));
        t = regexp(s, 'PV=([\d.]+).*EV=([\d.]+)', 'tokens', 'once');
        if isempty(t)
            dual = false;
            break;
        end
        xa(i) = str2double(t{1});
        ya(i) = str2double(t{2});
    end
    if dual && all(isfinite(xa)) && all(isfinite(ya))
        xlb = '光伏出力缩放系数';
        ylb = 'EV 可用性 / 功率缩放系数';
        ok = true;
        return;
    end

    xa = nan(n, 1);
    ya = nan(n, 1);
    dual2 = true;
    for i = 1:n
        s = char(pcol(i));
        t = regexp(s, 'ev_power_scale=([\d.]+).*pv_scale=([\d.]+)', 'tokens', 'once');
        if ~isempty(t)
            xa(i) = str2double(t{1});
            ya(i) = str2double(t{2});
        else
            t2 = regexp(s, 'pv_scale=([\d.]+).*ev_power_scale=([\d.]+)', 'tokens', 'once');
            if isempty(t2)
                dual2 = false;
                break;
            end
            xa(i) = str2double(t2{1});
            ya(i) = str2double(t2{2});
        end
    end
    if dual2 && all(isfinite(xa)) && all(isfinite(ya))
        xlb = 'EV 功率缩放系数';
        ylb = '光伏出力缩放系数';
        ok = true;
        return;
    end

    xa = nan(n, 1);
    ya = nan(n, 1);
    ok3 = true;
    for i = 1:n
        s = char(pcol(i));
        a = regexp(s, '(?i)flex[^\d]*([\d.]+)', 'tokens', 'once');
        b = regexp(s, '(?i)ESS[^\d]*([\d.]+)', 'tokens', 'once');
        if isempty(a) || isempty(b)
            ok3 = false;
            break;
        end
        xa(i) = str2double(a{1});
        ya(i) = str2double(b{1});
    end
    if ok3 && all(isfinite(xa)) && all(isfinite(ya))
        xlb = '建筑柔性缩放系数';
        ylb = 'ESS 容量缩放系数';
        ok = true;
    end
end

function [U, V, Zmat, ok] = build_full_grid_matrix(xa, ya, zrel)
    ok = false;
    U = sort(unique(xa(:)));
    V = sort(unique(ya(:)));
    nu = numel(U);
    nv = numel(V);
    expN = nu * nv;
    if numel(xa) ~= expN
        U = [];
        V = [];
        Zmat = [];
        return;
    end
    keys = (xa(:) * 1e9) + ya(:);
    if numel(unique(keys)) ~= numel(xa)
        U = [];
        V = [];
        Zmat = [];
        return;
    end
    got = containers.Map('KeyType', 'char', 'ValueType', 'double');
    for i = 1:numel(xa)
        k = sprintf('%.12g,%.12g', xa(i), ya(i));
        got(k) = zrel(i);
    end
    Zmat = nan(nv, nu);
    filled = 0;
    for j = 1:nu
        for ii = 1:nv
            k = sprintf('%.12g,%.12g', U(j), V(ii));
            if isKey(got, k)
                Zmat(ii, j) = got(k);
                filled = filled + 1;
            end
        end
    end
    if filled == expN
        ok = true;
    else
        U = [];
        V = [];
        Zmat = [];
    end
end

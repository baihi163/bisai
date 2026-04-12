function plot_weight_sensitivity_response_surface()
%PLOT_WEIGHT_SENSITIVITY_RESPONSE_SURFACE
% 基于 problem2 寿命权重扫描汇总 CSV 自动绘制三维响应图。
% 若为完整二维网格/散点，则绘制插值曲面；
% 若数据近似共线（如 ess_deg_weight ≈ ev_deg_weight 的对角扫描），
% 则绘制“带状三维响应曲面”，避免虚构完整二维面。

    root = get_project_root_local();

    csvPath = pick_weight_scan_csv(root);
    if isempty(csvPath)
        error('未找到可用的 weight_scan_summary*.csv。');
    end

    T = readtable(csvPath, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    req = {'ess_deg_weight', 'ev_deg_weight', 'operation_cost'};
    for k = 1:numel(req)
        if ~ismember(req{k}, T.Properties.VariableNames)
            error('缺少列: %s（文件: %s）', req{k}, csvPath);
        end
    end

    x = double(T.ess_deg_weight(:));
    y = double(T.ev_deg_weight(:));
    z = double(T.operation_cost(:));

    valid = ~(isnan(x) | isnan(y) | isnan(z));
    x = x(valid);
    y = y(valid);
    z = z(valid);

    if numel(x) < 2
        error('有效数据点不足，无法绘图。');
    end

    [x, ord] = sort(x);
    y = y(ord);
    z = z(ord);

    isDiagonal = max(abs(x - y)) < 1e-8 * (max(abs(x)) + 1);

    fig = figure('Color', 'w', 'Position', [100 80 920 700], 'Renderer', 'opengl');
    set(fig, 'MenuBar', 'none', 'ToolBar', 'none');

    ax = axes('Parent', fig);
    hold(ax, 'on');
    try
        ax.Toolbar.Visible = 'off';
    catch
    end

    zThr = median(z, 'omitnan');

    if isDiagonal
        % =========================================================
        % 对角扫描：画“带状曲面”
        % =========================================================
        xq = linspace(min(x), max(x), 240);
        zq = interp1(x, z, xq, 'pchip', 'extrap');
        yq = xq;

        bandWidth = 0.04 * (max(xq) - min(xq) + eps);
        s = linspace(-bandWidth, bandWidth, 28);

        [S, Xq] = meshgrid(s, xq);
        Yq = Xq + S;
        Zq = repmat(zq(:), 1, numel(s));

        surf(ax, Xq, Yq, Zq, Zq, ...
            'EdgeColor', 'none', ...
            'FaceColor', 'interp', ...
            'FaceAlpha', 0.98);

        scatter3(ax, x, y, z, 28, 'k', 'filled', ...
            'MarkerFaceAlpha', 0.58, ...
            'MarkerEdgeAlpha', 0.58);

        [Xp, Yp] = meshgrid(linspace(min(Xq(:)), max(Xq(:)), 80), ...
                            linspace(min(Yq(:)), max(Yq(:)), 80));
        Zp = zThr * ones(size(Xp));
        surf(ax, Xp, Yp, Zp, ...
            'FaceColor', [0.95 0.95 0.95], ...
            'FaceAlpha', 0.10, ...
            'EdgeColor', [0.75 0.75 0.75], ...
            'LineWidth', 0.35);

        title(ax, '统一寿命权重扫描的三维响应带', ...
            'FontSize', 13, 'FontWeight', 'bold');

    else
        % =========================================================
        % 真正二维数据：插值曲面
        % =========================================================
        xq = linspace(min(x), max(x), 120);
        yq = linspace(min(y), max(y), 120);
        [Xq, Yq] = meshgrid(xq, yq);

        try
            F = scatteredInterpolant(x, y, z, 'natural', 'none');
            Zq = F(Xq, Yq);
        catch
            try
                F = scatteredInterpolant(x, y, z, 'linear', 'none');
                Zq = F(Xq, Yq);
            catch
                Zq = griddata(x, y, z, Xq, Yq, 'linear');
            end
        end

        if all(isnan(Zq(:)))
            error('二维插值失败：当前数据可能不支撑二维曲面。');
        end

        surf(ax, Xq, Yq, Zq, Zq, ...
            'EdgeColor', 'none', ...
            'FaceColor', 'interp', ...
            'FaceAlpha', 0.98);

        scatter3(ax, x, y, z, 22, 'k', 'filled', ...
            'MarkerFaceAlpha', 0.55, ...
            'MarkerEdgeAlpha', 0.55);

        Zp = zThr * ones(size(Xq));
        surf(ax, Xq, Yq, Zp, ...
            'FaceColor', [0.95 0.95 0.95], ...
            'FaceAlpha', 0.10, ...
            'EdgeColor', [0.75 0.75 0.75], ...
            'LineWidth', 0.35);

        title(ax, '寿命权重灵敏度响应曲面', ...
            'FontSize', 13, 'FontWeight', 'bold');
    end

    shading(ax, 'interp');
    colormap(ax, turbo(256));
    cb = colorbar(ax);
    cb.Label.String = '运行费用 / 元';
    cb.FontSize = 10;

    xlabel(ax, 'ESS寿命权重', 'FontSize', 12);
    ylabel(ax, 'EV寿命权重', 'FontSize', 12);
    zlabel(ax, '运行费用 / 元', 'FontSize', 12);

    view(ax, 38, 24);
    grid(ax, 'on');
    box(ax, 'on');
    axis(ax, 'tight');
    ax.GridAlpha = 0.22;
    ax.LineWidth = 0.9;
    ax.FontSize = 11;
    ax.Projection = 'perspective';

    camlight(ax, 'headlight');
    lighting(ax, 'gouraud');

    outDir = fullfile(root, 'results', 'figures', 'problem2');
    if ~isfolder(outDir)
        mkdir(outDir);
    end

    outPng = fullfile(outDir, 'weight_response_surface_operation_cost.png');
    outSvg = fullfile(outDir, 'weight_response_surface_operation_cost.svg');

    try
        exportgraphics(fig, outPng, 'Resolution', 500, 'BackgroundColor', 'white');
    catch
        print(fig, outPng, '-dpng', '-r500');
    end

    try
        exportgraphics(fig, outSvg, 'BackgroundColor', 'white');
    catch
        try
            print(fig, outSvg, '-dsvg');
        catch
        end
    end

    fprintf('图已导出：\n%s\n%s\n', outPng, outSvg);
end

function p = pick_weight_scan_csv(root)
% 自动寻找最合适的 weight_scan_summary*.csv

    p = '';
    cand = {};

    scans = fullfile(root, 'results', 'problem2_lifecycle', 'scans');
    if isfolder(scans)
        d1 = dir(fullfile(scans, '**', 'weight_scan_summary.csv'));
        for k = 1:numel(d1)
            cand{end+1} = fullfile(d1(k).folder, d1(k).name); %#ok<AGROW>
        end
    end

    tabs = fullfile(root, 'results', 'problem2_lifecycle', 'tables');
    if isfolder(tabs)
        d2 = dir(fullfile(tabs, 'weight_scan_summary*.csv'));
        for k = 1:numel(d2)
            cand{end+1} = fullfile(d2(k).folder, d2(k).name); %#ok<AGROW>
        end
    end

    if isempty(cand)
        return;
    end

    best = '';
    bestN = -1;

    for k = 1:numel(cand)
        try
            T = readtable(cand{k}, 'TextType', 'string');
            vn = T.Properties.VariableNames;
            if ~all(ismember({'ess_deg_weight', 'ev_deg_weight', 'operation_cost'}, vn))
                continue;
            end
            n = height(T);
            if n > bestN
                bestN = n;
                best = cand{k};
            end
        catch
        end
    end

    p = best;
end

function root = get_project_root_local()
% 从当前 m 文件位置向上搜索，找到包含 results/ 或 code/ 的项目根目录

    here = fileparts(mfilename('fullpath'));
    root = here;

    for k = 1:8
        hasResults = isfolder(fullfile(root, 'results'));
        hasCode = isfolder(fullfile(root, 'code'));
        if hasResults || hasCode
            return;
        end
        parent = fileparts(root);
        if strcmp(parent, root)
            break;
        end
        root = parent;
    end

    % 如果没找到，就退回当前目录
    root = here;
end

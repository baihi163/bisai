function root = get_project_root()
%GET_PROJECT_ROOT 返回竞赛项目仓库根目录（含 results、data、code 等）。
%
% 本文件位于 code/matlab/utils/，向上三级为仓库根。

    utilsDir = fileparts(mfilename('fullpath'));
    matlabDir = fileparts(utilsDir);
    codeDir = fileparts(matlabDir);
    root = fileparts(codeDir);

    if ~isfolder(fullfile(root, 'results')) || ~isfolder(fullfile(root, 'code'))
        error('get_project_root:PathMismatch', ...
            '推断的根目录无效: %s（缺少 results 或 code）', root);
    end
end

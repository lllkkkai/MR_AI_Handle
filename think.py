import os
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dotenv import load_dotenv

from mr import analyze_with_deepseek

def split_log_entries(log_text: str) -> List[str]:
    """
    将包含多个错误日志的文本分割为单独的错误条目列表

    注意：
    1. 有些错误可能同时包含多种格式的开头行
    2. 需要避免将同一个错误分割成多个
    """
    # 找到所有可能表示新错误开始的行
    # 1. 包含 ERROR 的行，且不是堆栈跟踪中的行（堆栈跟踪行通常以空格开头）
    lines = log_text.split('\n')
    error_start_indices = []

    for i, line in enumerate(lines):
        # 检查是否是一个新的错误开始
        if (('[' in line and 'ERROR' in line) or  # [yl-xxx]ERROR: 格式
            (re.match(r'^\d{4}-\d{2}-\d{2}', line) and 'ERROR' in line)):  # 时间戳开头格式

            # 检查这一行是否是堆栈跟踪的一部分（堆栈跟踪行通常以空格开头）
            if not line.startswith(' '):
                # 避免将同一错误的不同格式头部分割为多个条目
                # 如果前一行同样包含ERROR但没有堆栈信息，则跳过当前行
                if i > 0 and 'ERROR' in lines[i-1] and not lines[i-1].startswith(' ') and 'at ' not in lines[i-1]:
                    # 检查两行内容是否相似（可能是同一错误的不同格式）
                    prev_content = re.sub(r'^\[.*?\]|^\d{4}-\d{2}-\d{2}.*?ERROR\s+', '', lines[i-1])
                    curr_content = re.sub(r'^\[.*?\]|^\d{4}-\d{2}-\d{2}.*?ERROR\s+', '', line)

                    if prev_content.strip() == curr_content.strip() or prev_content in curr_content or curr_content in prev_content:
                        continue

                error_start_indices.append(i)

    # 如果没有找到错误开始行，返回整个日志作为一个条目
    if not error_start_indices:
        return [log_text.strip()]

    # 根据错误开始行的索引分割日志
    error_entries = []
    for i in range(len(error_start_indices)):
        start_idx = error_start_indices[i]
        # 计算结束索引（下一个错误的开始或文件末尾）
        end_idx = error_start_indices[i+1] if i < len(error_start_indices) - 1 else len(lines)

        # 构建完整的错误条目
        error_entry = '\n'.join(lines[start_idx:end_idx]).strip()
        error_entries.append(error_entry)

    return error_entries

def extract_project_from_log(log_text: str) -> Optional[str]:
    """
    从日志中提取项目名称
    例如: 从 "[yl-web]ERROR:" 或 "yl-service" 中提取出项目名称
    """
    # 匹配如 [yl-web] 或 [yl-service] 的模式
    bracket_pattern = re.compile(r'\[(yl-[a-z-]+)\]')
    bracket_match = bracket_pattern.search(log_text)
    if bracket_match:
        return bracket_match.group(1)

    # 匹配如 yl-web_ 或 yl-service_ 的模式 (针对sign参数中的项目名)
    sign_pattern = re.compile(r'sign["\']:\s*["\']v1_(yl-[a-z-]+)_')
    sign_match = sign_pattern.search(log_text)
    if sign_match:
        return sign_match.group(1)

    # 匹配日志中可能出现的项目名称
    for project_name in PROJECT_PATHS.keys():
        if project_name in log_text:
            return project_name

    return None

def parse_stack_trace(log_text: str, limit: int = 3) -> List[Tuple[str, str, str]]:
    # 修正正则，只获取类名、文件名、行号
    pattern = re.compile(r'at ([\w\.]+)\.\w+\((\w+\.java):(\d+)\)')
    matches = pattern.findall(log_text)
    return matches[:limit]

def class_path_to_file_path(class_path: str, base_path: Path) -> Path:
    # 将类路径转为代码文件路径
    return base_path / (class_path.replace('.', '/') + '.java')

def read_file_lines(file_path: Path) -> List[str]:
    # 读取文件内容为行列表
    try:
        with file_path.open('r', encoding='utf-8') as f:
            return f.readlines()
    except FileNotFoundError:
        return []

def extract_code_context(file_path: Path, line_number: int, radius: int = 20) -> str:
    # 提取代码上下文（前后各 radius 行）
    lines = read_file_lines(file_path)
    if not lines:
        return f"[文件不存在] {file_path}"
    start = max(0, line_number - radius - 1)
    end = min(len(lines), line_number + radius)
    return ''.join(lines[start:end])

# 项目名到根目录的映射
PROJECT_PATHS = {
    'yl-admin': Path(os.environ.get('YL_ADMIN_PATH')),
    'yl-order-web': Path(os.environ.get('YL_ORDER_WEB_PATH')),
    'yl-order-service': Path(os.environ.get('YL_ORDER_SERVICE_PATH')),
    'yl-service': Path(os.environ.get('YL_SERVICE_PATH')),
    'yl-web': Path(os.environ.get('YL_WEB_PATH')),
    'yl-user-service': Path(os.environ.get('YL_USER_SERVICE_PATH')),
    'yl-user-web': Path(os.environ.get('YL_USER_WEB_PATH')),
}

# 类路径前缀到项目名的映射（需根据实际包名调整）
PREFIX_TO_PROJECT = {
    'com.wkb.yl.admin': 'yl-admin',
    'com.wkb.yl.order.web': 'yl-order-web',
    'com.wkb.yl.order.service': 'yl-order-service',
    'com.wkb.yl.service': 'yl-service',
    'com.wkb.yl.web': 'yl-web',
    'com.wkb.yl.user.service': 'yl-user-service',
    'com.wkb.yl.user.web': 'yl-user-web',
}

def get_project_base_path(class_path: str, log_text: str = None) -> Path:
    """
    基于类路径和日志内容确定项目的基础路径
    优先使用日志中的项目名称，如果无法从日志中获取则使用类路径前缀
    """
    # 先尝试从日志中提取项目名称
    if log_text:
        project_name = extract_project_from_log(log_text)
        if project_name and project_name in PROJECT_PATHS:
            return PROJECT_PATHS[project_name]

    # 如果无法从日志中提取，则使用类路径前缀
    for prefix, project in PREFIX_TO_PROJECT.items():
        if class_path.startswith(prefix):
            return PROJECT_PATHS[project]

    # 默认返回第一个项目路径
    return next(iter(PROJECT_PATHS.values()))

def build_prompt_for_entry(log_entry: str) -> str:
    """
    为单个错误日志条目构建提示
    """
    try:
        stack_entries = parse_stack_trace(log_entry)
        if not stack_entries:
            return f"[无法解析堆栈跟踪] 错误日志: {log_entry[:100]}..."

        prompt_parts = []

        # 先尝试从日志中提取项目名称
        project_name = extract_project_from_log(log_entry)

        for idx, (class_path, file_name, line_str) in enumerate(stack_entries, start=1):
            # 传递日志文本到get_project_base_path函数
            base_code_path = get_project_base_path(class_path, log_entry)
            file_path = class_path_to_file_path(class_path, base_code_path)
            try:
                code_context = extract_code_context(file_path, int(line_str))
            except Exception as e:
                code_context = f"[无法提取代码上下文: {str(e)}]"

            prompt_parts.append(
                f"\n【第{idx}处异常位置】\n类名: {class_path}\n文件: {file_name}\n行号: {line_str}\n"
                f"相关代码上下文:\n{code_context}"
            )

        return '\n'.join(prompt_parts)
    except Exception as e:
        return f"[构建错误提示失败] 错误信息: {str(e)}"

def build_prompt(log_text: str) -> str:
    """
    根据完整日志文本构建分析提示
    支持处理包含多个错误的日志文件
    """
    log_entries = split_log_entries(log_text)

    prompt_parts = []
    prompt_parts.append(
        "你是一位资深 Java 开发专家。请根据以下错误日志和相关代码，直接给出可应用于原始代码的补丁（unified diff 格式），不要输出任何解释或说明。"
        "\n补丁应能修复问题，且仅包含必要的修改。"
    )

    if len(log_entries) > 1:
        prompt_parts.append(f"\n【检测到 {len(log_entries)} 个错误日志】")

    for i, entry in enumerate(log_entries, start=1):
        # 为每个错误条目添加头部标记
        if len(log_entries) > 1:
            prompt_parts.append(f"\n\n===== 错误 #{i} =====")

        # 添加原始日志
        prompt_parts.append(f"\n【错误日志】\n{entry.strip()}")

        # 提取项目名称
        project_name = extract_project_from_log(entry)
        if project_name:
            prompt_parts.append(f"\n【检测到项目】: {project_name}")

        # 为当前错误条目构建详细分析
        entry_analysis = build_prompt_for_entry(entry)
        prompt_parts.append(entry_analysis)

    prompt_parts.append(
        "\n请只输出补丁内容（unified diff），不要输出任何解释或说明。"
        "\n补丁示例：\n"
        "--- 原文件路径\n+++ 修改后文件路径\n@@ -原始行号,行数 +修改后行号,行数 @@\n-原始代码\n+修改后代码"
    )

    return '\n'.join(prompt_parts)

def save_diff_to_txt(review_result: dict, file_path: str):
    """
    从 deepseek 返回结果中提取 diff 内容并保存到 txt 文件
    """
    diff_content = review_result.get('choices', [{}])[0].get('message', {}).get('content', '')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(diff_content)

load_dotenv()
with open(os.environ['EXAMPLE_LOG_PATH'], 'r', encoding='utf-8') as f:
    example_log = f.read()
prompt = build_prompt(example_log)
# prompt = parse_stack_trace(example_log)
print(prompt)
# review_result = analyze_with_deepseek(prompt)
# save_diff_to_txt(review_result, 'patch.txt')
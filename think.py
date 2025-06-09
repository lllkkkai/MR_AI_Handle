import os
import re
from pathlib import Path
from typing import List, Tuple
from dotenv import load_dotenv

from mr import analyze_with_deepseek


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

def build_prompt(log_text: str, base_code_path: Path) -> str:
    try:
        stack_entries = parse_stack_trace(log_text)
        prompt_parts = []
        prompt_parts.append("你是一位经验丰富的 Java 开发专家，请根据以下错误日志和相关代码，分析问题原因并给出修改建议。")
        prompt_parts.append("\n【错误日志全文】\n" + log_text.strip())

        for idx, (class_path, file_name, line_str) in enumerate(stack_entries, start=1):
            file_path = class_path_to_file_path(class_path, base_code_path)
            try:
                code_context = extract_code_context(file_path, int(line_str))
            except Exception as e:
                code_context = f"[无法提取代码上下文: {str(e)}]"
            prompt_parts.append(
                f"\n【第{idx}处异常位置】\n类名: {class_path}\n文件: {file_name}\n行号: {line_str}\n"
                f"相关代码上下文:\n{code_context}"
            )

        prompt_parts.append("\n请基于以上信息，分析问题并提供可行的代码修改建议。")
        return '\n'.join(prompt_parts)
    except Exception as e:
        return f"[构建提示失败] 错误信息: {str(e)}"


load_dotenv()
with open(os.environ['EXAMPLE_LOG_PATH'], 'r', encoding='utf-8') as f:
    example_log = f.read()
base_code_dir = Path(os.environ.get('BASE_CODE_DIR'))
prompt = build_prompt(example_log, base_code_dir)
# prompt = parse_stack_trace(example_log)
print(prompt)
review_result = analyze_with_deepseek(prompt)
print(review_result)
import requests
from dotenv import load_dotenv
import os

load_dotenv()

GITLAB_URL = os.getenv("GITLAB_URL")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEESEEK_API_KEY")
GITLAB_PROJECT_ID = os.getenv("GITLAB_PROJECT_ID")
MR_IID = os.getenv("MR_IID")

# === 获取 MR diff 内容 ===
def fetch_mr_diff():
    url = f"{GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/merge_requests/{MR_IID}/changes"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

# === 构造分析 prompt ===
def build_prompt(changes):
    prompt = (
        "你是一个资深 Java 工程师，请帮我审查以下 Merge Request 中的代码变更，"
        "专注指出潜在问题、潜在BUG、安全风险和改进建议。请将所有问题分为两类：\n"
        "1. 一定要修改（严重影响程序运行或明显错误）\n"
        "2. 建议修改（如可读性、结构优化等非紧急问题）\n\n"
        "请根据以下评分细则，对整体代码质量进行打分（总分10分），并给出简短说明：\n\n"
        "评分细则：\n"
        "1. 代码正确性（最高4分）：\n"
        "   - 4分：无语法或逻辑错误，异常处理完善\n"
        "   - 3分：轻微问题，不影响功能\n"
        "   - 2分：中等问题，部分功能可能异常\n"
        "   - 1分：严重问题，易崩溃或错误\n"
        "   - 0分：代码不可用\n\n"
        "2. 安全性（最高3分）：\n"
        "   - 3分：无安全隐患\n"
        "   - 2分：存在轻微安全风险\n"
        "   - 1分：明显安全风险\n"
        "   - 0分：严重安全漏洞\n\n"
        "3. 可读性（最高2分）：\n"
        "   - 2分：结构清晰，命名合理，注释充分\n"
        "   - 1分：一般，注释或命名不足\n"
        "   - 0分：混乱，缺注释\n\n"
        "4. 维护性（最高1分）：\n"
        "   - 1分：结构合理，重复少，易扩展\n"
        "   - 0分：耦合高，重复多，难扩展\n\n"
        "请最后输出评分表格和总结。\n\n"
    )

    for change in changes["changes"]:
        file = change["new_path"]
        diff = change["diff"]
        prompt += f"\n文件：{file}\n变更内容：\n{diff}\n"

    return prompt

# === 调用 DeepSeek API ===
def analyze_with_deepseek(prompt):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    resp = requests.post(url, headers=headers, json=data)
    resp.raise_for_status()
    return resp.json()

def generate_markdown_report(mr_info, analysis_result):
    md = f"# Merge Request 审查报告\n\n"
    md += f"## MR标题: {mr_info['title']}\n\n"
    md += f"## MR描述:\n{mr_info.get('description', '无')}\n\n"
    md += f"## 代码变更摘要:\n"
    for change in mr_info['changes']:
        md += f"- 文件: {change['new_path']}\n"
        md += f"  - 变更类型: {change['new_file'] and '新增' or '修改'}\n"
    md += "\n"
    choices = analysis_result.get('choices')
    if choices and len(choices) > 0:
        content = choices[0].get('message', {}).get('content', '无分析结果')
    else:
        content = '无分析结果'
    md += content + "\n"
    return md

def save_markdown_file(content, filename="mr_review_report.md"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"报告已保存到 {filename}")

# === 主函数 ===
if __name__ == "__main__":
    mr_data = fetch_mr_diff()
    prompt = build_prompt(mr_data)
    review_result = analyze_with_deepseek(prompt)
    md_content = generate_markdown_report(mr_data, review_result)
    save_markdown_file(md_content)
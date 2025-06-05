from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from datetime import datetime, timedelta

def is_error_mail(subject: str) -> bool:
    keywords = ["Exception", "NullPointerException", "error", "x"]
    return any(kw.lower() in subject.lower() for kw in keywords)

# 昨天的日期，用于筛选邮件
yesterday = (datetime.today() - timedelta(days=1)).strftime("%m月%d日")

# 启动浏览器
driver = webdriver.Chrome()
driver.get("https://qiye.aliyun.com/")
input("请手动登录阿里邮箱后按回车继续...")

time.sleep(5)
email_rows = driver.find_elements(By.CLASS_NAME, "mail-list-item")

for row in email_rows:
    try:
        date_text = row.find_element(By.CLASS_NAME, "mail-list-date").text
        if yesterday not in date_text:
            continue

        subject = row.find_element(By.CLASS_NAME, "mail-list-subject").text
        if is_error_mail(subject):
            row.click()
            time.sleep(2)
            content = driver.find_element(By.CLASS_NAME, "mail-detail-content").text
            with open("latest-error.txt", "w", encoding="utf-8") as f:
                f.write(content)
            print("找到报错邮件，内容已保存")
            break
    except Exception as e:
        print("跳过异常邮件行：", e)
        continue

driver.quit()

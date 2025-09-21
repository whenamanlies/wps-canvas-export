# 🎓 WPS Canvas Export

A lightweight Python script for listing and reporting your Canvas LMS courses using Observer credentials.  
Authenticate with the Canvas API, iterate over observable students, and optionally email yourself a summary via Gmail SMTP.

---

## 🚀 Features

- Connects to Canvas via the REST API  
- Lists all courses available to your token
- Creates comprehensive text content for the email body
- Includes all current information for all observable students:
  - Summary statistics per student
  - Course grades overview with status indicators
  - Overdue assignments list
  - Upcoming assignments (next 7 days)
- Optional email delivery of the course summary using Gmail
  - Summary in email body
  - Attaches all individual student HTML reports (mobile friendly)

---

## 🛠️ Requirements

- Python 3.x
- A Canvas API token with “Read” access to courses  
- (Optional) A Gmail account with an App Password for SMTP

---

## 📦 Use

Author has it setup as via GitHub Action (see .github/workflows/run-script.yml) where required environment variables (CANVAS_API_URL, CANVAS_API_TOKEN, GMAIL_USER, GMAIL_APP_PASSWORD) are fetched from Repository secrets (Settings → Secrets and variables → Actions)

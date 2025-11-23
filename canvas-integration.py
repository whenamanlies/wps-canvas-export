import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from canvasapi import Canvas

# ─── Configuration ──────────────────────────────────────────────────────────
CANVAS_API_URL   = os.environ.get("CANVAS_API_URL", "")
CANVAS_API_KEY  = os.environ.get("CANVAS_API_KEY", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

if not CANVAS_API_URL: raise ValueError("CANVAS_API_URL environment variable is required i.e. https://myschool.instructure.com")
if not CANVAS_API_KEY: raise ValueError("CANVAS_API_KEY environment variable is required")

# ─── Email Configuration ────────────────────────────────────────────────────
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "true").lower() == "true"

# ─── Logging Configuration ──────────────────────────────────────────────────
# Disable logging in GitHub Actions to prevent personal data from appearing in logs
LOGGING_ENABLED = os.environ.get("LOGGING_ENABLED", "false").lower() == "true"

def log(*args, **kwargs):
    """Wrapper for print() that respects LOGGING_ENABLED flag"""
    if LOGGING_ENABLED:
        print(*args, **kwargs)

print(f"LOGGING_ENABLED = {LOGGING_ENABLED}")

COURSE_ALIASES = {
    "AP Precalculus": "AP Precalculus",
    "Human Centered: Fundamentals of Human Centered Design": "Human Centered Design",
    "Individuals & Societies 9/10A: Global History Through Graphic Novels: The Modern Age": "I&S 9/10A",
    "Language & Literature 9/10A: Machines, Aliens, and the Human Condition": "Lang & Lit 9/10A",
    "Performing Arts: High School Band 1": "High School Band",
    "Pre-DP Chemistry": "Pre-DP Chemistry",
    "Spanish 4": "Spanish 4",
    "Programming: AP Computer Science A": "AP CS A",
    "Individuals & Societies 8: A Thematic History of the United States": "I&S 8",
    "Language & Literature 8: Voices of Change: Identity, Belonging, and Power": "Lang & Lit 8",
    "Integrated High School Mathematics I": "High School Math I",
    "Physical & Health Education: Musical Choreography": "PE: Musical Choreo",
    "Science 8: Introduction to High School Sciences": "Science 8",
    "Spanish 2": "Spanish 2",
    "Visual Arts: Photography 1": "Photography 1",
    "Performing Arts: Acting 1": "Acting 1"
}


# ─── Slicing Functions ───────────────────────────────────────────────────

def full_overview(student_id):
    s = students_data[student_id]
    log(f"\n{'='*70}")
    log(f"📚 Full Overview for {s['name']}")
    log(f"{'='*70}")
    for cid, cdata in s["courses"].items():
        score = cdata["current_score"]
        final = cdata["final_score"]
        score_str = f"{score::<6.1f}% / {final:>5.1f}%" if score is not None else "No grade"
        course_display = COURSE_ALIASES.get(cdata["name"], cdata["name"])
        log(f"{score_str:<18} {course_display}")
        for a in sorted(cdata["assignments"], key=lambda x: (x["due_at"] or now_utc)):
            due_str = a["due_at"].strftime("%Y-%m-%d %I:%M %p") if a["due_at"] else "No due date"
            log(f"    {a['score']} / {a['points_possible']} → {due_str} • {a['name']} ({a['grade']})")

def overdue_overview(student_id):
    s = students_data[student_id]
    log(f"\n⚠️ Overdue / Missing for {s['name']}:")
    for cid, cdata in s["courses"].items():
        for a in cdata["assignments"]:
            if a["due_at"] and a["due_at"] < now_utc.astimezone(pacific):
                # Skip if submitted or has score
                if a["score"] is not None or a["submitted_at"]:
                    continue
                if a["missing"]:
                    due_str = a["due_at"].strftime("%Y-%m-%d %I:%M %p")
                    course_display = COURSE_ALIASES.get(cdata["name"], cdata["name"])
                    log(f"    {due_str} • {course_display} → {a['name']} → {a['html_url']}")

def upcoming_week(student_id):
    s = students_data[student_id]
    log(f"\n📅 Upcoming Week for {s['name']}:")
    one_week = now_utc + timedelta(days=7)
    for cid, cdata in s["courses"].items():
        for a in cdata["assignments"]:
            if a["due_at"] and now_utc.astimezone(pacific) <= a["due_at"] <= one_week.astimezone(pacific):
                due_str = a["due_at"].strftime("%Y-%m-%d %I:%M %p")
                course_display = COURSE_ALIASES.get(cdata["name"], cdata["name"])
                log(f"    {due_str} • {course_display} → {a['name']}")


# ─── HTML Export Functions ──────────────────────────────────────────────────

def get_assignment_status_class(assignment, current_time):
    """Determine CSS class for assignment based on status"""
    classes = []

    # Check if assignment is overdue (past due date and not submitted)
    if assignment["due_at"] and assignment["due_at"] < current_time:
        if assignment["score"] is None and not assignment["submitted_at"]:
            classes.append("overdue")

    # Check if grading is overdue (submitted but not graded after reasonable time)
    elif assignment["submitted_at"] and assignment["score"] is None:
        # Consider grading overdue if submitted more than 3 days ago
        submitted_time = assignment["submitted_at"]
        if isinstance(submitted_time, str):
            try:
                submitted_time = datetime.fromisoformat(submitted_time.rstrip("Z")).replace(tzinfo=timezone.utc).astimezone(pacific)
            except:
                submitted_time = None

        if submitted_time and (current_time - submitted_time).days >= 3:
            classes.append("grading-overdue")
        elif submitted_time:
            classes.append("awaiting-grade")

    # Check if upcoming assignment with no submission (purple highlight)
    elif assignment["due_at"] and assignment["due_at"] > current_time:
        if assignment["score"] is None and not assignment["submitted_at"]:
            classes.append("upcoming-no-submission")

    # Check if missing score (only for assignments that are due and not submitted)
    elif assignment["score"] is None and assignment["due_at"] and assignment["due_at"] < current_time:
        if not assignment["submitted_at"]:
            classes.append("missing-score")

    # Check if score is below 80%
    if assignment["score"] is not None and assignment["points_possible"]:
        try:
            percentage = (float(assignment["score"]) / float(assignment["points_possible"])) * 100
            if percentage < 80:
                classes.append("low-score")
        except (ValueError, ZeroDivisionError):
            pass

    return " ".join(classes)

def get_course_status_class(course_data):
    """Determine CSS class for course based on current score"""
    classes = []

    current_score = course_data.get("current_score")
    if current_score is not None:
        try:
            if float(current_score) < 80:
                classes.append("low-grade")
        except (ValueError, TypeError):
            pass
    else:
        classes.append("no-grade")

    return " ".join(classes)

def generate_html_report(student_data_subset=None):
    """Generate comprehensive HTML report for all students or a subset"""
    current_time = now_utc.astimezone(pacific)
    timestamp = current_time.strftime("%Y-%m-%d %I:%M %p")

    # Use provided subset or all students
    data_to_process = student_data_subset or students_data

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canvas Academic Report - {timestamp}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}

        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}

        .timestamp {{
            margin-top: 10px;
            opacity: 0.9;
            font-size: 1.1em;
        }}

        .students-container {{
            padding: 30px;
        }}

        .student-section {{
            margin-bottom: 30px;
            border: 1px solid #ddd;
            border-radius: 12px;
            overflow: hidden;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .student-toggle {{
            display: none;
        }}

        .student-header {{
            padding: 20px 25px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s ease;
            user-select: none;
        }}

        .student-header:hover {{
            background: linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%);
        }}

        .student-name {{
            font-size: 1.8em;
            font-weight: 600;
            margin: 0;
        }}

        .student-expand-icon {{
            font-size: 1.5em;
            transition: transform 0.3s ease;
        }}

        .student-toggle:checked + .student-header .student-expand-icon {{
            transform: rotate(180deg);
        }}

        .student-content {{
            display: none;
            padding: 25px;
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }}

        .student-toggle:checked + .student-header + .student-content {{
            display: block;
            max-height: 5000px;
        }}



        .course {{
            margin-bottom: 20px;
            border: 1px solid #ddd;
            border-radius: 8px;
            overflow: hidden;
            background: white;
        }}

        .course-toggle {{
            display: none;
        }}

        .course-header {{
            padding: 15px 20px;
            background: #f8f9fa;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background-color 0.3s ease;
            user-select: none;
        }}

        .course-header:hover {{
            background: #e9ecef;
        }}

        .course-header.low-grade {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
        }}

        .course-header.no-grade {{
            background: #f8d7da;
            border-left: 4px solid #dc3545;
        }}

        .course-title {{
            font-size: 1.2em;
            font-weight: 600;
            color: #333;
            text-decoration: none;
        }}

        .course-title:hover {{
            color: #667eea;
        }}

        .course-grades {{
            display: flex;
            gap: 15px;
            align-items: center;
        }}

        .grade {{
            padding: 5px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9em;
        }}

        .current-grade {{
            background: #d4edda;
            color: #155724;
        }}

        .current-grade.low-grade {{
            background: #f8d7da;
            color: #721c24;
        }}

        .final-grade {{
            background: #cce5ff;
            color: #004085;
        }}

        .no-grade {{
            background: #f8d7da;
            color: #721c24;
        }}

        .expand-icon {{
            font-size: 1.2em;
            transition: transform 0.3s ease;
        }}

        .course-toggle:checked + .course-header .expand-icon {{
            transform: rotate(180deg);
        }}

        .course-content {{
            display: none;
            padding: 0;
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }}

        .course-toggle:checked + .course-header + .course-content {{
            display: block;
            max-height: 2000px;
        }}

        .assignments-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .assignments-table th {{
            background: #f8f9fa;
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
        }}

        .assignments-table td {{
            padding: 12px 15px;
            border-bottom: 1px solid #dee2e6;
            vertical-align: top;
        }}

        .assignment-name {{
            color: #333;
            text-decoration: none;
            font-weight: 500;
        }}

        .assignment-name:hover {{
            color: #667eea;
            text-decoration: underline;
        }}

        .overdue {{
            background-color: #f8d7da !important;
        }}

        .grading-overdue {{
            background-color: #ffeaa7 !important;
            border-left: 4px solid #fdcb6e !important;
        }}

        .awaiting-grade {{
            background-color: #e8f4fd !important;
            border-left: 4px solid #74b9ff !important;
        }}

        .upcoming-no-submission {{
            background-color: #f3e5f5 !important;
            border-left: 4px solid #9c27b0 !important;
        }}

        .missing-score {{
            background-color: #fff3cd !important;
        }}

        .low-score {{
            background-color: #ffe6e6 !important;
        }}

        .score {{
            font-weight: 600;
        }}

        .score.low-score {{
            color: #dc3545;
        }}

        .due-date {{
            white-space: nowrap;
        }}

        .due-date.overdue {{
            color: #dc3545;
            font-weight: 600;
        }}

        .summary-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .stat-number {{
            font-size: 2em;
            font-weight: 700;
            color: #667eea;
            margin-bottom: 5px;
        }}

        .stat-label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .alert {{
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}

        .alert.warning {{
            background: #fff3cd;
            border-color: #ffeaa7;
            color: #856404;
        }}

        .alert.success {{
            background: #d4edda;
            border-color: #c3e6cb;
            color: #155724;
        }}

        .instructions {{
            margin-bottom: 20px;
            padding: 15px;
            background: #e8f4fd;
            border-radius: 8px;
            border-left: 4px solid #74b9ff;
            font-size: 14px;
            color: #004085;
        }}

        @media (max-width: 768px) {{
            .students-container {{
                padding: 15px;
            }}

            .student-header {{
                padding: 15px 20px;
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }}

            .student-name {{
                font-size: 1.5em;
            }}

            .course-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }}

            .assignments-table {{
                font-size: 0.9em;
                display: block;
                overflow-x: auto;
                white-space: nowrap;
            }}

            .assignments-table th,
            .assignments-table td {{
                padding: 8px 10px;
                min-width: 120px;
            }}

            .summary-stats {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 Canvas Academic Report</h1>
            <div class="timestamp">Generated on {timestamp}</div>
        </div>

        <div class="students-container">"""

    # Generate expandable sections for each student
    for i, (student_id, student_data) in enumerate(data_to_process.items()):

        # Calculate statistics
        total_courses = len(student_data['courses'])
        total_assignments = sum(len(course['assignments']) for course in student_data['courses'].values())
        overdue_count = 0
        missing_scores = 0
        grading_overdue_count = 0
        awaiting_grade_count = 0
        upcoming_no_submission_count = 0

        for course_data in student_data['courses'].values():
            for assignment in course_data['assignments']:
                # Count overdue assignments (past due and not submitted)
                if assignment["due_at"] and assignment["due_at"] < current_time:
                    if assignment["score"] is None and not assignment["submitted_at"]:
                        overdue_count += 1

                # Count grading overdue (submitted but not graded after 3+ days)
                elif assignment["submitted_at"] and assignment["score"] is None:
                    submitted_time = assignment["submitted_at"]
                    if isinstance(submitted_time, str):
                        try:
                            submitted_time = datetime.fromisoformat(submitted_time.rstrip("Z")).replace(tzinfo=timezone.utc).astimezone(pacific)
                        except:
                            submitted_time = None

                    if submitted_time and (current_time - submitted_time).days >= 3:
                        grading_overdue_count += 1
                    elif submitted_time:
                        awaiting_grade_count += 1

                # Count upcoming assignments with no submission
                elif assignment["due_at"] and assignment["due_at"] > current_time:
                    if assignment["score"] is None and not assignment["submitted_at"]:
                        upcoming_no_submission_count += 1

                # Count missing scores (only for overdue assignments that weren't submitted)
                elif assignment["score"] is None and assignment["due_at"] and assignment["due_at"] < current_time:
                    if not assignment["submitted_at"]:
                        missing_scores += 1

        # Default to first student expanded
        checked = "checked" if i == 0 else ""

        html_content += f"""
        <div class="student-section">
            <input type="checkbox" id="student-{student_id}" class="student-toggle" {checked}>
            <label for="student-{student_id}" class="student-header">
                <h2 class="student-name">{student_data['name']}</h2>
                <span class="student-expand-icon">▼</span>
            </label>
            <div class="student-content">

            <div class="summary-stats">
                <div class="stat-card">
                    <div class="stat-number">{total_courses}</div>
                    <div class="stat-label">Active Courses</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{total_assignments}</div>
                    <div class="stat-label">Total Assignments</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{overdue_count}</div>
                    <div class="stat-label">Overdue Items</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{grading_overdue_count}</div>
                    <div class="stat-label">Grading Overdue</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{awaiting_grade_count}</div>
                    <div class="stat-label">Awaiting Grade</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{upcoming_no_submission_count}</div>
                    <div class="stat-label">Upcoming (No Submission)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{missing_scores}</div>
                    <div class="stat-label">Missing Scores</div>
                </div>
            </div>"""

        # Add alerts for issues
        if overdue_count > 0:
            html_content += f"""
            <div class="alert">
                <strong>⚠️ Attention Required:</strong> {overdue_count} overdue assignment(s) need immediate attention.
            </div>"""

        if grading_overdue_count > 0:
            html_content += f"""
            <div class="alert warning">
                <strong>📚 Grading Delayed:</strong> {grading_overdue_count} assignment(s) submitted but not graded for 3+ days.
            </div>"""

        if awaiting_grade_count > 3:
            html_content += f"""
            <div class="alert warning">
                <strong>📝 Note:</strong> {awaiting_grade_count} assignments are awaiting grading.
            </div>"""

        if upcoming_no_submission_count > 0:
            html_content += f"""
            <div class="alert warning">
                <strong>🔮 Upcoming Deadlines:</strong> {upcoming_no_submission_count} assignment(s) due soon with no submission yet.
            </div>"""

        if overdue_count == 0 and grading_overdue_count == 0 and missing_scores <= 1:
            html_content += """
            <div class="alert success">
                <strong>✅ Great Job:</strong> All assignments are up to date!
            </div>"""

        # Add instructions for mobile users
        html_content += """
            <div class="instructions">
                💡 <strong>Tip:</strong> Click on any course header to expand/collapse and view assignments
            </div>"""

        # Generate courses
        for course_id, course_data in student_data['courses'].items():
            course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])
            course_status_class = get_course_status_class(course_data)

            current_score = course_data.get("current_score")
            final_score = course_data.get("final_score")

            current_grade_display = f"{current_score:.1f}%" if current_score is not None else "No grade"
            final_grade_display = f"{final_score:.1f}%" if final_score is not None else "0.0%"

            current_grade_class = "current-grade"
            if current_score is not None and current_score < 80:
                current_grade_class += " low-grade"
            elif current_score is None:
                current_grade_class = "no-grade"

            html_content += f"""
            <div class="course">
                <input type="checkbox" id="course-{student_id}-{course_id}" class="course-toggle">
                <label for="course-{student_id}-{course_id}" class="course-header {course_status_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <a href="{course_data.get('html_url', '#')}" class="course-title" target="_blank" onclick="event.stopPropagation()">
                            {course_display}
                        </a>
                        <div class="course-grades">
                            <span class="{current_grade_class} grade">Current: {current_grade_display}</span>
                            <span class="final-grade grade">Final: {final_grade_display}</span>
                            <span class="expand-icon">▼</span>
                        </div>
                    </div>
                </label>
                <div class="course-content">
                    <table class="assignments-table">
                        <thead>
                            <tr>
                                <th>Assignment</th>
                                <th>Score</th>
                                <th>Possible</th>
                                <th>Due Date</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>"""

            # Sort assignments by due date
            sorted_assignments = sorted(course_data["assignments"], key=lambda x: (x["due_at"] or datetime.max.replace(tzinfo=pacific)))

            for assignment in sorted_assignments:
                status_class = get_assignment_status_class(assignment, current_time)

                due_str = assignment["due_at"].strftime("%Y-%m-%d %I:%M %p") if assignment["due_at"] else "No due date"
                due_class = "due-date"
                if assignment["due_at"] and assignment["due_at"] < current_time and assignment["score"] is None:
                    due_class += " overdue"

                score_display = assignment["score"] if assignment["score"] is not None else "—"
                score_class = "score"
                if assignment["score"] is not None and assignment["points_possible"]:
                    try:
                        percentage = (float(assignment["score"]) / float(assignment["points_possible"])) * 100
                        if percentage < 80:
                            score_class += " low-score"
                    except (ValueError, ZeroDivisionError):
                        pass

                points_possible = assignment["points_possible"] if assignment["points_possible"] is not None else "—"

                # Enhanced status determination
                if assignment["score"] is not None:
                    status = f"Graded ({assignment['grade']})"
                elif assignment["submitted_at"]:
                    submitted_time = assignment["submitted_at"]
                    if isinstance(submitted_time, str):
                        try:
                            submitted_time = datetime.fromisoformat(submitted_time.rstrip("Z")).replace(tzinfo=timezone.utc).astimezone(pacific)
                        except:
                            submitted_time = None

                    if submitted_time and (current_time - submitted_time).days >= 3:
                        status = "Grading Overdue"
                    else:
                        status = "Awaiting Grade"
                elif assignment["missing"]:
                    status = "Missing"
                else:
                    status = "Not submitted"

                assignment_url = assignment.get("html_url", "#")

                html_content += f"""
                            <tr class="{status_class}">
                                <td><a href="{assignment_url}" class="assignment-name" target="_blank">{assignment['name']}</a></td>
                                <td class="{score_class}">{score_display}</td>
                                <td>{points_possible}</td>
                                <td class="{due_class}">{due_str}</td>
                                <td>{status}</td>
                            </tr>"""

            html_content += """
                        </tbody>
                    </table>
                </div>
            </div>"""

        html_content += """
            </div>
        </div>"""

    # Close the students container
    html_content += """
        </div>
    </div>
</body>
</html>"""

    return html_content

def save_html_report():
    """Generate and save HTML report to file"""
    html_content = generate_html_report()

    # Generate filename with timestamp
    timestamp = now_utc.astimezone(pacific).strftime("%Y%m%d_%H%M%S")
    filename = f"canvas.html"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        log(f"\n📄 HTML report saved as: {filename}")
        log(f"   Open this file in your browser to view the interactive report.")
        return filename
    except Exception as e:
        log(f"\n❌ Error saving HTML report: {e}")
        return None

def generate_action_items_text_report(student_id, student_data):
    """Generate a text report for missing and poorly scored assignments for a student"""
    current_time = now_utc.astimezone(pacific)
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append(f"ACTION ITEMS REPORT - {student_data['name'].upper()}")
    lines.append(f"Generated: {current_time.strftime('%Y-%m-%d %I:%M %p')}")
    lines.append("=" * 70)
    lines.append("")

    # Collect missing assignments (overdue with missing or zero score)
    missing_by_course = {}
    maybe_redo_by_course = {}

    for course_id, course_data in student_data['courses'].items():
        course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])

        for assignment in course_data['assignments']:
            # Missing assignments: overdue AND (missing flag OR score is 0 OR no score and not submitted)
            # Filter out assignments without valid points_possible
            if assignment["due_at"] and assignment["due_at"] < current_time:
                # Skip if no valid points_possible
                if not assignment["points_possible"] or float(assignment["points_possible"]) == 0:
                    continue

                is_missing = False

                # Check if it's marked as missing
                if assignment["missing"]:
                    is_missing = True
                # Check if score is 0
                elif assignment["score"] is not None and float(assignment["score"]) == 0:
                    is_missing = True
                # Check if no score and not submitted
                elif assignment["score"] is None and not assignment["submitted_at"]:
                    is_missing = True

                if is_missing:
                    if course_display not in missing_by_course:
                        missing_by_course[course_display] = []
                    missing_by_course[course_display].append(assignment)

            # Maybe redo assignments: graded less than 66% (exclude 0 or missing scores)
            if assignment["score"] is not None and assignment["points_possible"]:
                try:
                    points_value = float(assignment["points_possible"])
                    # Skip if points_possible is 0
                    if points_value == 0:
                        continue

                    score_value = float(assignment["score"])
                    # Exclude assignments with 0 score or missing flag
                    if score_value > 0 and not assignment.get("missing", False):
                        percentage = (score_value / points_value) * 100
                        if percentage < 66:
                            if course_display not in maybe_redo_by_course:
                                maybe_redo_by_course[course_display] = []
                            maybe_redo_by_course[course_display].append(assignment)
                except (ValueError, ZeroDivisionError):
                    pass

    # Section 1: Missing Assignments
    total_missing = sum(len(assignments) for assignments in missing_by_course.values())
    lines.append(f"🚨 MISSING ASSIGNMENTS: {total_missing}")
    lines.append("-" * 70)

    if missing_by_course:
        # Sort courses alphabetically
        for course_name in sorted(missing_by_course.keys()):
            assignments = missing_by_course[course_name]
            # Sort assignments by due date descending (most recent first)
            assignments.sort(key=lambda x: x["due_at"] if x["due_at"] else datetime.min.replace(tzinfo=pacific), reverse=True)

            lines.append(f"\n📚 {course_name} ({len(assignments)})")
            for assignment in assignments:
                due_str = assignment["due_at"].strftime("%Y-%m-%d") if assignment["due_at"] else "No due date"
                score_str = f"{assignment['score']}" if assignment["score"] is not None else "—"
                points_str = f"{assignment['points_possible']}" if assignment["points_possible"] is not None else "—"
                lines.append(f"   • {due_str} | {assignment['name']} | {score_str}/{points_str}")
            lines.append("")
    else:
        lines.append("   ✅ No missing assignments!")
        lines.append("")

    # Section 2: Maybe Redo Assignments
    lines.append("")
    total_redo = sum(len(assignments) for assignments in maybe_redo_by_course.values())
    lines.append(f"⚠️  MAYBE REDO (Scored < 66%): {total_redo}")
    lines.append("-" * 70)

    if maybe_redo_by_course:
        # Sort courses alphabetically
        for course_name in sorted(maybe_redo_by_course.keys()):
            assignments = maybe_redo_by_course[course_name]
            # Sort assignments by due date descending (most recent first)
            assignments.sort(key=lambda x: x["due_at"] if x["due_at"] else datetime.min.replace(tzinfo=pacific), reverse=True)

            lines.append(f"\n📚 {course_name} ({len(assignments)})")
            for assignment in assignments:
                due_str = assignment["due_at"].strftime("%Y-%m-%d") if assignment["due_at"] else "No due date"
                percentage = (float(assignment["score"]) / float(assignment["points_possible"])) * 100
                lines.append(f"   • {due_str} | {assignment['score']}/{assignment['points_possible']} ({percentage:.1f}%) | {assignment['name']}")
            lines.append("")
    else:
        lines.append("   ✅ No assignments scored below 66%!")
        lines.append("")

    lines.append("")
    lines.append("=" * 70)
    lines.append("End of Report")
    lines.append("=" * 70)

    # Use Windows-style line breaks (\r\n) for better compatibility with print preview
    return "\r\n".join(lines)

def save_individual_student_reports():
    """Generate and save individual HTML reports and text action items for each student"""
    saved_files = []

    for student_id, student_data in students_data.items():
        # Clean filename (remove special characters)
        clean_name = "".join(c for c in student_data['name'] if c.isalnum() or c in (' ', '-', '_')).strip()

        # 1. Save HTML report
        student_subset = {student_id: student_data}
        html_content = generate_html_report(student_subset)
        html_filename = f"{clean_name}.html"

        try:
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            log(f"📄 Individual HTML report saved: {html_filename}")
            saved_files.append(html_filename)
        except Exception as e:
            log(f"❌ Error saving HTML report for {student_data['name']}: {e}")

        # 2. Save text action items report
        text_content = generate_action_items_text_report(student_id, student_data)
        text_filename = f"{clean_name}_ActionItems.txt"

        try:
            with open(text_filename, 'w', encoding='utf-8') as f:
                f.write(text_content)
            log(f"📝 Action items report saved: {text_filename}")
            saved_files.append(text_filename)
        except Exception as e:
            log(f"❌ Error saving action items for {student_data['name']}: {e}")

    return saved_files

def generate_email_body_content():
    """Generate comprehensive text content for email body"""
    current_time = now_utc.astimezone(pacific)
    body_content = []

    body_content.append("📚 CANVAS ACADEMIC REPORT")
    body_content.append("=" * 50)
    body_content.append(f"Generated: {current_time.strftime('%Y-%m-%d %I:%M %p')}")
    body_content.append("")

    # Generate content for each student
    for student_id, student_data in students_data.items():
        body_content.append(f"👤 {student_data['name'].upper()}")
        body_content.append("-" * 40)

        # Calculate statistics
        total_courses = len(student_data['courses'])
        total_assignments = sum(len(course['assignments']) for course in student_data['courses'].values())
        overdue_count = 0
        missing_scores = 0
        grading_overdue_count = 0
        awaiting_grade_count = 0
        upcoming_no_submission_count = 0

        for course_data in student_data['courses'].values():
            for assignment in course_data['assignments']:
                # Count overdue assignments (past due and not submitted)
                if assignment["due_at"] and assignment["due_at"] < current_time:
                    if assignment["score"] is None and not assignment["submitted_at"]:
                        overdue_count += 1

                # Count grading overdue (submitted but not graded after 3+ days)
                elif assignment["submitted_at"] and assignment["score"] is None:
                    submitted_time = assignment["submitted_at"]
                    if isinstance(submitted_time, str):
                        try:
                            submitted_time = datetime.fromisoformat(submitted_time.rstrip("Z")).replace(tzinfo=timezone.utc).astimezone(pacific)
                        except:
                            submitted_time = None

                    if submitted_time and (current_time - submitted_time).days >= 3:
                        grading_overdue_count += 1
                    elif submitted_time:
                        awaiting_grade_count += 1

                # Count upcoming assignments with no submission
                elif assignment["due_at"] and assignment["due_at"] > current_time:
                    if assignment["score"] is None and not assignment["submitted_at"]:
                        upcoming_no_submission_count += 1

        # Summary statistics
        body_content.append(f"📊 SUMMARY:")
        body_content.append(f"   • Active Courses: {total_courses}")
        body_content.append(f"   • Total Assignments: {total_assignments}")
        body_content.append(f"   • Overdue Items: {overdue_count}")
        body_content.append(f"   • Grading Overdue: {grading_overdue_count}")
        body_content.append(f"   • Awaiting Grade: {awaiting_grade_count}")
        body_content.append(f"   • Upcoming (No Submission): {upcoming_no_submission_count}")
        body_content.append("")

        # Course grades overview
        body_content.append("📚 COURSE GRADES:")
        for course_id, course_data in student_data['courses'].items():
            course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])
            current_score = course_data.get("current_score")
            final_score = course_data.get("final_score")

            current_grade = f"{current_score:.1f}%" if current_score is not None else "No grade"
            final_grade = f"{final_score:.1f}%" if final_score is not None else "0.0%"

            status_indicator = "⚠️" if current_score is not None and current_score < 80 else "✅"
            body_content.append(f"   {status_indicator} {course_display}: {current_grade} (Final: {final_grade})")

        body_content.append("")

        # Overdue assignments
        if overdue_count > 0:
            body_content.append("⚠️ OVERDUE ASSIGNMENTS:")
            for course_data in student_data['courses'].values():
                for assignment in course_data['assignments']:
                    if assignment["due_at"] and assignment["due_at"] < current_time:
                        if assignment["score"] is None and not assignment["submitted_at"]:
                            due_str = assignment["due_at"].strftime("%Y-%m-%d %I:%M %p")
                            course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])
                            body_content.append(f"   • {due_str} - {course_display}: {assignment['name']}")
            body_content.append("")

        # Upcoming assignments
        upcoming_assignments = []
        one_week = current_time + timedelta(days=7)
        for course_data in student_data['courses'].values():
            for assignment in course_data['assignments']:
                if assignment["due_at"] and current_time <= assignment["due_at"] <= one_week:
                    if assignment["score"] is None and not assignment["submitted_at"]:
                        due_str = assignment["due_at"].strftime("%Y-%m-%d %I:%M %p")
                        course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])
                        upcoming_assignments.append(f"   • {due_str} - {course_display}: {assignment['name']}")

        if upcoming_assignments:
            body_content.append("📅 UPCOMING ASSIGNMENTS (Next 7 Days):")
            body_content.extend(upcoming_assignments)
            body_content.append("")

        # Add action items section
        body_content.append("")
        body_content.append("🎯 ACTION ITEMS")
        body_content.append("-" * 40)

        # Collect missing and maybe redo assignments
        missing_by_course = {}
        maybe_redo_by_course = {}

        for course_data in student_data['courses'].values():
            course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])

            for assignment in course_data['assignments']:
                # Missing assignments
                if assignment["due_at"] and assignment["due_at"] < current_time:
                    # Skip if no valid points_possible
                    if not assignment["points_possible"] or float(assignment["points_possible"]) == 0:
                        continue

                    is_missing = False
                    if assignment["missing"]:
                        is_missing = True
                    elif assignment["score"] is not None and float(assignment["score"]) == 0:
                        is_missing = True
                    elif assignment["score"] is None and not assignment["submitted_at"]:
                        is_missing = True

                    if is_missing:
                        if course_display not in missing_by_course:
                            missing_by_course[course_display] = []
                        missing_by_course[course_display].append(assignment)

                # Maybe redo assignments (exclude 0 or missing scores)
                if assignment["score"] is not None and assignment["points_possible"]:
                    try:
                        points_value = float(assignment["points_possible"])
                        # Skip if points_possible is 0
                        if points_value == 0:
                            continue

                        score_value = float(assignment["score"])
                        # Exclude assignments with 0 score or missing flag
                        if score_value > 0 and not assignment.get("missing", False):
                            percentage = (score_value / points_value) * 100
                            if percentage < 66:
                                if course_display not in maybe_redo_by_course:
                                    maybe_redo_by_course[course_display] = []
                                maybe_redo_by_course[course_display].append(assignment)
                    except (ValueError, ZeroDivisionError):
                        pass

        # Missing assignments
        if missing_by_course:
            body_content.append("")
            total_missing = sum(len(assignments) for assignments in missing_by_course.values())
            body_content.append(f"🚨 MISSING ASSIGNMENTS: {total_missing}")
            for course_name in sorted(missing_by_course.keys()):
                assignments = missing_by_course[course_name]
                assignments.sort(key=lambda x: x["due_at"] if x["due_at"] else datetime.min.replace(tzinfo=pacific), reverse=True)
                body_content.append(f"   📚 {course_name} ({len(assignments)})")
                for assignment in assignments:
                    due_str = assignment["due_at"].strftime("%Y-%m-%d") if assignment["due_at"] else "No due date"
                    score_str = f"{assignment['score']}" if assignment["score"] is not None else "—"
                    points_str = f"{assignment['points_possible']}" if assignment["points_possible"] is not None else "—"
                    body_content.append(f"      • {due_str} | {score_str}/{points_str} | {assignment['name']}")

        # Maybe redo assignments
        if maybe_redo_by_course:
            body_content.append("")
            total_redo = sum(len(assignments) for assignments in maybe_redo_by_course.values())
            body_content.append(f"⚠️  MAYBE REDO (Scored < 66%): {total_redo}")
            for course_name in sorted(maybe_redo_by_course.keys()):
                assignments = maybe_redo_by_course[course_name]
                assignments.sort(key=lambda x: x["due_at"] if x["due_at"] else datetime.min.replace(tzinfo=pacific), reverse=True)
                body_content.append(f"   📚 {course_name} ({len(assignments)})")
                for assignment in assignments:
                    due_str = assignment["due_at"].strftime("%Y-%m-%d") if assignment["due_at"] else "No due date"
                    percentage = (float(assignment["score"]) / float(assignment["points_possible"])) * 100
                    body_content.append(f"      • {due_str} | {assignment['score']}/{assignment['points_possible']} ({percentage:.1f}%) | {assignment['name']}")

        if not missing_by_course and not maybe_redo_by_course:
            body_content.append("")
            body_content.append("   ✅ No action items - all caught up!")

        body_content.append("")
        body_content.append("=" * 50)
        body_content.append("")

    body_content.append("📎 ATTACHMENTS:")
    body_content.append("For each student, you'll find:")
    body_content.append("  • HTML report - Open in browser for detailed interactive view")
    body_content.append("  • Action Items (TXT) - Missing & low-scored assignments for easy copy/paste")
    body_content.append("")
    body_content.append("Best regards,")
    body_content.append("Canvas Integration Bot")

    return "\n".join(body_content)

def generate_email_body_html():
    """Generate HTML email body with hyperlinked assignment names"""
    current_time = now_utc.astimezone(pacific)

    html_parts = []
    html_parts.append("""
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; font-size: 13px; }
            h2 { color: #667eea; border-bottom: 2px solid #667eea; padding-bottom: 5px; font-size: 18px; }
            h3 { color: #555; margin-top: 20px; font-size: 15px; }
            .student-section { margin-bottom: 30px; padding: 15px; background: #f9f9f9; border-radius: 8px; }
            .course-name { font-weight: bold; color: #764ba2; margin-top: 10px; font-size: 13px; }
            .assignment { margin-left: 20px; margin-bottom: 5px; font-size: 12px; }
            .assignment a { color: #667eea; text-decoration: none; }
            .assignment a:hover { text-decoration: underline; }
            .stats { background: #e8f4fd; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 12px; }
            .grades { background: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 12px; }
            .action-items { background: #fff3cd; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 12px; }
            .missing { color: #dc3545; }
            .maybe-redo { color: #856404; }
        </style>
    </head>
    <body>
    """)

    html_parts.append(f"<h2>📚 CANVAS ACADEMIC REPORT</h2>")
    html_parts.append(f"<p><strong>Generated:</strong> {current_time.strftime('%Y-%m-%d %I:%M %p')}</p>")

    # Generate content for each student
    for student_id, student_data in students_data.items():
        html_parts.append(f"<div class='student-section'>")
        html_parts.append(f"<h3>👤 {student_data['name'].upper()}</h3>")

        # Calculate statistics
        total_courses = len(student_data['courses'])
        total_assignments = sum(len(course['assignments']) for course in student_data['courses'].values())
        overdue_count = 0
        grading_overdue_count = 0
        awaiting_grade_count = 0
        upcoming_no_submission_count = 0

        for course_data in student_data['courses'].values():
            for assignment in course_data['assignments']:
                if assignment["due_at"] and assignment["due_at"] < current_time:
                    if assignment["score"] is None and not assignment["submitted_at"]:
                        overdue_count += 1
                elif assignment["submitted_at"] and assignment["score"] is None:
                    submitted_time = assignment["submitted_at"]
                    if isinstance(submitted_time, str):
                        try:
                            submitted_time = datetime.fromisoformat(submitted_time.rstrip("Z")).replace(tzinfo=timezone.utc).astimezone(pacific)
                        except:
                            submitted_time = None
                    if submitted_time and (current_time - submitted_time).days >= 3:
                        grading_overdue_count += 1
                    elif submitted_time:
                        awaiting_grade_count += 1
                elif assignment["due_at"] and assignment["due_at"] > current_time:
                    if assignment["score"] is None and not assignment["submitted_at"]:
                        upcoming_no_submission_count += 1

        # Summary statistics
        html_parts.append("<div class='stats'>")
        html_parts.append("<strong>📊 SUMMARY:</strong><br>")
        html_parts.append(f"• Active Courses: {total_courses}<br>")
        html_parts.append(f"• Total Assignments: {total_assignments}<br>")
        html_parts.append(f"• Overdue Items: {overdue_count}<br>")
        html_parts.append(f"• Grading Overdue: {grading_overdue_count}<br>")
        html_parts.append(f"• Awaiting Grade: {awaiting_grade_count}<br>")
        html_parts.append(f"• Upcoming (No Submission): {upcoming_no_submission_count}")
        html_parts.append("</div>")

        # Course grades
        html_parts.append("<div class='grades'>")
        html_parts.append("<strong>📚 COURSE GRADES:</strong><br>")
        for course_data in student_data['courses'].values():
            course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])
            current_score = course_data.get("current_score")
            final_score = course_data.get("final_score")
            current_grade = f"{current_score:.1f}%" if current_score is not None else "No grade"
            final_grade = f"{final_score:.1f}%" if final_score is not None else "0.0%"
            status_indicator = "⚠️" if current_score is not None and current_score < 80 else "✅"
            html_parts.append(f"{status_indicator} {course_display}: {current_grade} (Final: {final_grade})<br>")
        html_parts.append("</div>")

        # Action items with hyperlinks
        missing_by_course = {}
        maybe_redo_by_course = {}

        for course_data in student_data['courses'].values():
            course_display = COURSE_ALIASES.get(course_data["name"], course_data["name"])

            for assignment in course_data['assignments']:
                # Missing assignments
                if assignment["due_at"] and assignment["due_at"] < current_time:
                    # Skip if no valid points_possible
                    if not assignment["points_possible"] or float(assignment["points_possible"]) == 0:
                        continue

                    is_missing = False
                    if assignment["missing"]:
                        is_missing = True
                    elif assignment["score"] is not None and float(assignment["score"]) == 0:
                        is_missing = True
                    elif assignment["score"] is None and not assignment["submitted_at"]:
                        is_missing = True

                    if is_missing:
                        if course_display not in missing_by_course:
                            missing_by_course[course_display] = []
                        missing_by_course[course_display].append(assignment)

                # Maybe redo assignments (exclude 0 or missing scores)
                if assignment["score"] is not None and assignment["points_possible"]:
                    try:
                        points_value = float(assignment["points_possible"])
                        # Skip if points_possible is 0
                        if points_value == 0:
                            continue

                        score_value = float(assignment["score"])
                        # Exclude assignments with 0 score or missing flag
                        if score_value > 0 and not assignment.get("missing", False):
                            percentage = (score_value / points_value) * 100
                            if percentage < 66:
                                if course_display not in maybe_redo_by_course:
                                    maybe_redo_by_course[course_display] = []
                                maybe_redo_by_course[course_display].append(assignment)
                    except (ValueError, ZeroDivisionError):
                        pass

        if missing_by_course or maybe_redo_by_course:
            html_parts.append("<div class='action-items'>")
            html_parts.append("<strong>🎯 ACTION ITEMS</strong><br><br>")

            # Missing assignments
            if missing_by_course:
                total_missing = sum(len(assignments) for assignments in missing_by_course.values())
                html_parts.append(f"<span class='missing'><strong>🚨 MISSING ASSIGNMENTS: {total_missing}</strong></span><br>")
                for course_name in sorted(missing_by_course.keys()):
                    assignments = missing_by_course[course_name]
                    assignments.sort(key=lambda x: x["due_at"] if x["due_at"] else datetime.min.replace(tzinfo=pacific), reverse=True)
                    html_parts.append(f"<div class='course-name'>📚 {course_name} ({len(assignments)})</div>")
                    for assignment in assignments:
                        due_str = assignment["due_at"].strftime("%Y-%m-%d") if assignment["due_at"] else "No due date"
                        score_str = f"{assignment['score']}" if assignment["score"] is not None else "—"
                        points_str = f"{assignment['points_possible']}" if assignment["points_possible"] is not None else "—"
                        url = assignment.get("html_url", "#")
                        html_parts.append(f"<div class='assignment'>• {due_str} | <a href='{url}' target='_blank'>{assignment['name']}</a> | Score: {score_str}/{points_str}</div>")
                html_parts.append("<br>")

            # Maybe redo assignments
            if maybe_redo_by_course:
                total_redo = sum(len(assignments) for assignments in maybe_redo_by_course.values())
                html_parts.append(f"<span class='maybe-redo'><strong>⚠️ MAYBE REDO (Scored &lt; 66%): {total_redo}</strong></span><br>")
                for course_name in sorted(maybe_redo_by_course.keys()):
                    assignments = maybe_redo_by_course[course_name]
                    assignments.sort(key=lambda x: x["due_at"] if x["due_at"] else datetime.min.replace(tzinfo=pacific), reverse=True)
                    html_parts.append(f"<div class='course-name'>📚 {course_name} ({len(assignments)})</div>")
                    for assignment in assignments:
                        due_str = assignment["due_at"].strftime("%Y-%m-%d") if assignment["due_at"] else "No due date"
                        percentage = (float(assignment["score"]) / float(assignment["points_possible"])) * 100
                        url = assignment.get("html_url", "#")
                        html_parts.append(f"<div class='assignment'>• {due_str} | <a href='{url}' target='_blank'>{assignment['name']}</a> | Score: {assignment['score']}/{assignment['points_possible']} ({percentage:.1f}%)</div>")

            html_parts.append("</div>")
        else:
            html_parts.append("<div class='action-items'>")
            html_parts.append("<strong>✅ No action items - all caught up!</strong>")
            html_parts.append("</div>")

        html_parts.append("</div>")  # Close student-section

    html_parts.append("<hr>")
    html_parts.append("<p><strong>📎 ATTACHMENTS:</strong><br>")
    html_parts.append("For each student, you'll find:<br>")
    html_parts.append("• HTML report - Open in browser for detailed interactive view<br>")
    html_parts.append("• Action Items (TXT) - Missing & low-scored assignments for easy copy/paste</p>")
    html_parts.append("<p>Best regards,<br>Canvas Integration Bot</p>")
    html_parts.append("</body></html>")

    return "".join(html_parts)

def send_email_report(individual_report_files, current_time):
    """Send email with comprehensive body content and individual student report attachments"""
    if not EMAIL_ENABLED:
        log("📧 Email sending disabled (set EMAIL_ENABLED=true to enable)")
        return

    if not GMAIL_USER:
        print("❌ Email configuration missing. Please set GMAIL_USER action secret")
        return
    if not GMAIL_APP_PASSWORD:
        print("❌ Email configuration missing. Please set GMAIL_APP_PASSWORD action secret")
        return

    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER
        msg['Subject'] = f"📚 Canvas Academic Report - {current_time.strftime('%Y-%m-%d %I:%M %p')}"

        # Generate both plain text and HTML versions
        text_body = generate_email_body_content()
        html_body = generate_email_body_html()

        # Attach both versions (email clients will prefer HTML if supported)
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        # Attach individual student HTML files
        for filename in individual_report_files:
            try:
                with open(filename, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())

                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {os.path.basename(filename)}'
                )
                msg.attach(part)
                log(f"📎 Attached: {filename}")
            except Exception as e:
                log(f"❌ Failed to attach {filename}: {e}")

        # Connect to Gmail SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Enable encryption
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)

        # Send email
        text = msg.as_string()
        server.sendmail(GMAIL_USER, GMAIL_USER, text)
        server.quit()

        log(f"✅ Email sent successfully to {GMAIL_USER}")
        log(f"📧 Email includes comprehensive report for all students")
        log(f"📎 {len(individual_report_files)} individual student reports attached")
        # Always print success message even when logging is disabled
        if not LOGGING_ENABLED:
            print("✅ Email sent successfully")

    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        log("💡 Make sure you're using a Gmail App Password, not your regular password")
        log("💡 Enable 2FA and generate an App Password at: https://myaccount.google.com/apppasswords")

print(f'ℹ️  Starting execution...')
# ─── Initialize Canvas Client ───────────────────────────────────────────────
canvas = Canvas(CANVAS_API_URL, CANVAS_API_KEY)
parent_user = canvas.get_user("self")
observees = parent_user.get_observees()

now_utc = datetime.now(timezone.utc)
pacific = ZoneInfo("America/Los_Angeles")

# ─── Data Structure to Hold Everything ──────────────────────────────────────
students_data = {}

print(f'ℹ️  Getting student data...')
for student in observees:
    print(f"ℹ️  Getting student's data...")
    student_info = {
        "courses": {},   # course_id -> {name, current_score, final_score, assignments: []}
    }

    # 1. Fetch all active courses (via enrollments)
    for enr in student.get_enrollments(
        type=["StudentEnrollment"],
        state=["active"],
        per_page=100
    ):
        try:
            course = canvas.get_course(enr.course_id)
        except Exception:
            continue

        g = enr.grades
        student_info["courses"][course.id] = {
            "name": course.name,
            "current_score": g.get("current_score"),
            "final_score": g.get("final_score"),
            "assignments": [],
            "html_url": getattr(course, "html_url", f"{CANVAS_API_URL}/courses/{course.id}")
        }

        # 2. Fetch all submissions (includes assignment info)
        for sub in course.get_multiple_submissions(
            student_ids=[student.id],
            include=["assignment"]
        ):
            a = sub.assignment
            due_dt = None
            if a.get("due_at"):
                due_dt = datetime.fromisoformat(a.get("due_at").rstrip("Z")).replace(tzinfo=timezone.utc).astimezone(pacific)

            student_info["courses"][course.id]["assignments"].append({
                "id": a.get("id"),
                "name": a.get("name"),
                "due_at": due_dt,
                "points_possible": a.get("points_possible"),
                "score": getattr(sub, "score", None),
                "grade": getattr(sub, "grade", None),
                "missing": getattr(sub, "missing", None),
                "submitted_at": getattr(sub, "submitted_at", None),
                "html_url": a.get("html_url")
            })

    students_data[student.id] = {
        "name": student.name,
        "courses": student_info["courses"]
    }

print(f'ℹ️  Slicing the data...')
for sid in students_data:
    full_overview(sid)
    overdue_overview(sid)
    upcoming_week(sid)

# Generate HTML reports
log(f"\n{'='*70}")
log("🌐 Generating HTML Reports...")
log(f"{'='*70}")
if not LOGGING_ENABLED:
    print("🌐 Generating reports...")

# Save overall report
html_filename = save_html_report()

# Save individual student reports
individual_reports = save_individual_student_reports()

# Send email if enabled and reports were generated successfully
if individual_reports and EMAIL_ENABLED:
    log(f"\n{'='*70}")
    log("📧 Sending Email Report...")
    log(f"{'='*70}")
    if not LOGGING_ENABLED:
        print("📧 Sending email...")
    send_email_report(individual_reports, now_utc.astimezone(pacific))

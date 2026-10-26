# Nogoa Private school site
    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    python app.py   # http://127.0.0.1:5000
Admin login: admin@nogoa.school / admin123 (CHANGE THIS before deploying)

## Where images go
| Image | How to add it |
|---|---|
| Home page background | Admin > Edit site text, logo and home picture |
| School logo | same page |
| Proprietor, headmistress, staff photos | Admin > Manage photos... > Leadership and staff |
| Gallery / student photos | Admin > Manage photos... > Gallery photos |
| Fixed design images you keep in the code | put the file in static/img/ and use url_for('static', filename='img/NAME.jpg') |

## How the site knows who is admin
Each user row has a `role` column. At login the app copies it into the signed session cookie,
and `@login_required("admin")` in app.py checks it on every admin page.
To make another person admin (they must register first), run in the project folder:
    python -c "import sqlite3; c=sqlite3.connect('school.db'); c.execute(\"UPDATE users SET role='admin' WHERE email='THEIR@EMAIL'\"); c.commit()"


from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html", school_name="Nogoa Private")

@app.route("/admissions")
def admissions():
    steps = [
        {"title": "Fill Application", "desc": "Complete the online form."},
        {"title": "Upload Documents", "desc": "Birth certificate and passport photo."},
    ]
    return render_template("admissions.html", steps=steps)

if __name__ == "__main__":
    app.run(debug=True)
# Student Attendance and Leave Management System

## About the Project

This web application was developed to manage student attendance and leave requests.

## Technologies Used

- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript

## Main Features

The application has two types of users: Admin and Student.

### Admin

Available functions:

- Managing student details
- Managing modules
- Marking and updating student attendance
- Viewing attendance records
- Viewing and managing leave requests
- Approving or rejecting leave requests

### Student

Available functions:

- Logging into the system
- Viewing attendance details
- Submitting leave requests
- Viewing the status of leave requests

## How to Run the Project

1. Download the project.
2. Open the project folder in VS Code.
3. Open the terminal.
4. Install the required packages: `pip install -r requirements.txt`
5. Run the application: `python app.py`
6. Open the local address shown in the terminal using a web browser.

## Database

SQLite is used to store student details, module details, attendance records and leave requests. The database file is created locally when the application runs.
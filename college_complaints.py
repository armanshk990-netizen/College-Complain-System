-- College Complaint System — Database Setup
-- Run: mysql -u root -p < college_complaints.sql

CREATE DATABASE IF NOT EXISTS college_complaints;
USE college_complaints;

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id    INT AUTO_INCREMENT PRIMARY KEY,
    student_name    VARCHAR(100) NOT NULL,
    roll_number     VARCHAR(30)  NOT NULL,
    student_class   VARCHAR(30)  NOT NULL,
    category        VARCHAR(50)  NOT NULL,
    description     TEXT         NOT NULL,
    date_submitted  VARCHAR(30)  NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'Pending',
    remark          VARCHAR(255),
    is_archived     INT          DEFAULT 0
);

CREATE TABLE IF NOT EXISTS status_history (
    history_id    INT AUTO_INCREMENT PRIMARY KEY,
    complaint_id  INT NOT NULL,
    old_status    VARCHAR(20),
    new_status    VARCHAR(20),
    change_time   VARCHAR(30),
    FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admins (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    username   VARCHAR(50) UNIQUE NOT NULL,
    password   VARCHAR(100) NOT NULL,
    created_at VARCHAR(30)
);

CREATE TABLE IF NOT EXISTS inspectors (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    password   VARCHAR(100) UNIQUE NOT NULL,
    created_by VARCHAR(50),
    created_at VARCHAR(30)
);

-- Default admin
INSERT INTO admins (username, password, created_at)
VALUES ('admin', 'admin123', NOW());

-- Sample complaints
INSERT INTO complaints
(student_name, roll_number, student_class, category, description, date_submitted, status, remark, is_archived)
VALUES
('Aarav Sharma', 'AIML01', 'AIML-A', 'Classroom',  'Fan not working in room 101',       '2025-01-10', 'Pending',     NULL,               0),
('Diya Patel',   'AIML02', 'AIML-A', 'Classroom',  'Projector not displaying properly', '2025-01-10', 'Pending',     NULL,               0),
('Rohan Mehta',  'AIML03', 'AIML-B', 'Washroom',   'Washroom near lab not cleaned',     '2025-01-11', 'In Progress', 'Cleaner assigned', 0),
('Sara Khan',    'AIML04', 'AIML-B', 'Laboratory', 'Computer no. 12 not starting',      '2025-01-11', 'Pending',     NULL,               0),
('Vivaan Joshi', 'AIML05', 'AIML-C', 'Wi-Fi',      'Wi-Fi very slow in library',        '2025-01-12', 'In Progress', 'Network team',     0),
('Anaya Desai',  'AIML06', 'AIML-C', 'Library',    'Library books not arranged',        '2025-01-12', 'Resolved',    'Re-arranged',      1),
('Kabir Singh',  'CO01',   'CO-A',   'Water',      'Water cooler not working',          '2025-01-13', 'Pending',     NULL,               0),
('Isha Verma',   'CO02',   'CO-A',   'Furniture',  'Broken bench in room 205',          '2025-01-13', 'In Progress', 'Carpenter',        0),
('Arjun Rao',    'IT01',   'IT-A',   'Teacher',    'Teacher not attending lectures',    '2025-01-14', 'Pending',     NULL,               0),
('Meera Nair',   'IT02',   'IT-B',   'ID Card',    'ID card not received',              '2025-01-14', 'Resolved',    'Card issued',      1);

-- Status history
INSERT INTO status_history (complaint_id, old_status, new_status, change_time) VALUES
(3,  'Pending',     'In Progress', '2025-01-12 09:00:00'),
(5,  'Pending',     'In Progress', '2025-01-13 10:00:00'),
(6,  'Pending',     'In Progress', '2025-01-13 09:00:00'),
(6,  'In Progress', 'Resolved',    '2025-01-14 14:00:00'),
(8,  'Pending',     'In Progress', '2025-01-14 10:00:00'),
(10, 'Pending',     'In Progress', '2025-01-15 09:00:00'),
(10, 'In Progress', 'Resolved',    '2025-01-16 11:00:00');

-- Inspector
INSERT INTO inspectors (name, password, created_by, created_at) VALUES
('Mr. Sharma (HOD)', 'inspect2024', 'admin', NOW());

-- Verify
SELECT 'complaints'     AS table_name, COUNT(*) AS rows_count FROM complaints
UNION ALL SELECT 'status_history', COUNT(*) FROM status_history
UNION ALL SELECT 'admins',         COUNT(*) FROM admins
UNION ALL SELECT 'inspectors',     COUNT(*) FROM inspectors;
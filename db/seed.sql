
-- Student Auctions - Vulnerable Demo Data
-- MariaDB 11.4
-- All information is fictional.
-- Password for all demo accounts: Student123!

SET time_zone = '+00:00';

START TRANSACTION;

-- 1. Approved Students
INSERT INTO students
(student_id, full_name, university_email, is_active)
VALUES
('20260001', 'Demo Administrator', 'admin@students.example.edu', 1),
('20260015', 'Giorgos Georgiou', 'giorgos@students.example.edu', 1),
('20260016', 'Maria Andreou', 'maria@students.example.edu', 1),
('20260017', 'Andreas Ioannou', 'andreas@students.example.edu', 1),
('20260018', 'Eleni Demo', 'eleni@students.example.edu', 1),
('20260019', 'Nikos Demo', 'nikos@students.example.edu', 1),
('20260020', 'Sofia Demo', 'sofia@students.example.edu', 1);

-- 2. Users
-- Vulnerable: SHA-1 without salt
-- SHA1("Student123!") =
-- 6b018bfa7a54ddd1bf8f6a1bdaeb107056506873

INSERT INTO users
(id, student_id, username, email, password_hash,
 role, is_active, created_at)
VALUES
(1, '20260001', 'admin', 'admin@students.example.edu',
 '6b018bfa7a54ddd1bf8f6a1bdaeb107056506873',
 'admin', 1, '2026-11-01 09:00:00'),

(15, '20260015', 'giorgos', 'giorgos@students.example.edu',
 '6b018bfa7a54ddd1bf8f6a1bdaeb107056506873',
 'user', 1, '2026-11-01 09:10:00'),

(16, '20260016', 'maria', 'maria@students.example.edu',
 '6b018bfa7a54ddd1bf8f6a1bdaeb107056506873',
 'user', 1, '2026-11-01 09:20:00'),

(17, '20260017', 'andreas', 'andreas@students.example.edu',
 '6b018bfa7a54ddd1bf8f6a1bdaeb107056506873',
 'user', 1, '2026-11-01 09:30:00');

-- 3. Delivery Addresses
INSERT INTO addresses
(user_id, line1, city, postal_code, updated_at)
VALUES
(15, '25 Example Street', 'Paphos', '8010',
 '2026-11-01 10:00:00'),

(16, '20 Example Street', 'Limassol', '3010',
 '2026-11-01 10:05:00'),

(17, '10 Sample Avenue', 'Nicosia', '1010',
 '2026-11-01 10:10:00');

-- 4. Auctions
-- 101: Public and open
-- 102: Closed, Giorgos is the winner
-- 103: Hidden auction for SQL Injection testing

INSERT INTO auctions
(id, seller_id, winner_user_id, title, description,
 starting_price, is_public, status, ends_at, created_at)
VALUES
(101, 17, NULL,
 'Laptop HP',
 'Used HP laptop in good condition.',
 150.00, 1, 'open',
 '2030-12-31 23:59:59',
 '2026-11-02 12:00:00'),

(102, 16, 15,
 'Books',
 'Second-hand university textbooks.',
 20.00, 1, 'closed',
 '2026-11-03 18:00:00',
 '2026-11-02 12:30:00'),

(103, 17, NULL,
 'PRIVATE_DEMO_01',
 'Hidden test record: not for public search.',
 10.00, 0, 'open',
 '2030-12-31 23:59:59',
 '2026-11-02 13:00:00');

-- 5. Bids
INSERT INTO bids
(id, auction_id, bidder_id, amount, created_at)
VALUES
(1001, 102, 15, 40.00, '2026-11-03 14:00:00');

COMMIT;

USE studybuddy;

-- Set this to the ID of the user you want demo data for
-- Example: after registering, run:
--   SELECT id, email FROM users;
-- and set the correct id here.
SET @USER_ID = 1;

-- Subjects
INSERT INTO subjects (user_id, name, code, attended_classes, total_classes)
VALUES
(@USER_ID, 'Database Systems', 'DBS101', 10, 12),
(@USER_ID, 'Data Structures & Algorithms', 'DSA201', 6, 10),
(@USER_ID, 'Calculus II', 'MATH202', 8, 11);

SET @SUBJ_DB = LAST_INSERT_ID();

-- Unfortunately LAST_INSERT_ID only returns last row, so fetch IDs directly
SELECT id INTO @SUBJ_DBS FROM subjects WHERE user_id=@USER_ID AND name='Database Systems' LIMIT 1;
SELECT id INTO @SUBJ_DSA FROM subjects WHERE user_id=@USER_ID AND name='Data Structures & Algorithms' LIMIT 1;
SELECT id INTO @SUBJ_CALC FROM subjects WHERE user_id=@USER_ID AND name='Calculus II' LIMIT 1;

-- Topics for Database Systems
INSERT INTO topics (subject_id, name, is_completed, order_index) VALUES
(@SUBJ_DBS, 'Introduction', 1, 1),
(@SUBJ_DBS, 'ER Diagrams', 1, 2),
(@SUBJ_DBS, 'Relational Model', 1, 3),
(@SUBJ_DBS, 'SQL', 1, 4),
(@SUBJ_DBS, 'Normalization', 0, 5),
(@SUBJ_DBS, 'Transactions', 0, 6),
(@SUBJ_DBS, 'Indexing', 0, 7),
(@SUBJ_DBS, 'NoSQL', 0, 8);

-- Topics for DSA
INSERT INTO topics (subject_id, name, is_completed, order_index) VALUES
(@SUBJ_DSA, 'Arrays & Linked Lists', 1, 1),
(@SUBJ_DSA, 'Stacks & Queues', 1, 2),
(@SUBJ_DSA, 'Trees', 0, 3),
(@SUBJ_DSA, 'Graphs', 0, 4),
(@SUBJ_DSA, 'Hashing', 0, 5),
(@SUBJ_DSA, 'Heaps & Priority Queues', 0, 6);

-- Topics for Calculus
INSERT INTO topics (subject_id, name, is_completed, order_index) VALUES
(@SUBJ_CALC, 'Limits & Continuity', 1, 1),
(@SUBJ_CALC, 'Derivatives', 1, 2),
(@SUBJ_CALC, 'Integrals', 0, 3),
(@SUBJ_CALC, 'Series', 0, 4);

-- Assignments
INSERT INTO assignments (user_id, subject_id, title, description, due_date, is_completed)
VALUES
(@USER_ID, @SUBJ_DBS, 'Normalization problem set', 'Practice 3NF and BCNF decomposition.', DATE_ADD(CURDATE(), INTERVAL 2 DAY), 0),
(@USER_ID, @SUBJ_DSA, 'Binary Search Tree implementation', 'Implement insert, search, delete.', DATE_ADD(CURDATE(), INTERVAL 5 DAY), 0),
(@USER_ID, @SUBJ_CALC, 'Integration worksheet', 'Definite and indefinite integrals.', DATE_ADD(CURDATE(), INTERVAL 7 DAY), 1);

-- Tests
INSERT INTO tests (user_id, subject_id, title, test_date)
VALUES
(@USER_ID, @SUBJ_DBS, 'Database Midterm Test', DATE_ADD(CURDATE(), INTERVAL 2 DAY)),
(@USER_ID, @SUBJ_DSA, 'DSA Quiz 1', DATE_ADD(CURDATE(), INTERVAL 4 DAY));

SELECT id INTO @TEST_DBS FROM tests WHERE user_id=@USER_ID AND title='Database Midterm Test' LIMIT 1;
SELECT id INTO @TEST_DSA FROM tests WHERE user_id=@USER_ID AND title='DSA Quiz 1' LIMIT 1;

-- Link some topics to tests
INSERT INTO test_topics (test_id, topic_id)
SELECT @TEST_DBS, id FROM topics
 WHERE subject_id=@SUBJ_DBS AND name IN ('SQL','Normalization','Transactions');

INSERT INTO test_topics (test_id, topic_id)
SELECT @TEST_DSA, id FROM topics
 WHERE subject_id=@SUBJ_DSA AND name IN ('Arrays & Linked Lists','Stacks & Queues','Trees');

-- Exams
INSERT INTO exams (user_id, subject_id, title, exam_date)
VALUES
(@USER_ID, @SUBJ_DBS, 'Database Final Exam', DATE_ADD(CURDATE(), INTERVAL 14 DAY)),
(@USER_ID, @SUBJ_CALC, 'Calculus II Final', DATE_ADD(CURDATE(), INTERVAL 21 DAY));

SELECT id INTO @EXAM_DBS FROM exams WHERE user_id=@USER_ID AND title='Database Final Exam' LIMIT 1;
SELECT id INTO @EXAM_CALC FROM exams WHERE user_id=@USER_ID AND title='Calculus II Final' LIMIT 1;

INSERT INTO exam_topics (exam_id, topic_id)
SELECT @EXAM_DBS, id FROM topics WHERE subject_id=@SUBJ_DBS;

INSERT INTO exam_topics (exam_id, topic_id)
SELECT @EXAM_CALC, id FROM topics WHERE subject_id=@SUBJ_CALC;